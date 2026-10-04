// Forma <-> OpenCascade bridge: STEP read/write over a triangle mesh.
//
// Deliberately tiny C ABI (dlopen-able from Python ctypes, no wrapped
// types). Forma's kernel guarantees watertight meshes, so export sews
// triangles into one solid; import re-tessellates a STEP shape to OBJ
// which trimesh/manifold3d consume on the Python side.
//
// Build: g++ -O2 -fPIC -shared -o occt_bridge.so occt_bridge.cpp \
//        -I/usr/include/opencascade -lTKernel -lTKBRep -lTKGeomBase \
//        -lTKMesh -lTKDESTEP -lTKXSBase

#include <BRep_Builder.hxx>
#include <BRep_Tool.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepBuilderAPI_MakePolygon.hxx>
#include <BRepBuilderAPI_Sewing.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <Interface_Static.hxx>
#include <Poly_Triangulation.hxx>
#include <Standard_Version.hxx>
#include <STEPControl_Reader.hxx>
#include <STEPControl_Writer.hxx>
#include <TopExp.hxx>
#include <TopExp_Explorer.hxx>
#include <TopLoc_Location.hxx>
#include <TopTools_IndexedDataMapOfShapeListOfShape.hxx>
#include <TopTools_ListOfShape.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shell.hxx>
#include <TopoDS_Solid.hxx>
#include <gp_Pln.hxx>
#include <gp_Pnt.hxx>

#include <cstdio>
#include <string>

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

extern "C" {

const char *occt_last_error() { return g_err.c_str(); }

int occt_version_major() { return OCC_VERSION_MAJOR; }

int step_export(const char *path, const double *verts, int nverts,
                const int *tris, int ntris) {
  try {
    BRepBuilderAPI_Sewing sewing(1e-5);
    int made = 0;
    for (int t = 0; t < ntris; ++t) {
      const int *ix = tris + 3 * t;
      if (ix[0] < 0 || ix[1] < 0 || ix[2] < 0 ||
          ix[0] >= nverts || ix[1] >= nverts || ix[2] >= nverts) {
        set_err("triangle index out of range");
        return 0;
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
      set_err("no usable triangles in mesh");
      return 0;
    }
    sewing.Perform();
    TopoDS_Shape sewn = sewing.SewedShape();
    // Every closed shell becomes a solid; a Forma document may legitimately
    // contain several disjoint bodies, so collect them all.
    BRep_Builder builder;
    TopoDS_Compound comp;
    builder.MakeCompound(comp);
    int nsolids = 0;
    for (TopExp_Explorer ex(sewn, TopAbs_SHELL); ex.More(); ex.Next()) {
      TopoDS_Shell shell = TopoDS::Shell(ex.Current());
      if (!shell_closed(shell))
        continue;  // open shell: not a body we can promise in STEP
      TopoDS_Solid solid;
      builder.MakeSolid(solid);
      builder.Add(solid, shell);
      solid.Orientation(TopAbs_FORWARD);
      builder.Add(comp, solid);
      ++nsolids;
    }
    if (!nsolids) {
      set_err("mesh did not form a closed solid (sewing failed)");
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
    BRepMesh_IncrementalMesh mesher(shape, 0.25, Standard_False, 0.35,
                                    Standard_True);
    mesher.Perform();
    if (!mesher.IsDone()) {
      set_err("tessellation of STEP shape failed");
      return 0;
    }
    FILE *f = std::fopen(obj_out, "wb");
    if (!f) {
      set_err("cannot open output OBJ");
      return 0;
    }
    long vbase = 0;
    long ntri = 0;
    std::fprintf(f, "# forma occt_bridge import\n");
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
    if (!ntri) {
      set_err("STEP shape tessellated to zero triangles");
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

}  // extern "C"
