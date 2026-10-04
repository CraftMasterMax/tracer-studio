"""moderngl scene renderer: gradient sky, ground grid with axes,
Blinn-Phong solid with screen-space antialiased edges (barycentric
trick). Renders to an FBO and hands back RGBA — one code path for the
live widget and for headless tests.
"""
from __future__ import annotations

import math

import numpy as np
import moderngl

from .camera import Camera
from .theme import DARK

_SOLID_VS = """
#version 330
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_bary;
in vec3 in_mask;
uniform mat4 u_view;
uniform mat4 u_proj;
out vec3 v_nrm;
out vec3 v_world;
out vec3 v_bary;
out vec3 v_mask;
void main() {
    v_world = in_pos;
    v_nrm = in_nrm;
    v_bary = in_bary;
    v_mask = in_mask;
    gl_Position = u_proj * u_view * vec4(in_pos, 1.0);
}
"""

_SOLID_FS = """
#version 330
in vec3 v_nrm;
in vec3 v_world;
in vec3 v_bary;
in vec3 v_mask;
uniform vec3 u_eye;
uniform vec3 u_base;
uniform vec3 u_edge_col;
uniform float u_edge_width;
uniform int u_show_edges;
out vec4 frag;

float edge_amount() {
    vec3 d = fwidth(v_bary) * u_edge_width;
    vec3 a = smoothstep(vec3(0.0), d, v_bary);
    a = mix(vec3(1.0), a, v_mask);   // non-crease triangulation edges vanish
    return 1.0 - min(min(a.x, a.y), a.z);
}

void main() {
    vec3 N = normalize(v_nrm);
    vec3 V = normalize(u_eye - v_world);
    vec3 L1 = normalize(vec3(0.35, 0.25, 1.0));           // key, warm-neutral
    vec3 L2 = normalize(vec3(-0.6, -0.4, 0.35));          // fill, cool
    float d1 = max(dot(N, L1), 0.0);
    float d2 = max(dot(N, L2), 0.0);
    vec3 H = normalize(L1 + V);
    float spec = pow(max(dot(N, H), 0.0), 56.0) * 0.35;
    vec3 hemi = mix(u_base * 0.45, u_base * 1.00, N.z * 0.5 + 0.5);
    vec3 col = hemi + u_base * d1 * 0.55 + u_base * d2 * vec3(0.10, 0.13, 0.18)
             + vec3(0.85, 0.90, 1.0) * spec;
    col += vec3(0.10, 0.14, 0.20) * pow(1.0 - max(dot(N, V), 0.0), 3.0);  // rim
    if (u_show_edges == 1) {
        float e = clamp(edge_amount(), 0.0, 1.0);
        col = mix(col, u_edge_col, e * 0.8);
    }
    frag = vec4(col, 1.0);
}
"""

_LINE_VS = """
#version 330
in vec3 in_pos;
in vec4 in_color;
uniform mat4 u_view;
uniform mat4 u_proj;
out vec4 v_color;
out vec3 v_world;
void main() {
    v_color = in_color;
    v_world = in_pos;
    gl_Position = u_proj * u_view * vec4(in_pos, 1.0);
}
"""

_LINE_FS = """
#version 330
in vec4 v_color;
in vec3 v_world;
uniform vec3 u_center;
uniform vec2 u_fade;
out vec4 frag;
void main() {
    float d = distance(v_world.xy, u_center.xy);
    float a = v_color.a * (1.0 - smoothstep(u_fade.x, u_fade.y, d));
    frag = vec4(v_color.rgb, a);
}
"""

_BG_VS = """
#version 330
out vec2 v_uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    v_uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 1.0, 1.0);
}
"""

_BG_FS = """
#version 330
in vec2 v_uv;
uniform vec3 u_top;
uniform vec3 u_bottom;
out vec4 frag;
void main() { frag = vec4(mix(u_bottom, u_top, v_uv.y), 1.0); }
"""

class SceneRenderer:
    def __init__(self, ctx: moderngl.BaseContext | None = None,
                 palette: dict = DARK, samples: int = 4):
        self.ctx = ctx or moderngl.create_standalone_context()
        self.palette = palette
        self._samples = samples
        c = self.ctx
        self._solid_prog = c.program(vertex_shader=_SOLID_VS, fragment_shader=_SOLID_FS)
        self._line_prog = c.program(vertex_shader=_LINE_VS, fragment_shader=_LINE_FS)
        self._bg_prog = c.program(vertex_shader=_BG_VS, fragment_shader=_BG_FS)
        self._bg_vao = c.vertex_array(self._bg_prog, [], mode=moderngl.TRIANGLES)
        self._solid_vao: moderngl.VertexArray | None = None
        self._solid_count = 0
        self._grid_vao: moderngl.VertexArray | None = None
        self._grid_count = 0
        self.show_grid = True
        self.show_edges = True
        self._grid_extent = 100.0
        self._size = (2, 2)
        self._fbo = None
        self._resolve = None
        self.resize(*self._size)

    # ---- resources ---------------------------------------------------------
    def resize(self, w: int, h: int):
        w, h = max(int(w), 2), max(int(h), 2)
        if (w, h) == self._size and self._fbo is not None:
            return
        self._release_fbo()
        self._size = (w, h)
        c = self.ctx
        self._msaa = self._samples >= 2
        if self._msaa:
            color = c.texture((w, h), 4, samples=self._samples)
            depth = c.depth_renderbuffer((w, h), samples=self._samples)
            self._fbo = c.framebuffer(color_attachments=[color], depth_attachment=depth)
            self._resolve = c.framebuffer(
                color_attachments=[c.texture((w, h), 4)],
                depth_attachment=c.depth_renderbuffer((w, h)))
        else:
            color = c.texture((w, h), 4)
            depth = c.depth_renderbuffer((w, h))
            self._fbo = c.framebuffer(color_attachments=[color], depth_attachment=depth)
            self._resolve = None

    def _release_fbo(self):
        if self._fbo:
            self._fbo.release()
            self._fbo = None
        if self._resolve:
            self._resolve.release()
            self._resolve = None

    def set_mesh(self, verts: np.ndarray, normals: np.ndarray, faces: np.ndarray):
        """Expand to unindexed triangles + barycentric attrs for edge AA.

        Only *feature* edges (dihedral angle > CREASE_DEG) and silhouette
        (boundary) edges get an edge mask; coplanar triangulation seams are
        suppressed so flat faces render clean.
        """
        import trimesh
        CREASE_DEG = 25.0
        mask = np.ones((len(faces), 3), np.float32)     # 1 = draw edge
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        adj = np.asarray(mesh.face_adjacency)
        ade = np.asarray(mesh.face_adjacency_edges)
        if len(adj):
            tn = np.asarray(mesh.face_normals)
            cosang = np.einsum("ij,ij->i", tn[adj[:, 0]], tn[adj[:, 1]])
            crease = cosang < math.cos(math.radians(CREASE_DEG))
            v_of_face = np.asarray(faces)
            for (f0, f1), (va, vb), cr in zip(adj, ade, crease):
                if cr:
                    continue
                for f_idx in (f0, f1):
                    vs = v_of_face[f_idx]
                    opp = int(next(v for v in range(3) if vs[v] not in (va, vb)))
                    mask[f_idx, opp] = 0.0

        idx = faces.reshape(-1)
        pos = verts[idx]
        nrm = normals[idx]
        n_tri = len(idx) // 3
        bary = np.tile(np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], np.float32),
                       (n_tri, 1))
        m_flat = mask.repeat(3, axis=0)   # constant across each face's 3 corners
        data = np.hstack([pos, nrm, bary, m_flat]).astype(np.float32)
        c = self.ctx
        if self._solid_vao is not None:
            self._solid_vao.release()
        buf = c.buffer(data.tobytes())
        self._solid_vao = c.vertex_array(
            self._solid_prog,
            [(buf, "3f 3f 3f 3f", "in_pos", "in_nrm", "in_bary", "in_mask")])
        self._solid_count = len(idx)

    def clear_mesh(self):
        if self._solid_vao is not None:
            self._solid_vao.release()
        self._solid_vao, self._solid_count = None, 0

    def set_grid(self, extent: float, minor: float):
        """XY ground grid at z=0 with highlighted axes."""
        e = float(extent)
        step = float(minor)
        n = int(e // step)
        lines: list[tuple] = []

        def add(p0, p1, rgba):
            lines.extend([(*p0, *rgba), (*p1, *rgba)])

        for i in range(-n, n + 1):
            k = i * step
            major = (i % 5 == 0)
            gm = self.palette["grid_major"]
            gmn = self.palette["grid_minor"]
            base = (*gm, 0.9) if major else (*gmn, 0.55)
            ax = self.palette["axis_y"] if i == 0 else None
            add((k, -e, 0), (k, e, 0), (*ax, 1.0) if ax else base)   # lines along Y
            ay = self.palette["axis_x"] if i == 0 else None
            add((-e, k, 0), (e, k, 0), (*ay, 1.0) if ay else base)   # lines along X
        arr = np.array(lines, np.float32)
        self._grid_extent = e
        c = self.ctx
        if self._grid_vao is not None:
            self._grid_vao.release()
        buf = c.buffer(arr.tobytes())
        self._grid_vao = c.vertex_array(self._line_prog, [(buf, "3f 4f", "in_pos", "in_color")])
        self._grid_count = len(arr)          # rows ARE vertices (7 floats each)

    def _grid_auto(self, bbox: np.ndarray):
        lo, hi = bbox
        diag = float(np.hypot(*(hi[:2] - lo[:2])))
        extent = max(60.0, diag * 1.6)
        for step in (0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500):
            if 2 * extent / step <= 60:
                break
        self.set_grid(extent, step)

    # ---- drawing --------------------------------------------------------------
    def render(self, camera: Camera, bbox: np.ndarray | None = None) -> np.ndarray:
        c = self.ctx
        w, h = self._size
        p = self.palette
        target = self._fbo
        target.use()
        c.enable(moderngl.DEPTH_TEST)
        c.viewport = (0, 0, w, h)
        # MUST clear every frame: stale depth from the previous render
        # otherwise kills all fragments at equal depths.
        c.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)
        # numpy matrices are row-major for M@v math; GLSL mat4 wants
        # column-major bytes, i.e. the transpose uploaded raw.
        view = np.ascontiguousarray(camera.view_matrix().T, "f4")
        proj = np.ascontiguousarray(camera.proj_matrix(w / h).T, "f4")

        # background: drawn first each frame on cleared depth, z far-plane,
        # so depth-test pass/fail ordering stays correct without glDepthMask
        # (not exposed by moderngl).
        c.disable(moderngl.DEPTH_TEST)
        self._bg_prog["u_top"].value = _hexrgb(p["sky_top"])
        self._bg_prog["u_bottom"].value = _hexrgb(p["sky_bottom"])
        self._bg_vao.render(moderngl.TRIANGLES, vertices=3)

        # grid
        if self.show_grid and self._grid_vao is not None:
            c.enable(moderngl.DEPTH_TEST)
            c.enable(moderngl.BLEND)
            self._line_prog["u_view"].write(view.tobytes())
            self._line_prog["u_proj"].write(proj.tobytes())
            self._line_prog["u_center"].value = tuple(float(t) for t in camera.target)
            self._line_prog["u_fade"].value = (self._grid_extent * 0.78,
                                               self._grid_extent * 1.02)
            self._grid_vao.render(moderngl.LINES, vertices=self._grid_count)
            c.disable(moderngl.BLEND)

        # solid
        if self._solid_vao is not None and self._solid_count:
            c.enable(moderngl.DEPTH_TEST)
            u = self._solid_prog
            u["u_view"].write(view.tobytes())
            u["u_proj"].write(proj.tobytes())
            u["u_eye"].value = tuple(np.asarray(camera.position, "f4"))
            u["u_base"].value = p["solid_base"]
            u["u_edge_col"].value = p["solid_edge"]
            u["u_edge_width"].value = 1.2
            u["u_show_edges"].value = 1 if self.show_edges else 0
            self._solid_vao.render(moderngl.TRIANGLES, vertices=self._solid_count)

        if self._msaa:
            c.disable(moderngl.DEPTH_TEST)
            c.copy_framebuffer(self._resolve, target)
            raw = self._resolve.read(components=4)
        else:
            raw = target.read(components=4)
        img = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
        return np.flipud(img).copy()          # GL bottom-up -> image top-down


def _hexrgb(hx: str):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
