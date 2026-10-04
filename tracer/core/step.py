"""STEP import/export through a small on-demand OpenCascade bridge.

Tracer Studio's own kernel is a mesh CSG (manifold3d), so STL/OBJ/3MF are native.
STEP is a boundary-rep format, so a ~200-line C++ bridge
(``core/native/occt_bridge.cpp``) talks to the *system* OpenCascade and is
compiled with the *system* g++ the first time STEP is used, then cached.

Nothing here is a hard dependency: machines without OCCT (or Windows,
where a different compiler dance is needed) get ``available() == False``
and the UI simply hides/dims the STEP actions.  That keeps Tracer Studio free to
build and run everywhere while still exchanging real CAD files on any
Linux box that has OpenCascade installed.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .geometry import Solid

_CPP = Path(__file__).parent / "native" / "occt_bridge.cpp"
_LIBS = ["TKDESTEP", "TKSTEP", "TKXSBase", "TKFillet", "TKMesh",
         "TKTopAlgo", "TKGeomAlgo", "TKGeomBase", "TKBRep", "TKernel",
         # fillet/chamfer pulls in boolean & feature ops; only linked if
         # present, and only reachable through the fillet entry point, so
         # a STEP-only OCCT install still loads.
         "TKBO", "TKBool", "TKFeat", "TKOffset", "TKMath"]

_cache: dict[str, object] = {}


@contextmanager
def _silenced():
    """OCCT prints transfer statistics on the C-level stdout."""
    fd_out, fd_err = sys.stdout.fileno(), sys.stderr.fileno()
    with open(os.devnull, "w") as devnull:
        save_out, save_err = os.dup(fd_out), os.dup(fd_err)
        try:
            os.dup2(devnull.fileno(), fd_out)
            os.dup2(devnull.fileno(), fd_err)
            yield
        finally:
            os.dup2(save_out, fd_out)
            os.dup2(save_err, fd_err)
            os.close(save_out)
            os.close(save_err)


def _find(flag: str, needle: str) -> str | None:
    """Probe pkg-config first, then common distro layouts."""
    exe = shutil.which("pkg-config")
    if exe:
        r = subprocess.run([exe, flag, needle], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            out = r.stdout.strip()
            if flag == "--cflags":           # "-I/usr/include/opencascade"
                out = out.split("-I")[-1].strip() if "-I" in out else out
            else:                            # "-L/usr/lib64 -lTKernel..."
                out = out.split("-L")[1].split()[0] if "-L" in out else ""
            if out:
                return out
    if flag == "--cflags":
        for cand in ("/usr/include/opencascade", "/usr/local/include/opencascade"):
            if Path(cand, "BRep_Builder.hxx").exists():
                return cand
    else:  # --libs
        for cand in ("/usr/lib64", "/usr/lib", "/usr/local/lib",
                     "/usr/lib/x86_64-linux-gnu"):
            if any(Path(cand).glob("libTKernel.so*")):
                return cand
    return None


def available() -> bool:
    """True when the bridge could plausibly compile on this machine."""
    if sys.platform.startswith("win"):        # MSVC route not wired yet
        return False
    return bool(shutil.which("g++") and _find("--cflags", "opencascade")
                and _find("--libs", "opencascade"))


def _probe_libdir() -> tuple[str, list[str]]:
    libdir = _find("--libs", "opencascade") or "/usr/lib64"
    libs = [n for n in _LIBS if any(Path(libdir).glob(f"lib{n}.so*"))]
    # link order: keep the original (upper-level first) order
    order = {n: i for i, n in enumerate(_LIBS)}
    libs.sort(key=lambda n: order[n])
    if "TKDESTEP" not in libs and "TKSTEP" not in libs:
        raise RuntimeError("OpenCascade STEP toolkit not found in " + libdir)
    return libdir, libs


def _bridge() -> ctypes.CDLL:
    lib = _cache.get("lib")
    if lib is not None:
        return lib
    gxx = shutil.which("g++")
    inc = _find("--cflags", "opencascade")
    if not gxx or not inc:
        raise RuntimeError("STEP needs a system OpenCascade + g++ "
                           "(on Arch: pacman -S opencascade")
    libdir, libs = _probe_libdir()
    src = _CPP.read_bytes()
    key = hashlib.sha1(src + inc.encode() + libdir.encode()).hexdigest()[:12]
    out_dir = Path(os.environ.get("XDG_CACHE_HOME",
                                  Path.home() / ".cache")) / "tracer"
    out_dir.mkdir(parents=True, exist_ok=True)
    so = out_dir / f"occt_bridge_{key}.so"
    if not so.exists():
        cmd = [gxx, "-O2", "-fPIC", "-shared", "-std=c++17", str(_CPP),
               "-o", str(so) + ".tmp", f"-I{inc}", f"-L{libdir}",
               f"-Wl,-rpath,{libdir}"] + [f"-l{n}" for n in libs]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("compiling the STEP bridge failed:\n"
                               + r.stderr[-2000:])
        os.replace(str(so) + ".tmp", so)
    lib = ctypes.CDLL(str(so))
    dp = ctypes.POINTER(ctypes.c_double)
    ip = ctypes.POINTER(ctypes.c_int)
    lib.step_export.argtypes = [ctypes.c_char_p, dp, ctypes.c_int,
                                ip, ctypes.c_int]
    lib.step_export.restype = ctypes.c_int
    lib.step_import.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.step_import.restype = ctypes.c_int
    lib.fillet_chamfer.argtypes = [ctypes.c_char_p, dp, ctypes.c_int,
                                   ip, ctypes.c_int, ctypes.c_double,
                                   ctypes.c_int]
    lib.fillet_chamfer.restype = ctypes.c_int
    lib.occt_last_error.restype = ctypes.c_char_p
    _cache["lib"] = lib
    return lib


def _err(lib: ctypes.CDLL) -> str:
    msg = lib.occt_last_error()
    return msg.decode(errors="replace") if msg else "unknown STEP error"


def _tri_arrays(solid: Solid):
    tm = solid.to_trimesh()
    v = tm.vertices.astype("float64", order="C")
    f = tm.faces.astype("int32", order="C")
    dp = ctypes.POINTER(ctypes.c_double)
    ip = ctypes.POINTER(ctypes.c_int)
    return (v.ctypes.data_as(dp), len(v), f.ctypes.data_as(ip), len(f))


def _solid_from_obj(obj_path: Path) -> Solid:
    import trimesh
    m = trimesh.load(str(obj_path), process=True, force="mesh")
    if not m.is_watertight:
        m.fill_holes()
    return Solid.from_mesh(m.vertices, m.faces)


def export_step(solid: Solid, path: str | Path) -> Path:
    """Write a boundary-rep STEP file for ``solid`` (mm units)."""
    lib = _bridge()
    vp, vn, fp, fn = _tri_arrays(solid)
    path = Path(path)
    with _silenced():
        ok = lib.step_export(os.fsencode(path), vp, vn, fp, fn)
    if not ok:
        raise RuntimeError(_err(lib))
    return path


def import_step(path: str | Path) -> Solid:
    """Read the first solids of a STEP file into a kernel Solid (mesh)."""
    lib = _bridge()
    with tempfile.TemporaryDirectory(prefix="tracer-step-") as td:
        obj = Path(td) / "imported.obj"
        with _silenced():
            ok = lib.step_import(os.fsencode(path), os.fsencode(obj))
        if not ok:
            raise RuntimeError(_err(lib))
        return _solid_from_obj(obj)


def fillet_mesh(solid: Solid, radius: float, chamfer: bool = False) -> Solid:
    """Round (or bevel) every sharp edge of ``solid`` at true 3D radius
    using OCCT's fillet algorithm; tangent/failed edges are skipped."""
    lib = _bridge()
    with tempfile.TemporaryDirectory(prefix="tracer-fillet-") as td:
        obj = Path(td) / "filleted.obj"
        vp, vn, fp, fn = _tri_arrays(solid)
        with _silenced():
            ok = lib.fillet_chamfer(os.fsencode(obj), vp, vn, fp, fn,
                                    float(radius), 1 if chamfer else 0)
        if not ok:
            raise RuntimeError(_err(lib))
        return _solid_from_obj(obj)


def backend_info() -> str:
    """Short human string for the Help/About: OCCT version when compiled."""
    try:
        lib = _bridge()
        return f"OpenCascade {lib.occt_version_major()}.x via g++"
    except Exception:
        return "not available on this system"
