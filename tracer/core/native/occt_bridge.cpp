// Tracer Studio <-> OpenCascade bridge: STEP read/write and 3D fillet/chamfer
// over a triangle mesh.
//
// Deliberately tiny C ABI (dlopen-able from Python ctypes, no wrapped
// types). Tracer Studio's kernel guarantees watertight meshes, so everything
// sews triangles into solids first; anything OCCT returns is re-
// tessellated to OBJ which trimesh/manifold3d consume on the Python side.
//
// Build: g++ -O2 -fPIC -shared -o occt_bridge.so occt_bridge.cpp \
//        -I/usr/include/opencascade -lTKernel -lTKBRep -lTKGeomBase \
//        -lTKMesh -lTKDESTEP -lTKXSBase -lTKFillet -lTKTopAlgo

#include <BRepAdaptor_Curve.hxx>
#include <BRepAdaptor_Surface.hxx>
#include <BRep_Builder.hxx>
#include <BRep_Tool.hxx>
#include <BRepFilletAPI_MakeChamfer.hxx>
#include <BRepFilletAPI_MakeFillet.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepBuilderAPI_MakePolygon.hxx>
#include <BRepBuilderAPI_Sewing.hxx>
#include <BRepTools.hxx>
#include <GCPnts_AbscissaPoint.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <Interface_Static.hxx>
#include <Poly_Triangulation.hxx>
#include <ShapeUpgrade_UnifySameDomain.hxx>
#include <Standard_Failure.hxx>
#include <Standard_Version.hxx>
#include <STEPControl_Reader.hxx>
#include <STEPControl_Writer.hxx>
#include <TopExp.hxx>
#include <TopExp_Explorer.hxx>
#include <TopLoc_Location.hxx>
#include <TopTools_IndexedDataMapOfShapeListOfShape.hxx>
#include <TopTools_IndexedMapOfShape.hxx>
#include <TopTools_ListOfShape.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Compound.hxx>
#include <TopoDS_Edge.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shell.hxx>
#include <TopoDS_Solid.hxx>
#include <gp_Dir.hxx>
#include <gp_Pln.hxx>
#include <gp_Pnt.hxx>
#include <gp_Vec.hxx>

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

static std::string g_err;

static void set_err(const std::string &msg) { g_err = msg; }

// A shell is closed iff every edge borders two of its faces.
static bool shell_closed(const TopoDS_Shape &shell) {
  TopTools_IndexedDataMapOfShapeListOfShape edge_faces;
  TopExp::MapShapesAndAncestors(shell, TopAbs_EDGE, TopAbs_FACE, edge_faces);
  if (edge_faces.IsEmpty())
    return false;
  for (int i = 1; i <= edge_faces.Extent(); ++i)
    if (edge_faces(i).Extent() < 2)
      return false;
  return true;
}

// Triangle mesh -> compound of closed solids (one per watertight shell).
static bool mesh_to_solids(const double *verts, int nverts, const int *tris,
                           int ntris, TopoDS_Shape &out, std::string &err) {
  BRepBuilderAPI_Sewing sewing(1e-5);
  int made = 0;
  for (int t = 0; t < ntris; ++t) {
    const int *ix = tris + 3 * t;
    if (ix[0] < 0 || ix[1] < 0 || ix[2] < 0 ||
        ix[0] >= nverts || ix[1] >= nverts || ix[2] >= nverts) {
      err = "triangle index out of range";
      return false;
    }
    const double *a = verts + 3 * ix[0];
    const double *b = verts + 3 * ix[1];
    const double *c = verts + 3 * ix[2];
    gp_Pnt p0(a[0], a[1], a[2]), p1(b[0], b[1], b[2]), p2(c[0], c[1], c[2]);
    gp_XYZ e1 = p1.XYZ() - p0.XYZ();
    gp_XYZ e2 = p2.XYZ() - p0.XYZ();
    gp_XYZ n = e1.Crossed(e2);
    double nl = n.Modulus();
    if (nl < 1e-9)
      continue;  // degenerate or collinear triangle
    gp_Pln plane(p0, gp_Dir(n.X() / nl, n.Y() / nl, n.Z() / nl));
    BRepBuilderAPI_MakePolygon poly(p0, p1, p2, Standard_True);
    if (!poly.IsDone())
      continue;
    BRepBuilderAPI_MakeFace mf(plane, poly.Wire());
    if (!mf.IsDone())
      continue;
    sewing.Add(mf.Face());
    ++made;
  }
  if (!made) {
    err = "no usable triangles in mesh";
    return false;
  }
  sewing.Perform();
  TopoDS_Shape sewn = sewing.SewedShape();
  BRep_Builder builder;
  TopoDS_Compound comp;
  builder.MakeCompound(comp);
  int nsolids = 0;
  for (TopExp_Explorer ex(sewn, TopAbs_SHELL); ex.More(); ex.Next()) {
    TopoDS_Shell shell = TopoDS::Shell(ex.Current());
    if (!shell_closed(shell))
      continue;  // open shell: not a body we can promise
    TopoDS_Solid solid;
    builder.MakeSolid(solid);
    builder.Add(solid, shell);
    solid.Orientation(TopAbs_FORWARD);
    builder.Add(comp, solid);
    ++nsolids;
  }
  if (!nsolids) {
    err = "mesh did not form a closed solid (sewing failed)";
    return false;
  }
  out = comp;
  return true;
}

// Tessellate a shape and write it as OBJ; returns triangle count (-1 = err).
static long shape_to_obj(const TopoDS_Shape &shape, const char *obj_out,
                         std::string &err) {
  // refine=true (2nd arg Standard_False = absolute deflection), parallel
  // ON: same settings the STEP import uses (which re-manifolds cleanly).
  BRepMesh_IncrementalMesh mesher(shape, 0.1, Standard_False, 0.2,
                                  Standard_True);
  mesher.Perform();
  if (!mesher.IsDone()) {
    err = "tessellation failed";
    return -1;
  }
  FILE *f = std::fopen(obj_out, "wb");
  if (!f) {
    err = "cannot open output OBJ";
    return -1;
  }
  long vbase = 0;
  long ntri = 0;
  std::fprintf(f, "# tracer occt_bridge\n");
  for (TopExp_Explorer ex(shape, TopAbs_FACE); ex.More(); ex.Next()) {
    TopoDS_Face face = TopoDS::Face(ex.Current());
    TopLoc_Location loc;
    Handle(Poly_Triangulation) tri = BRep_Tool::Triangulation(face, loc);
    if (tri.IsNull())
      continue;
    bool reversed = face.Orientation() == TopAbs_REVERSED;
    gp_Trsf xform = loc.Transformation();
    for (int i = 1; i <= tri->NbNodes(); ++i) {
      gp_Pnt p = tri->Node(i).Transformed(xform);
      std::fprintf(f, "v %.9f %.9f %.9f\n", p.X(), p.Y(), p.Z());
    }
    for (int i = 1; i <= tri->NbTriangles(); ++i) {
      Poly_Triangle t = tri->Triangle(i);
      int a = vbase + t.Value(1), b = vbase + t.Value(2),
          c = vbase + t.Value(3);
      if (reversed)
        std::swap(b, c);
      std::fprintf(f, "f %d %d %d\n", a, b, c);
      ++ntri;
    }
    vbase += tri->NbNodes();
  }
  std::fclose(f);
  if (!ntri)
    err = "shape tessellated to zero triangles";
  return ntri ? ntri : -1;
}

// Fillet (or chamfer) every edge of one solid. If the all-edges build
// fails (tangent edges, oversized radius), edges that individually fail
// are dropped and the survivors are rebuilt once.
static TopoDS_Shape fillet_solid(const TopoDS_Solid &sol, double radius,
                                 int chamfer, std::string &err) {
  TopTools_IndexedMapOfShape edges;
  TopExp::MapShapes(sol, TopAbs_EDGE, edges);
  if (edges.IsEmpty()) {
    err = "solid has no edges";
    return TopoDS_Shape();
  }
  auto attempt = [&](const std::vector<int> &ids,
                     TopoDS_Shape &out) -> bool {
    try {
      if (chamfer) {
        BRepFilletAPI_MakeChamfer mk(sol);
        for (int i : ids)
          mk.Add(radius, TopoDS::Edge(edges(i)));
        if (!mk.IsDone())
          mk.Build();
        if (!mk.IsDone())
          return false;
        out = mk.Shape();
      } else {
        BRepFilletAPI_MakeFillet mk(sol);
        for (int i : ids)
          mk.Add(radius, TopoDS::Edge(edges(i)));   // constant-radius form;
        if (!mk.IsDone())                           // Add(E) alone = variable
          mk.Build();                               // radius => NoSuchObject
        if (!mk.IsDone())
          return false;
        out = mk.Shape();
      }
      return !out.IsNull();
    } catch (const Standard_Failure &e) {
      err = std::string("fillet: ") + (e.GetMessageString() ?
                                       e.GetMessageString() : "failed");
      return false;
    } catch (...) {
      err = "fillet: unknown exception";
      return false;
    }
  };
  std::vector<int> all;
  for (int i = 1; i <= edges.Extent(); ++i)
    all.push_back(i);
  TopoDS_Shape shaped;
  if (attempt(all, shaped))
    return shaped;
  std::vector<int> good;
  for (int i : all) {
    TopoDS_Shape one;
    if (attempt(std::vector<int>{i}, one))
      good.push_back(i);
  }
  if (good.empty()) {
    err = chamfer ? "no edge could be chamfered at this size"
                  : "no edge could be filleted at this radius";
    return TopoDS_Shape();
  }
  if (!attempt(good, shaped)) {
    err = chamfer ? "combined chamfer build failed"
                  : "combined fillet build failed";
    return TopoDS_Shape();
  }
  return shaped;
}

extern "C" {

const char *occt_last_error() { return g_err.c_str(); }

int occt_version_major() { return OCC_VERSION_MAJOR; }

int step_export(const char *path, const double *verts, int nverts,
                const int *tris, int ntris) {
  try {
    TopoDS_Shape comp;
    std::string err;
    if (!mesh_to_solids(verts, nverts, tris, ntris, comp, err)) {
      set_err(err);
      return 0;
    }
    STEPControl_Writer writer;
    Interface_Static::SetCVal("write.step.unit", "MM");
    Interface_Static::SetIVal("write.step.nonmanifold", 0);
    IFSelect_ReturnStatus st = writer.Transfer(comp, STEPControl_AsIs);
    if (st != IFSelect_RetDone) {
      set_err("STEP transfer failed");
      return 0;
    }
    st = writer.Write(path);
    if (st != IFSelect_RetDone) {
      set_err("STEP write failed");
      return 0;
    }
    return 1;
  } catch (const std::exception &e) {
    set_err(std::string("occt: ") + e.what());
    return 0;
  } catch (...) {
    set_err("occt: unknown exception");
    return 0;
  }
}

int step_import(const char *step_path, const char *obj_out) {
  try {
    STEPControl_Reader reader;
    if (reader.ReadFile(step_path) != IFSelect_RetDone) {
      set_err("could not read STEP file");
      return 0;
    }
    reader.TransferRoots();
    TopoDS_Shape shape = reader.OneShape();
    if (shape.IsNull()) {
      set_err("STEP file held no geometry");
      return 0;
    }
    std::string err;
    if (shape_to_obj(shape, obj_out, err) < 0) {
      set_err(err);
      return 0;
    }
    return 1;
  } catch (const std::exception &e) {
    set_err(std::string("occt: ") + e.what());
    return 0;
  } catch (...) {
    set_err("occt: unknown exception during import");
    return 0;
  }
}

// Fillet (chamfer=0) or chamfer (chamfer=1) every edge of the mesh's
// solids; the processed geometry is written to obj_out.
int fillet_chamfer(const char *obj_out, const double *verts, int nverts,
                   const int *tris, int ntris, double radius, int chamfer) {
  try {
    if (!(radius > 0.0)) {
      set_err("radius must be positive");
      return 0;
    }
    TopoDS_Shape comp;
    std::string err;
    if (!mesh_to_solids(verts, nverts, tris, ntris, comp, err)) {
      set_err(err);
      return 0;
    }
    BRep_Builder builder;
    TopoDS_Compound out;
    builder.MakeCompound(out);
    int nsolid = 0;
    for (TopExp_Explorer ex(comp, TopAbs_SOLID); ex.More(); ex.Next()) {
      TopoDS_Shape shaped =
          fillet_solid(TopoDS::Solid(ex.Current()), radius, chamfer, err);
      if (shaped.IsNull()) {
        builder.Add(out, ex.Current());  // keep the body, unfilleted
        continue;
      }
      builder.Add(out, shaped);
      ++nsolid;
    }
    if (!nsolid) {
      set_err(err.empty() ? "nothing could be filleted" : err);
      return 0;
    }
    if (shape_to_obj(out, obj_out, err) < 0) {
      set_err(err);
      return 0;
    }
    return 1;
  } catch (const std::exception &e) {
    set_err(std::string("occt: ") + e.what());
    return 0;
  } catch (...) {
    set_err("occt: unknown exception during fillet");
    return 0;
  }
}

}  // extern "C"
