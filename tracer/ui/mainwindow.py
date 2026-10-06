"""Application shell: menus, status bar, document <-> viewport wiring."""
from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np
import trimesh
from PySide6.QtCore import QSize, Qt, QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, 
                               QLabel, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)

from ..core import import2d
from ..core import export2d
from ..core import io as fio
from ..core import params
from ..core import printcheck
from ..core import step
from ..core.thread import ISO_COARSE
from ..core.document import (BodyFilletFeature, CircularPatternFeature,
                             CombineFeature,
                             Document, ExtrudeFeature, HoleFeature,
                             ImportedFeature, LinearPatternFeature,
                             LoftFeature, MirrorFeature, MoveFeature,
                             PathPatternFeature, RotateFeature,
                             PrimitiveFeature,
                             RevolveFeature, ShellFeature, SplitFeature,
                             SweepFeature,
                             ThreadFeature)
from ..core.measure import describe, face_stats, mass_properties
from ..core import units
from ..core.sketch.model import (SketchModel, face_basis, model_from_dict,
                                 model_to_dict, plane_uv)
from . import icons
from . import cmddialog
from .hole import HoleDialog
from .loft import LoftDialog
from .renderer import SceneRenderer
from .panels import LeftRail
from .ribbon import RibbonBar
from .shortcuts import TourDialog
from .sketcheditor import SketchCanvas
from .theme import DARK
from .timeline import TimelineHost
from .viewport import Viewport
from .cmddialog import Shell


def demo_document() -> Document:
    """Mounting bracket: plate + corner holes + boss + bore. Exercises
    every primitive path (profile extrude w/ holes, union, subtract)."""
    doc = Document("bracket-demo")
    doc.add_plate("base plate", 60, 40, 8,
                  holes=[(6, 6, 1.6), (54, 6, 1.6), (6, 34, 1.6), (54, 34, 1.6)])
    doc.add_cylinder("boss Ø14", radius=7, height=12, center=(30, 20),
                     z=8.0, op="union")
    doc.add_cylinder("bore Ø6", radius=3, height=30, center=(30, 20), op="subtract")
    return doc


class MainWindow(QMainWindow):
    _MATERIAL_DENSITIES = [        # label carries g/cm³ (parsed back)
        "PLA (1.24)", "PETG (1.27)", "ABS (1.04)", "Nylon (1.14)",
        "TPU (1.20)", "Resin (1.10)", "Water (1.00)", "Aluminium (2.70)",
        "Steel (7.85)", "Stainless (8.00)", "Brass (8.50)",
        "Titanium (4.50)", "Copper (8.96)",
    ]

    def __init__(self, renderer: SceneRenderer | None = None):
        super().__init__()
        self.setWindowTitle("Tracer Studio")
        self.resize(1280, 800)
        self.doc: Document | None = None
        self.file_path: Path | None = None
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._renderer = renderer or SceneRenderer()
        self.viewport = Viewport(self._renderer)
        self.rail = LeftRail()
        self.rail.tree.currentItemChanged.connect(
            lambda *_: self.rail.props.show_feature(self.rail.tree.current_feature()))
        self.rail.tree.itemDoubleClicked.connect(self._tree_activated)
        self.rail.tree.feature_menu.connect(self._feature_menu)
        self.rail.tree.cplane_menu.connect(self._cplane_menu)
        self.rail.tree.body_menu.connect(self._body_menu)
        self.rail.tree.feature_delete.connect(self._delete_feature)
        self.rail.tree.feature_rename.connect(self._rename_feature)
        self.viewport.zoom_selection.connect(self._zoom_to_selection)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.rail)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.viewport)
        self._sketch_page = self._make_sketch_page()
        self.stack.addWidget(self._sketch_page)
        self._drawing_page = self._make_drawing_page()   # M93 sheet
        self.stack.addWidget(self._drawing_page)
        split.addWidget(self.stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 1000])
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(split, 1)
        self.timeline = TimelineHost()
        self.timeline.bar.feature_activated.connect(self._feature_activated)
        self.timeline.bar.feature_menu.connect(self._feature_menu)
        self.timeline.bar.rollback_changed.connect(self._apply_rollback)
        self.timeline.bar.feature_delete.connect(self._delete_feature)
        self.timeline.bar.home_clicked.connect(self.viewport.home)
        self.viewport.face_picked.connect(self._start_sketch_on_face)
        self.viewport.coords.connect(self._show_coords)
        self.viewport.press_pull.connect(self._press_pull)
        self.viewport.move_drag.connect(self._on_move_drag)
        self.viewport.rotate_drag.connect(self._on_rotate_drag)
        self.viewport.context_request.connect(self._show_marking_menu)
        self.viewport.zoom_window.connect(self._on_zoom_window)
        self._mark_menu = None               # open marking menu (M56)
        self._move_origin = None             # armed Move gesture (M53)
        self._move_len = 40.0
        self._rotate_center = None           # armed Rotate (M55)
        self._rotate_radius = 40.0
        self.viewport.selection_changed.connect(self._on_face_selection)
        cl.addWidget(self.timeline)
        self.setCentralWidget(center)

        self._make_actions()
        self._make_toolbar()
        self.status = self.statusBar()
        self._coords = QLabel("x 0.00   y 0.00   z 0.00")
        self._coords.setObjectName("dim")
        self._coords.setMinimumWidth(170)
        self._coords.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status.addPermanentWidget(self._coords)
        self.status.showMessage("Ready — F fit · G grid · E edges · 0/1/2/3 views")
        self.new_document(demo_document())

    def _show_coords(self, pt):
        if pt is None:
            self._coords.setText("x —   y —   z —")
        else:
            self._coords.setText(f"x {pt[0]:.2f}   y {pt[1]:.2f}   "
                                 f"z {pt[2]:.2f}")

    # ---- Press-Pull (drag a face to add/remove material) -------------------
    def _press_pull(self, d: dict):
        if "cancel" in d:
            self._pp_cache = None
            self.viewport.preview_mesh(None)
            self.status.showMessage("Press-Pull cancelled", 3000)
            return
        if d.get("live"):
            self.status.showMessage(
                f"Press-Pull: {d['offset']:+.2f} mm   "
                "(release to apply, Esc to cancel)")
            self._press_pull_preview(d)
            return
        self._pp_cache = None
        self._apply_press_pull(d)

    def _press_pull_preview(self, d: dict):
        """Deform the viewport mesh while dragging, the way Fusion does.
        The face region is computed once per drag; every move re-runs the
        prism boolean (single-digit ms on maker parts), throttled to ~20fps.
        Purely cosmetic — the committed feature is rebuilt on release."""
        import time
        if self.doc is None or self.doc.result is None:
            return
        cached = getattr(self, "_pp_cache", None)
        if cached is None or cached[0] is not d.get("ppid"):
            from ..core.presspull import face_region
            v, _n, f = self.doc.result.to_render_arrays()
            mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
            try:
                reg = face_region(mesh, d["faces"])
            except Exception:
                reg = None
            cached = self._pp_cache = (d.get("ppid"), reg,
                                       self.doc.result, 0.0)
        pid, reg, base, t_last = cached
        if reg is None:
            return
        now = time.monotonic()
        if now - t_last < 0.045:
            return
        self._pp_cache = (pid, reg, base, now)
        off = float(d["offset"])
        pull = off >= 0
        u, vn = reg["u"], reg["v"]
        axes = ([u.tolist(), vn.tolist()] if pull
                else [[-float(x) for x in u], vn.tolist()])
        feat = ExtrudeFeature(name="_preview", outer=reg["outer"],
                              holes=reg["holes"], height=max(abs(off), 0.005),
                              plane="FACE", axes=axes,
                              placement=tuple(reg["point"]),
                              op="union" if pull else "subtract")
        try:
            prism = feat.build()
            solid = base.union(prism) if pull else base.subtract(prism)
        except Exception:
            return
        self.viewport.preview_mesh(solid)

    def _apply_press_pull(self, d: dict):
        off = float(d["offset"])
        if abs(off) < 0.05:
            self.viewport.preview_mesh(None)
            self.status.clearMessage()
            return
        if self.doc is None or self.doc.result is None:
            return
        from ..core.presspull import face_region
        solid = self.doc.result
        v, _n, f = solid.to_render_arrays()          # viewport's index space
        faces = np.asarray(d["faces"], int)
        if faces.size == 0 or int(faces.max()) >= len(f):
            self.viewport.preview_mesh(None)         # doc changed mid-drag
            self.status.showMessage("Press-Pull: stale selection — "
                                    "grab the face again", 4000)
            return
        mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)
        reg = face_region(mesh, faces)
        if reg is None:
            self.status.showMessage(
                "Press-Pull works on flat faces — select a plane and drag",
                5000)
            return
        u, vn, n = reg["u"], reg["v"], reg["normal"]
        pull = off > 0
        # union grows the prism out along +n; subtract pushes it into the
        # material (flip an axis so plane_matrix extrudes along −n).
        axes = [u.tolist(), vn.tolist()] if pull else [[-u[0], -u[1], -u[2]],
                                                        vn.tolist()]
        idx = sum(isinstance(x, ExtrudeFeature) and x.name.startswith("PressPull")
                  for x in self.doc.features) + 1
        feat = ExtrudeFeature(
            name=f"PressPull{idx}", op="union" if pull else "subtract",
            outer=reg["outer"], holes=reg["holes"], height=abs(off),
            plane="FACE", axes=axes, placement=tuple(reg["point"]),
            sketch=None, region=0)
        self._capture()
        self.doc.add(feat)
        try:
            self.doc.recompute()               # not the dialog wrapper:
        except Exception:                      # a bad press-pull must undo
            self.undo()                        # silently
            self.status.showMessage("Press-Pull failed — geometry rejected",
                                    5000)
            return
        self.viewport.refresh()
        self.rail.tree.reload()
        self.timeline.bar.update()
        self._update_status()
        verb = "added" if pull else "removed"
        self.status.showMessage(
            f"Press-Pull {verb} {feat.name}: {abs(off):+.2f} mm", 5000)

    # ---- quick toolbar (Fusion-style icon strip under the menus) ----------
    def _make_toolbar(self):
        """Fusion ribbon: quick-access strip, Design/Sketch tabs, grouped
        panels.  Tooltip contracts from M20 stay honored: the sketch
        button fires on click; extrude & fillet buttons carry dropdown
        menus whose first entry is the headline operation."""
        tb = QToolBar("Tools", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setStyleSheet(f"QToolBar {{ background: {DARK['bg0']};"
                         f" border: none; padding: 0; }}")
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, tb)
        r = self.ribbon = RibbonBar(tb)
        tb.addWidget(r)
        r.tab_clicked.connect(self._ribbon_tab)

        qa = r.quick_button
        qa("new", "New (Ctrl+N)", self.act_new.trigger)
        qa("open", "Open… (Ctrl+O)", self.act_open.trigger)
        qa("save", "Save (Ctrl+S)", self.act_save.trigger)
        qa("undo", "Undo (Ctrl+Z)", self.act_undo.trigger)
        qa("redo", "Redo (Ctrl+Shift+Z)", self.act_redo.trigger)

        d = r.design_tool
        d("sketch", "New sketch (N)",
          lambda checked=False: self.action_new_sketch())
        r.design_sep()
        d("extrude", "Extrude — sweep a sketch profile into a solid",
          menu_actions=[
              ("E&xtrude profile… (X)", self._tb_extrude),
              ("&Revolve profile… (⇧R)", self._tb_revolve),
              ("&Hole… (Ctrl+H)", self.action_hole),
              ("S&weep… (W)", self.action_sweep),
              ("&Loft… (Ctrl+L)", self.action_loft)])
        d("sweep", "Sweep — pipe the sketch's circle along its path (W)",
          lambda checked=False: self.action_sweep())
        d("loft", "Loft — blend one sketch's profile into another's (Ctrl+L)",
          lambda checked=False: self.action_loft())
        d("primitive", "Primitive — drop a box, cone, cylinder, sphere "
                       "or torus",
          lambda checked=False: self.action_primitive())
        d("text", "Text — emboss or engrave a line of text",
          lambda checked=False: self.action_text())
        d("hole", "Hole — drill every sketch circle (Ctrl+H)",
          lambda checked=False: self.action_hole())
        r.design_sep()
        d("pattern", "Rectangular pattern — grid-copy a feature",
          lambda checked=False: self.action_linear_pattern())
        d("cpattern", "Circular pattern — polar-copy a feature",
          lambda checked=False: self.action_circular_pattern())
        d("mirror", "Mirror — flip a feature across a plane or axis",
          lambda checked=False: self.action_mirror())
        d("ppattern", "Pattern on path — copies walking a sketch path",
          lambda checked=False: self.action_path_pattern())
        r.design_sep()
        d("fillet", "Fillet — round every sharp edge of the body",
          menu_actions=[self.act_fillet, self.act_chamfer, self.act_shell])
        d("shell", "Shell — hollow the body, open top face removed",
          lambda checked=False: self.action_shell())
        d("thread", "Thread — cut a bolt thread on a cylindrical boss face",
          lambda checked=False: self.action_thread())
        d("split", "Split body — trim the solid flush with a plane",
          lambda checked=False: self.action_split_body())
        d("move", "Move body — drag the triad to slide it (Ctrl = copy)",
          lambda checked=False: self.action_move_body())
        d("rotate", "Rotate body — drag a ring to spin it (Ctrl = copy)",
          lambda checked=False: self.action_rotate_body())
        d("combine", "Combine body — Join / Cut / Intersect a placed "
          "solid", lambda checked=False: self.action_combine())
        r.design_sep()
        d("plane", "Construction plane — offset work plane (Ctrl+Shift+P)",
          lambda checked=False: self.action_construction_plane())
        d("section", "Section analysis — clip the body on a plane",
          menu_actions=[
              ("Section on XY plane",
               lambda checked=False: self.action_section("XY")),
              ("Section on XZ plane",
               lambda checked=False: self.action_section("XZ")),
              ("Section on YZ plane",
               lambda checked=False: self.action_section("YZ")),
              ("Flip clipped side", self.action_flip_section),
              ("Turn section off",
               lambda checked=False: self.action_section(None))])
        d("appearance", "Appearance — paint the body with a material",
          lambda checked=False: self.action_appearance())
        d("mass", "Mass properties — volume, area, mass, centre of mass",
          lambda checked=False: self.action_mass_properties())

        s = r.sketch_tool
        for glyph, tip, tool in (
                ("rect", "Rectangle (R)", "rect"),
                ("line", "Line (L)", "line"),
                ("circle", "Circle (C)", "circle"),
                ("slot", "Slot (O)", "slot"),
                ("poly", "Polygon (Y)", "poly"),
                ("arc", "Arc (A)", "arc")):
            s(glyph, tip,
              lambda checked=False, t=tool: self.sketch.set_tool(t))
        r.sketch_sep()
        s("trim", "Trim — close a corner between two selected lines (/)",
          lambda checked=False: self.sketch.act_trim())
        s("offset", "Offset — parallel copies of selected lines (U)",
          lambda checked=False: self.sketch.act_offset())
        s("construction", "Construction — toggle selected geometry (K)",
          lambda checked=False: self.sketch.act_construction())
        r.sketch_sep()
        s("dimension", "Dimension — distance or radius with a value (D)",
          lambda checked=False: self.sketch.act_dim())
        r.sketch_sep()
        f = r.sketch_flyout
        f("constrain", "Geometric constraints — pick a tie (keys shown)", [
            ("Horizontal", "H", lambda: self.sketch.act_H()),
            ("Vertical", "V", lambda: self.sketch.act_V()),
            ("Perpendicular", "P", lambda: self.sketch.act_perp()),
            ("Equal", "Q", lambda: self.sketch.act_equal()),
            ("Collinear", "L", lambda: self.sketch.act_collinear()),
            ("Midpoint", "J", lambda: self.sketch.act_midpoint()),
            ("Symmetry", "M", lambda: self.sketch.act_symmetry()),
            ("Concentric", "2", lambda: self.sketch.act_concentric()),
            ("Tangent", "T", lambda: self.sketch.act_tangent()),
            ("On-curve", ".", lambda: self.sketch.act_on()),
            ("Angle", "I", lambda: self.sketch.act_angle()),
            ("Fix", "F", lambda: self.sketch.act_fix())])
        r.sketch_sep()
        s("extrude", "Finish — extrude the profile (X)",
          self._tb_extrude,
          menu_actions=[("Revolve profile… (⇧R)", self._tb_revolve),
                        ("Hole… (Ctrl+H)", self.action_hole),
                        ("Sweep… (W)", self.action_sweep),
                        ("Loft… (Ctrl+L)", self.action_loft)])

        # app-launcher menu: Fusion's top-left file surface, sharing the
        # very QActions from the menu bar so shortcuts/ids stay identical
        lm = QMenu(self)
        lm.setObjectName("launcherMenu")
        lm.addActions([self.act_new, self.act_open, self.act_save,
                       self.act_save_as])
        lm.addSeparator()
        lm.addAction(self.act_import)
        lme = lm.addMenu("E&xport")
        for a in self._export_acts:
            lme.addAction(a)
        lme.addSeparator()
        lme.addAction(self.act_export_step_a)
        lme.addAction(self.act_export_render_a)
        lm.addSeparator()
        lm.addAction(QAction("Keyboard &shortcuts", self,
                             triggered=self.show_shortcuts))
        lm.addSeparator()
        lm.addAction(self.act_exit)
        r.launcher.setMenu(lm)

    def _ribbon_tab(self, index: int):
        """Design tab = leave to the model page (same path as the sketch
        page's Back button); Sketch tab = start a sketch if none is open."""
        if index == 0:
            if self.stack.currentWidget() is not self.viewport:
                self._show_page(self.viewport)
        elif self.stack.currentWidget() is not self._sketch_page:
            self.action_new_sketch()

    def _tb_extrude(self, checked=False):
        """Fusion flow: Extrude wants a profile. On the sketch page it
        finishes the sketch; in the model it starts one and hints."""
        if self.stack.currentWidget() is not self.viewport:
            self.sketch.finish()
            return
        self.action_new_sketch()
        self.status.showMessage("Draw a closed profile, then press X to "
                                "extrude", 5000)

    def _tb_revolve(self, checked=False):
        if self.stack.currentWidget() is not self.viewport:
            self.sketch.finish(revolve=True)
            return
        self.action_new_sketch()
        self.status.showMessage("Draw a profile beside the axis, then press "
                                "⇧R to revolve", 5000)

    # ---- actions -----------------------------------------------------------
    def _make_actions(self):
        m_file = self.menuBar().addMenu("&File")
        self.act_new = QAction("&New", self, shortcut=QKeySequence.New,
                               triggered=self.action_new)
        self.act_save = QAction("&Save", self, shortcut=QKeySequence.Save,
                                triggered=self.action_save)
        self.act_save_as = QAction("Save &As…", self,
                                   shortcut=QKeySequence.SaveAs,
                                   triggered=lambda: self.action_save(as_new=True))
        self.act_open = QAction("&Open…", self, shortcut=QKeySequence.Open,
                                triggered=self.action_open)
        self.act_import = QAction("&Import body…", self,
                                  triggered=self.action_import)
        m_file.addActions([self.act_new, self.act_open])
        self.m_recent = m_file.addMenu("Recent Files")
        self._rebuild_recents()
        m_file.addActions([self.act_save, self.act_save_as])
        m_file.addSeparator()
        m_file.addAction(self.act_import)
        self.act_import_profile = QAction(
            "Import profile (DXF/S&VG)…", self,
            triggered=lambda checked=False: self.action_import_profile())
        m_file.addAction(self.act_import_profile)
        # export actions are members: the ribbon launcher menu shares them
        # (menus can't be shared, actions happily can)
        self._export_acts = [
            QAction(ext.upper().lstrip("."), self,
                    triggered=lambda checked=False, e=ext: self.action_export(e))
            for ext in (".stl", ".3mf", ".obj", ".ply")]
        self.act_export_step_a = QAction("Export &STEP (.step)…", self,
                                         triggered=self.action_export_step)
        self.act_export_profile_a = QAction(
            "Export &profile (DXF/SVG)", self,
            triggered=lambda checked=False: self.action_export_profile())
        self.act_export_render_a = QAction(
            "Export &render (PNG)…", self,
            triggered=lambda checked=False: self.action_export_render())
        m_export = m_file.addMenu("&Export mesh")
        for a in self._export_acts:
            m_export.addAction(a)
        m_file.addAction(self.act_export_step_a)
        m_file.addAction(self.act_export_profile_a)
        m_file.addSeparator()
        m_file.addAction(self.act_export_render_a)
        m_file.addSeparator()
        self.act_exit = QAction("E&xit", self, shortcut=QKeySequence.Quit,
                                triggered=self.close)
        m_file.addAction(self.act_exit)

        m_sk = self.menuBar().addMenu("S&ketch")
        self.act_new_sketch = QAction("&New sketch", self, shortcut="N",
                                      triggered=lambda checked=False: self.action_new_sketch())
        self.act_extrude = QAction("&Extrude profile…", self, shortcut="X",
                                   triggered=lambda: self.sketch.finish())
        self.act_revolve = QAction("&Revolve profile…", self, shortcut="Shift+R",
                                   triggered=lambda: self.sketch.finish(revolve=True))
        self.act_hole = QAction("&Hole…", self, shortcut="Ctrl+H",
                                triggered=lambda checked=False: self.action_hole())
        self.act_sweep = QAction("S&weep…", self, shortcut="W",
                                 triggered=lambda checked=False: self.action_sweep())
        self.act_loft = QAction("&Loft…", self, shortcut="Ctrl+L",
                                triggered=lambda checked=False: self.action_loft())
        self.act_plane = QAction("Construction &plane…", self,
                                 shortcut="Ctrl+Shift+P",
                                 triggered=lambda checked=False:
                                 self.action_construction_plane())
        m_sk.addActions([self.act_new_sketch, self.act_extrude,
                         self.act_revolve, self.act_hole, self.act_sweep,
                         self.act_loft, self.act_plane])

        m_cr = self.menuBar().addMenu("C&reate")
        self.act_linpat = QAction("&Linear pattern…", self,
                                  triggered=lambda checked=False: self.action_linear_pattern())
        self.act_cirpat = QAction("C&ircular pattern…", self,
                                  triggered=lambda checked=False: self.action_circular_pattern())
        self.act_mirror = QAction("&Mirror…", self,
                                  triggered=lambda checked=False: self.action_mirror())
        m_cr.addActions([self.act_linpat, self.act_cirpat, self.act_mirror])
        m_cr.addSeparator()
        m_cr.addAction("New drawing…",
                       lambda checked=False: self.action_new_drawing())

        m_mo = self.menuBar().addMenu("Mo&dify")
        self.act_fillet = QAction("&Fillet body edges…", self,
                                  triggered=lambda checked=False: self._body_fillet(False))
        self.act_chamfer = QAction("C&hamfer body edges…", self,
                                   triggered=lambda checked=False: self._body_fillet(True))
        self.act_shell = QAction("&Shell…", self,
                                 triggered=lambda checked=False: self.action_shell())
        m_mo.addActions([self.act_fillet, self.act_chamfer, self.act_shell])
        m_mo.addSeparator()
        m_mo.addAction("Change Parameters…",
                       lambda checked=False: self.action_change_params())
        m_mo.addAction("User Parameters…", self.action_user_parameters)
        m_mo.addAction("Configurations…", self.action_configurations)
        m_mo.addAction("Move body…",
                       lambda checked=False: self.action_move_body())
        m_mo.addAction("Rotate body…",
                       lambda checked=False: self.action_rotate_body())

        m_edit = self.menuBar().addMenu("&Edit")
        self.act_undo = QAction("&Undo", self, shortcut=QKeySequence.Undo,
                                triggered=self.undo)
        self.act_redo = QAction("&Redo", self, shortcut="Ctrl+Shift+Z",
                                triggered=self.redo)
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)

        m_view = self.menuBar().addMenu("&View")
        view_acts = []
        for label, key, view in (("Front", "1", "front"), ("Top", "2", "top"),
                                 ("Right", "3", "right"), ("Isometric", "0", "iso"),
                                 ("Fit view", "F", "fit")):
            a = QAction(label, self, shortcut=key,
                        triggered=lambda checked=False, v=view: self.action_view(v))
            m_view.addAction(a)
            view_acts.append(a)
        m_view.addSeparator()
        self.act_grid = QAction("Toggle grid", self, shortcut="G",
                                triggered=self.action_toggle_grid)
        self.act_edges = QAction("Toggle edges", self, shortcut="E",
                                 triggered=self.action_toggle_edges)
        m_view.addAction(self.act_grid)
        m_view.addAction(self.act_edges)
        m_vs = m_view.addMenu("Visual Styles")
        for _label in ("Wireframe", "Ghosted", "Shaded",
                       "Shaded with edges", "X-ray"):
            m_vs.addAction(
                _label, lambda checked=False, lb=_label:
                self.action_visual_style(lb))

        m_tools = self.menuBar().addMenu("&Tools")
        m_tools.addAction("Document Measures…",
                          lambda checked=False:
                          self.action_document_measures())
        m_tools.addAction("Mass properties…",
                          lambda checked=False:
                          self.action_mass_properties())
        m_tools.addAction("3D Print…",
                          lambda checked=False: self.action_3d_print())
        m_tools.addAction("Configurations…",
                          lambda checked=False: self.action_configurations())

        m_help = self.menuBar().addMenu("&Help")
        self.act_tour = QAction("&Welcome tour", self,
                                triggered=lambda checked=False: self.show_tour())
        self.act_keys = QAction("&Keyboard shortcuts", self, shortcut="?",
                                triggered=lambda checked=False: self.show_shortcuts())
        m_help.addActions([self.act_tour, self.act_keys])

        # While sketching, single-key view shortcuts (F fit, G grid, E edges)
        # would eat the sketcher's constraint keys — a real-desktop bug that
        # offscreen tests never see. Disabled actions don't match shortcuts.
        self._sketch_conflicts = [self.act_undo, self.act_redo,
                                  self.act_grid, self.act_edges, *view_acts]

    def _show_page(self, page):
        self.stack.setCurrentWidget(page)
        if hasattr(self, "ribbon"):
            self.ribbon.set_current(1 if page is self._sketch_page else 0)
        for a in getattr(self, "_sketch_conflicts", []):
            a.setEnabled(page is not self._sketch_page)

    # ---- help: tour + shortcut sheet ---------------------------------------
    def show_shortcuts(self):
        """Reveal the dedicated Shortcuts tab in the left rail."""
        self.rail.show_shortcuts()
        self.status.showMessage("Keyboard shortcuts — Help ▸ Welcome tour to replay")

    def show_tour(self):
        """First-run (or on-demand) guided tour of the key shortcuts."""
        dlg = TourDialog(self)
        dlg.btn_sheet.clicked.connect(dlg.accept)
        dlg.btn_sheet.clicked.connect(self.show_shortcuts)
        dlg.exec()

    def maybe_show_tour(self):
        """Show the tour once per install (remembered via QSettings)."""
        if QSettings().value("ui/tour_shown", False, type=bool):
            return False
        QSettings().setValue("ui/tour_shown", True)
        self.show_tour()
        return True

    # ---- sketching: new, finish (associative extrude), re-edit ---------------
    def _tree_activated(self, item, col):
        role = item.data(0, Qt.UserRole) if item else None
        if not role:
            return
        kind, arg = role
        if kind == "plane":
            self.action_new_sketch(arg)
        elif kind == "cplane":
            self.action_sketch_on_plane(arg)
        elif kind == "sketch":
            self._feature_activated(self.doc.features[arg])
        elif kind == "sheet":                 # M96: double-click a sheet
            self._open_drawing(arg)

    def _feature_activated(self, feature):
        if (isinstance(feature, (ExtrudeFeature, RevolveFeature, HoleFeature))
                and feature.sketch):
            self.edit_sketch(feature)
        elif isinstance(feature, BodyFilletFeature):
            self._set_fillet_size(feature)      # reopen the size dialog
        elif isinstance(feature, ExtrudeFeature):
            self._set_distance(feature)         # e.g. Press-Pull: no sketch
        else:
            self.status.showMessage("Feature has no editable sketch (yet)", 3000)

    # ---- feature management (context menus: timeline + browser) --------------
    def _feature_menu(self, feature, pos):
        menu = QMenu(self)
        sketchy = (isinstance(feature, (ExtrudeFeature, RevolveFeature,
                                        HoleFeature))
                   and feature.sketch)
        if sketchy:
            menu.addAction("Edit sketch", lambda: self.edit_sketch(feature))
        if isinstance(feature, ExtrudeFeature):
            menu.addAction("Set extrude distance…",
                           lambda: self._set_distance(feature))
            menu.addAction("Fillet vertical edges…",
                           lambda: self._set_corner(feature, "fillet"))
            menu.addAction("Chamfer vertical edges…",
                           lambda: self._set_corner(feature, "chamfer"))
        if isinstance(feature, RevolveFeature):
            menu.addAction("Set revolve angle…",
                           lambda: self._set_angle(feature))
        if isinstance(feature, BodyFilletFeature):
            menu.addAction("Set chamfer distance…" if feature.chamfer
                           else "Set fillet radius…",
                           lambda: self._set_fillet_size(feature))
        base = self._is_base_feature(feature)
        if isinstance(feature, (ExtrudeFeature, RevolveFeature,
                                PrimitiveFeature)):
            op_menu = menu.addMenu("Boolean operation")
            for label, op in (("Join (union)", "union"),
                              ("Cut (subtract)", "subtract"),
                              ("Intersect", "intersect")):
                act = op_menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(feature.op == op)
                act.setEnabled(not base or op == "union")
                act.triggered.connect(
                    lambda checked=False, o=op: self._set_operation(feature, o))
        if not isinstance(feature, BodyFilletFeature):
            # a body-replacing op has no solid of its own to twin
            mir_menu = menu.addMenu("Mirror copy")
            for pl, hint in (("YZ", "X\u2192\u2212X"), ("XZ", "Y\u2192\u2212Y"),
                             ("XY", "Z\u2192\u2212Z")):
                mir_menu.addAction(f"across {pl} ({hint})",
                                   lambda checked=False, p=pl:
                                   self._mirror_feature(feature, p))
        if self._feature_params(feature):
            menu.addAction("Change Parameters…",
                           lambda: self.action_change_params(feature))
        menu.addAction("User Parameters…", self.action_user_parameters)
        menu.addAction("Rename…", lambda: self._rename_feature(feature))
        menu.addSeparator()
        menu.addAction("Unsuppress" if feature.suppressed else "Suppress",
                       lambda: self._toggle_suppress(feature))
        menu.addAction("Rollback to here",
                       lambda: self._rollback_to(feature))
        if self.doc is not None and self.doc.rollback_to is not None:
            menu.addAction("End rollback",
                           lambda: self._apply_rollback(None))
        menu.addAction("Delete feature", lambda: self._delete_feature(feature))
        menu.exec(pos)

    def _is_base_feature(self, feature) -> bool:
        """True if nothing before it adds material — the base cannot Cut."""
        for f in self.doc.features:
            if f is feature:
                return True
            if not f.suppressed:
                return False
        return True

    def _set_operation(self, feature, op: str):
        if feature.op == op:
            return
        if op != "union" and self._is_base_feature(feature):
            self.status.showMessage(
                "The first feature must add material — later features can "
                "Cut or Intersect it", 5000)
            return
        self._capture()
        feature.op = op
        self.doc.dirty = True
        self.recompute()
        self.viewport.refresh()
        label = {"union": "Join", "subtract": "Cut",
                 "intersect": "Intersect"}[op]
        self.status.showMessage(f"{feature.name}: {label}", 4000)

    def _rollback_to(self, feature):
        """Fusion's rollback rubber band: the band lands right AFTER
        this feature — everything downstream hides; on the last chip
        rolling back means ending it."""
        if self.doc is None or feature not in self.doc.features:
            return
        idx = self.doc.features.index(feature)
        self._apply_rollback(idx + 1)

    def _apply_rollback(self, n):
        """Move (or end, for None / past-the-end) the rubber band and
        show the partial history.  View state: never serialized."""
        if self.doc is None:
            return
        total = len(self.doc.features)
        if n is None or n >= total:
            self.doc.rollback_to = None
            msg = (f"Rollback ended — showing all {total} feature"
                   + ("" if total == 1 else "s"))
        else:
            self.doc.rollback_to = max(0, int(n))
            msg = f"Rollback: showing {self.doc.rollback_to} of {total}"
        self.recompute()
        self.status.showMessage(msg, 4000)

    def _toggle_suppress(self, feature):
        self._capture()
        feature.suppressed = not feature.suppressed
        self.doc.dirty = True
        self.recompute()
        verb = "Suppressed" if feature.suppressed else "Unsuppressed"
        self.status.showMessage(f"{verb} {feature.name}", 4000)

    def _set_distance(self, feature):
        val, ok = Shell.getDouble(self, "Extrude distance",
                                         "Height (mm):", feature.height,
                                         0.01, 1e5, 3)
        if not ok or abs(val - feature.height) < 1e-12:
            return
        self._capture()
        feature.height = float(val)
        self.doc.dirty = True
        self.recompute()
        self.status.showMessage(f"{feature.name}: height {val:g} mm", 4000)

    # ---- Change Parameters (M61) ---------------------------------------------
    def _feature_params(self, feature):
        """Fusion's Change Parameters (M61): the numeric levers a feature
        is built from, expressed in document measures (mm stays the
        stored truth).  Returns cmddialog field specs — empty for
        features whose geometry is captured data (loft/sweep/sketch)."""
        u = self.doc.units if self.doc else "mm"
        sc = units.PER_MM[u]
        lab = units.LABEL[u]
        fld = []

        def dbl(key, label, mm, dec=2, mn=0.0, ang=False):
            spec = dict(key=key, kind="double", decimals=dec,
                        label=f"{label} ({'\u00b0' if ang else lab})")
            spec["default"] = float(mm) if ang else round(mm / sc, 6)
            if mn is not None:
                spec["min"] = mn if ang else mn / sc
            fld.append(spec)

        def ints(key, label, val, mn=2):
            fld.append(dict(key=key, label=label, kind="int",
                            default=int(val), min=mn))

        def combo(key, label, choices, cur):
            fld.append(dict(key=key, label=label, kind="combo",
                            choices=list(choices), default=cur))

        def check(key, label, val):
            fld.append(dict(key=key, label=label, kind="check",
                            default=bool(val)))

        if isinstance(feature, PrimitiveFeature):
            d = feature.dims
            if feature.kind == "box":
                dbl("dx", "length X", d["dx"])
                dbl("dy", "length Y", d["dy"])
                dbl("dz", "length Z", d["dz"])
            elif feature.kind == "cylinder":
                dbl("radius", "radius", d["radius"])
                dbl("height", "height", d["height"])
            elif feature.kind == "cone":
                dbl("r1", "bottom radius", d["radius_bottom"])
                dbl("r2", "top radius", d["radius_top"], mn=0.0)
                dbl("height", "height", d["height"])
            elif feature.kind == "torus":
                dbl("major", "ring radius", d["major"], dec=3)
                dbl("minor", "tube radius", d["minor"], dec=3, mn=0.01)
            elif feature.kind == "sphere":
                dbl("radius", "radius", d["radius"])
        elif isinstance(feature, ExtrudeFeature):
            dbl("height", "height", feature.height)
            dbl("fillet", "fillet", feature.fillet, mn=0.0)
            dbl("chamfer", "chamfer", feature.chamfer, mn=0.0)
            dbl("taper", "taper", feature.taper, dec=1, mn=None,
                ang=True)
            check("symmetric", "symmetric about the sketch plane",
                  feature.symmetric)
        elif isinstance(feature, RevolveFeature):
            dbl("angle", "angle", feature.angle, dec=1, ang=True)
        elif isinstance(feature, HoleFeature):
            dbl("radius", "radius", feature.radius, dec=3, mn=0.05)
            check("through", "through all", feature.through)
            dbl("depth", "depth", feature.depth, mn=0.05)
        elif isinstance(feature, BodyFilletFeature):
            dbl("radius", "radius", feature.radius)
            check("chamfer", "chamfer, not fillet", feature.chamfer)
        elif isinstance(feature, ShellFeature):
            dbl("thickness", "wall thickness", feature.thickness, mn=0.05)
        elif isinstance(feature, ThreadFeature):
            dbl("pitch", "pitch", feature.pitch, dec=3)
            dbl("length", "length", feature.length)
        elif isinstance(feature, LinearPatternFeature):
            ints("count", "occurrences", feature.count)
            for i, k in enumerate("xyz"):
                dbl(f"v{i}", f"offset {k}", feature.vector[i], mn=None)
        elif isinstance(feature, CircularPatternFeature):
            ints("count", "occurrences", feature.count)
            dbl("angle", "angle", feature.angle, dec=1, mn=1.0, ang=True)
        elif isinstance(feature, PathPatternFeature):
            ints("count", "occurrences", feature.count)
        elif isinstance(feature, MirrorFeature):
            combo("plane", "mirror plane", ("YZ", "XZ", "XY"),
                  feature.plane)
            dbl("offset", "offset", feature.offset, mn=None)
        elif isinstance(feature, SplitFeature):
            n = np.abs(np.asarray(feature.normal, float))
            i = int(n.argmax())
            dbl("dist", f"plane at {'XYZ'[i]}", feature.origin[i], mn=None)
            check("flip", "keep other side", feature.flip)
        elif isinstance(feature, MoveFeature):
            for i, k in enumerate("xyz"):
                dbl(f"v{i}", f"translate {k}", feature.vec[i], mn=None)
            check("copy", "copy (join the twin)", feature.copy)
        elif isinstance(feature, RotateFeature):
            ax = int(np.abs(np.asarray(feature.axis, float)).argmax())
            combo("axis", "axis", ("X", "Y", "Z"), "xyz"[ax].upper())
            dbl("angle", "angle", feature.angle_deg, dec=1, mn=None,
                ang=True)
            check("copy", "copy (join the twin)", feature.copy)
        elif isinstance(feature, CombineFeature):
            combo("tool", "tool shape", ("Box", "Cylinder", "Cone",
                                         "Torus", "Sphere"),
                  {"box": "Box", "cylinder": "Cylinder", "cone": "Cone",
                   "torus": "Torus",
                   "sphere": "Sphere"}.get(feature.tool, "Box"))
            combo("op", "operation", ("Join", "Cut", "Intersect"),
                  {"union": "Join", "subtract": "Cut",
                   "intersect": "Intersect"}.get(feature.op, "Join"))
            dbl("dx", "length X", feature.dims.get("dx", 20.0))
            dbl("dy", "length Y", feature.dims.get("dy", 20.0))
            dbl("dz", "length Z", feature.dims.get("dz", 20.0))
            dbl("radius", "radius", feature.dims.get("radius", 8.0),
                dec=3)
            dbl("r1", "bottom radius",
                feature.dims.get("radius_bottom", 12.0), dec=3)
            dbl("r2", "top radius", feature.dims.get("radius_top", 4.0),
                dec=3, mn=0.0)
            dbl("major", "ring radius", feature.dims.get("major", 15.0),
                dec=3)
            dbl("minor", "tube radius", feature.dims.get("minor", 4.0),
                dec=3, mn=0.01)
            dbl("height", "height", feature.dims.get("height", 30.0))
            for i, k in enumerate("xyz"):
                dbl(f"c{i}", f"centre {k}", feature.center[i], mn=None)
        return fld

    def _apply_feature_params(self, feature, v):
        """Write the dialog's (unit-spoken) values back into the
        feature — millimetres stay the stored truth."""
        u = self.doc.units if self.doc else "mm"
        sc = units.PER_MM[u]

        def mm(key):
            return float(v[key]) * sc

        if isinstance(feature, PrimitiveFeature):
            d = feature.dims
            if feature.kind == "box":
                for k in ("dx", "dy", "dz"):
                    d[k] = mm(k)
            elif feature.kind == "cylinder":
                d["radius"] = mm("radius")
                d["height"] = mm("height")
            elif feature.kind == "cone":
                d["radius_bottom"] = mm("r1")
                d["radius_top"] = mm("r2")
                d["height"] = mm("height")
            elif feature.kind == "torus":
                d["major"] = mm("major")
                d["minor"] = mm("minor")
            elif feature.kind == "sphere":
                d["radius"] = mm("radius")
        elif isinstance(feature, ExtrudeFeature):
            feature.height = mm("height")
            feature.fillet = mm("fillet")
            feature.chamfer = mm("chamfer")
            feature.taper = float(v["taper"])
            feature.symmetric = bool(v["symmetric"])
        elif isinstance(feature, RevolveFeature):
            feature.angle = float(v["angle"])
        elif isinstance(feature, HoleFeature):
            feature.radius = mm("radius")
            feature.through = bool(v["through"])
            feature.depth = mm("depth")
        elif isinstance(feature, BodyFilletFeature):
            feature.radius = mm("radius")
            feature.chamfer = bool(v["chamfer"])
        elif isinstance(feature, ShellFeature):
            feature.thickness = mm("thickness")
        elif isinstance(feature, ThreadFeature):
            feature.pitch = mm("pitch")
            feature.length = mm("length")
        elif isinstance(feature, LinearPatternFeature):
            feature.count = int(v["count"])
            feature.vector = tuple(mm(f"v{i}") for i in range(3))
        elif isinstance(feature, CircularPatternFeature):
            feature.count = int(v["count"])
            feature.angle = float(v["angle"])
        elif isinstance(feature, PathPatternFeature):
            feature.count = int(v["count"])
        elif isinstance(feature, MirrorFeature):
            feature.plane = str(v["plane"])
            feature.offset = mm("offset")
        elif isinstance(feature, SplitFeature):
            n = np.abs(np.asarray(feature.normal, float))
            i = int(n.argmax())
            org = [float(x) for x in feature.origin]
            org[i] = mm("dist")
            feature.origin = tuple(org)
            feature.flip = bool(v["flip"])
        elif isinstance(feature, MoveFeature):
            feature.vec = tuple(mm(f"v{i}") for i in range(3))
            feature.copy = bool(v["copy"])
        elif isinstance(feature, RotateFeature):
            feature.axis = tuple(float(x) for x in
                                 np.eye(3)["XYZ".index(str(v["axis"]))])
            feature.angle_deg = float(v["angle"])
            feature.copy = bool(v["copy"])
        elif isinstance(feature, CombineFeature):
            feature.tool = {"Box": "box", "Cylinder": "cylinder",
                            "Cone": "cone", "Torus": "torus",
                            "Sphere": "sphere"}[str(v["tool"])]
            feature.op = {"Join": "union", "Cut": "subtract",
                          "Intersect": "intersect"}[str(v["op"])]
            if feature.tool == "box":
                feature.dims = {"dx": mm("dx"), "dy": mm("dy"),
                                "dz": mm("dz")}
            elif feature.tool == "cylinder":
                feature.dims = {"radius": mm("radius"),
                                "height": mm("height")}
            elif feature.tool == "cone":
                feature.dims = {"radius_bottom": mm("r1"),
                                "radius_top": mm("r2"),
                                "height": mm("height")}
            elif feature.tool == "torus":
                feature.dims = {"major": mm("major"),
                                "minor": mm("minor")}
            else:
                feature.dims = {"radius": mm("radius")}
            feature.center = tuple(mm(f"c{i}") for i in range(3))
        self.doc.dirty = True

    # ---- Drawings (M93) --------------------------------------------------------
    def _make_drawing_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 4, 6, 4)
        bl.setSpacing(4)
        back = QPushButton("\u2190 Back")
        back.setProperty("tb", True)
        back.clicked.connect(lambda: self._show_page(self.viewport))
        bl.addWidget(back)
        self._drawing_page_btn = back
        pg = QPushButton("A3")
        pg.setProperty("tb", True)
        pg.setToolTip("Sheet size")
        pg.clicked.connect(self._toggle_sheet)
        bl.addWidget(pg)
        self._sheet_btn = pg
        ex_png = QPushButton("Export PNG\u2026")
        ex_png.setProperty("tb", True)
        ex_png.clicked.connect(lambda: self.export_drawing())
        bl.addWidget(ex_png)
        ex_dxf = QPushButton("Export DXF\u2026")
        ex_dxf.setProperty("tb", True)
        ex_dxf.setToolTip("The whole sheet as one DXF drawing")
        ex_dxf.clicked.connect(
            lambda: self.export_drawing(ext=".dxf"))
        bl.addWidget(ex_dxf)
        dimb = QPushButton("Dimension")                  # M94 toggle
        dimb.setProperty("tb", True)
        dimb.setCheckable(True)
        dimb.setToolTip("Click two view endpoints to lay a live "
                        "millimetre bubble (Esc-free: click again to "
                        "take it off)")
        dimb.toggled.connect(
            lambda on: self.drawing.set_dim_mode(on))
        bl.addWidget(dimb)
        self._dim_btn = dimb
        bl.addStretch(1)
        lay.addWidget(bar)
        from .drawingview import DrawingCanvas
        self.drawing = DrawingCanvas()
        self.drawing.dim_added.connect(self._add_dim)     # M94 bubbles
        self.drawing.view_drag_begin.connect(            # M96 undo capture
            self._capture)
        lay.addWidget(self.drawing, 1)
        return page

    def _toggle_sheet(self):
        if self.doc is None or not self.doc.drawings:
            return
        self._capture()
        g = self.doc.drawings[-1]
        g["page"] = "A4" if g.get("page", "A3") == "A3" else "A3"
        self.drawing.page = g["page"]
        self.drawing.set_document(self.doc)
        self.doc.dirty = True
        self.status.showMessage(f"Sheet: {g['page']}", 3000)

    def action_new_drawing(self):
        """Create ▸ New drawing: a sheet of live silhouette views of
        the body — top, front, right, iso, fitted to the page."""
        if self.doc is None:
            return
        if self.doc.result is None:
            self.status.showMessage("Nothing to draw — build a body "
                                    "first", 5000)
            return
        self._capture()
        n = len(self.doc.drawings) + 1
        name = f"Drawing{n}"
        self.doc.drawings.append({"name": name, "page": "A3",
                                  "dims": []})            # M94 bubbles
        self.doc.dirty = True
        self.drawing.set_document(self.doc)
        self._show_page(self._drawing_page)
        self.recompute()
        self.status.showMessage(
            f"{name} created \u2014 top \u00b7 front \u00b7 right \u00b7 iso"
            " \u00b7 live off the model", 6000)

    def _add_dim(self, view: str, a: tuple, b: tuple, opts: dict = None):
        """A finished bubble (M94/M95): undo-captured, stored in MODEL
        millimetres — linear endpoints PLUS view fractions so they
        follow a stretch; diameter bubbles remember centre + travel
        direction and re-find their live circle on every repaint."""
        if self.doc is None or not self.doc.drawings:
            return
        opts = opts or {}
        self._capture()
        g = self.doc.drawings[-1]
        if opts.get("diameter"):
            r = float(opts["r"])
            entry = {"view": view, "diameter": True,
                     "center": [float(x) for x in opts["center"]],
                     "dir": [float(x) for x in opts["dir"]],
                     "r": r,
                     "a": [float(a[0]), float(a[1])],
                     "b": [float(b[0]), float(b[1])],
                     "text": "\u00d8 %.2f" % (2 * r)}
        else:
            entry = {"view": view, "a": [float(a[0]), float(a[1])],
                     "b": [float(b[0]), float(b[1])],
                     "text": f"{math.dist(a, b):.2f}"}
            ra = self.drawing.rel_anchor(view, a)
            rb = self.drawing.rel_anchor(view, b)
            if ra is not None:
                entry["a_rel"] = [float(ra[0]), float(ra[1])]
            if rb is not None:
                entry["b_rel"] = [float(rb[0]), float(rb[1])]
        g.setdefault("dims", []).append(entry)
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage(
            f"Dimension {entry['text']} \u00b7 {view} view", 4000)

    def _open_drawing(self, idx: int):
        if self.doc is None or not (0 <= idx < len(self.doc.drawings)):
            return
        self.drawing.set_document(self.doc, idx=idx)
        self._show_page(self._drawing_page)

    def export_drawing(self, path=None, ext=".png"):
        """Sheet out: PNG pixels or one DXF holding every view — the
        drawing reuses the M92 profile writer."""
        if self.doc is None or self.drawing is None:
            return
        lay = self.drawing.layout()
        if not lay:
            self.status.showMessage("The sheet has no views to export",
                                    5000)
            return
        if path is None:
            from PySide6.QtWidgets import QFileDialog
            base = self.doc.drawings[-1]["name"] if self.doc.drawings \
                else "drawing"
            flt = ("PNG (*.png)" if ext == ".png" else "DXF (*.dxf)")
            path, _f = QFileDialog.getSaveFileName(
                self, "Export drawing",
                str(Path.home() / f"{base}{ext}"), flt)
            if not path:
                return
        try:
            if path.lower().endswith(".dxf"):
                placed = self.drawing.placed()
                ops = []
                for view in placed.values():
                    for c in view["chains"]:
                        if len(c) > 1:
                            closed = (len(c) > 3
                                      and np.allclose(c[0], c[-1]))
                            ops.append(("poly", [tuple(p) for p in c],
                                        bool(closed)))
                # M94: the bubbles' ink travels (the paper text is the
                # PNG's job — DXF line art only)
                if self.doc.drawings:
                    g = self.doc.drawings[-1]
                    for d in g.get("dims", []):
                        view = placed.get(d["view"])
                        if view is None:
                            continue
                        sc, off = view["sc"], view["off"]
                        if d.get("diameter"):               # M95: rim to rim
                            cx0, cy0 = d["a"]
                            ux0, uy0 = d.get("dir", (1.0, 0.0))
                            r0 = float(d.get("r", math.dist(d["a"], d["b"])))
                            pa = (cx0 - ux0 * r0, cy0 - uy0 * r0)
                            pb = (cx0 + ux0 * r0, cy0 + uy0 * r0)
                        else:
                            pa, pb = d["a"], d["b"]
                        A = (pa[0] * sc + off[0],
                             pa[1] * sc + off[1])
                        B = (pb[0] * sc + off[0],
                             pb[1] * sc + off[1])
                        vx, vy = B[0] - A[0], B[1] - A[1]
                        L = math.hypot(vx, vy)
                        if L < 1e-9:
                            continue
                        nx, ny = -vy / L, vx / L
                        ctr = (off[0] + 0.5 * (view["min"][0]
                                               + view["max"][0]),
                               off[1] + 0.5 * (view["min"][1]
                                               + view["max"][1]))
                        mx, my = 0.5 * (A[0] + B[0]), 0.5 * (A[1] + B[1])
                        if (mx - ctr[0]) * nx + (my - ctr[1]) * ny < 0:
                            nx, ny = -nx, -ny
                        od = 4.0                            # sheet mm
                        A2 = (A[0] + nx * od, A[1] + ny * od)
                        B2 = (B[0] + nx * od, B[1] + ny * od)
                        ops.append(("line", A, A2))
                        ops.append(("line", B, B2))
                        ops.append(("line", A2, B2))
                n = export2d.write_dxf(ops, path)
            else:
                from PySide6.QtGui import QPixmap
                w, h = 1600, int(1600 * (self.drawing.height() /
                                         max(1, self.drawing.width())))
                pm = QPixmap(w, max(h, 400))
                pm.fill()
                from PySide6.QtGui import QPainter as _QP
                p = _QP(pm)
                self.drawing.resize(w, max(h, 400))
                self.drawing.paintPage(p)
                p.end()
                pm.save(path)
                n = w * h
        except Exception as e:
            self.status.showMessage(f"Drawing export refused: {e}", 6000)
            return
        self.status.showMessage(f"Drawing exported to {Path(path).name}",
                                6000)

    # ---- User Parameters (M81) ----------------------------------------------
    def action_user_parameters(self):
        """Fusion's parameter sheet: named numbers (`width = 20`) whose
        formulas may reference each other, driving every feature lever
        that carries an fx binding.  A sheet with one bad line is
        refused whole — nothing half-loads."""
        if self.doc is None:
            return
        sheet = "\n".join(f"{k} = {v}" for k, v in self.doc.params.items())
        v = cmddialog.ask(self, "User Parameters", [dict(
            key="sheet", kind="multiline",
            label="name = formula   (one per line, # comments ok)",
            default=sheet)])
        if v is None:
            return
        try:
            raw = params.parse_sheet(v["sheet"])
            vals = params.resolve(raw)
        except params.ParamError as e:
            self.status.showMessage(f"Parameters refused: {e}", 6000)
            return
        self._capture()
        self.doc.params = raw
        self.recompute()
        self.status.showMessage(
            "User parameters: " + ",  ".join(f"{k} = {g:g}"
                                             for k, g in vals.items())
            if vals else "User parameters cleared", 5000)

    def action_configurations(self):
        """Fusion's Configurations, sheet-honest (M91): named rows that
        override parameter values, one active at a time. The table is
        text — `Small: width = 18, height = 10` per line — same grammar
        precedent as the M81 sheet. A bad row is refused whole."""
        if self.doc is None:
            return
        body = "\n".join(
            f"{name}: " + ", ".join(f"{p} = {val}"
                                    for p, val in over.items())
            for name, over in sorted(self.doc.configs.items()))
        v = cmddialog.ask(self, "Configurations", [
            dict(key="sheet", kind="multiline",
                 label="Name: param = value, param = value"
                 "   (one per line, # comments ok)",
                 default=body),
            dict(key="active", kind="combo", label="Active",
                 choices=["Default"] + sorted(self.doc.configs),
                 default=self.doc.active_config or "Default")])
        if v is None:
            return
        try:
            cfgs = params.parse_configs(str(v["sheet"]))
            if v["active"] != "Default" and v["active"] not in cfgs:
                raise params.ParamError(
                    f"configuration {v['active']!r} is not in the table")
        except params.ParamError as e:
            self.status.showMessage(f"Configurations refused: {e}", 6000)
            return
        self._capture()
        self.doc.configs = cfgs
        self.doc.active_config = (None if v["active"] == "Default"
                                  else v["active"])
        self.recompute()
        named = " \u00b7 ".join(sorted(cfgs)) if cfgs else "none defined"
        self.status.showMessage(
            f"Configurations: {named}"
            + (f" \u00b7 active {self.doc.active_config}"
               if self.doc.active_config else " \u00b7 base parameters"),
            5000)

    def _set_active_config(self, name):
        """The switcher half (M91): flip the active configuration and
        rebuild — the solid follows its new numbers. Undo-safe."""
        if self.doc is None:
            return
        self._capture()
        self.doc.active_config = name
        try:
            self.recompute()
        except params.ParamError as e:        # sheet got illegal under it
            self.status.showMessage(f"Configuration refused: {e}", 6000)
            return
        self.status.showMessage(
            f"Configuration {name!r} active — solid rebuilt"
            if name else "Configuration cleared — base parameters", 4000)

    def action_change_params(self, feature=None):
        """Fusion's Modify ▸ Change Parameters: edit the numbers that
        define a feature.  Undo-safe; honours document measures."""
        if self.doc is None:
            return
        feat = feature if feature is not None \
            else self.rail.tree.current_feature()
        if feat is None:
            self.status.showMessage("Select a feature, then change its "
                                    "parameters", 3500)
            return
        fld = self._feature_params(feat)
        if not fld:
            self.status.showMessage(
                f"{feat.name}: captured geometry — no plain numbers to "
                "change", 3500)
            return
        for spec in list(fld):            # the fx column (M81)
            if spec["kind"] in ("double", "int"):
                fld.append(dict(key=f"fx_{spec['key']}", kind="text",
                                label=f"fx \u00b7 {spec['label']}",
                                default=feat.bindings.get(spec["key"], "")))
        v = cmddialog.ask(self, f"Change Parameters \u2014 {feat.name}",
                          fld)
        if v is None:
            return
        # M81 fx column: every numeric lever may instead carry a formula
        exprs, touched = {}, []
        for key in [k for k in v if str(k).startswith("fx_")]:
            attr = key[3:]
            expr = str(v.pop(key)).strip().lstrip("=").strip()
            touched.append(attr)
            if expr:
                try:
                    params.eval_expr(expr, params.resolve(self.doc.params))
                except params.ParamError as e:
                    self.status.showMessage(f"Binding refused: {e}", 6000)
                    return
                exprs[attr] = expr
        self._capture()
        self._apply_feature_params(feat, v)
        for attr in touched:
            feat.bindings.pop(attr, None)
        feat.bindings.update(exprs)
        self.recompute()
        self.status.showMessage(f"Parameters changed on {feat.name}", 4000)

    def _set_corner(self, feature, kind: str):
        """Round (fillet) or cut (chamfer) the extrusion's vertical edges.
        The two are mutually exclusive; 0 clears."""
        cur = getattr(feature, kind)
        title = "Fillet vertical edges" if kind == "fillet" \
            else "Chamfer vertical edges"
        val, ok = Shell.getDouble(self, title, "Size (mm, 0 = none):",
                                         cur, 0.0, 5000.0, 3)
        if not ok:
            return
        self._capture()
        setattr(feature, kind, float(val))
        setattr(feature, "fillet" if kind == "chamfer" else "chamfer", 0.0)
        self.doc.dirty = True
        self.recompute()
        verb = "filleted" if kind == "fillet" else "chamfered"
        self.status.showMessage(
            f"{feature.name}: {verb} {val:g} mm" if val > 0
            else f"{feature.name}: sharp edges restored", 4000)

    def _set_angle(self, feature):
        val, ok = Shell.getDouble(self, "Revolve angle",
                                         "Angle (°):", feature.angle,
                                         1.0, 360.0, 1)
        if not ok or abs(val - feature.angle) < 1e-9:
            return
        self._capture()
        feature.angle = float(val)
        self.doc.dirty = True
        self.recompute()
        self.status.showMessage(f"{feature.name}: {val:g}° revolve", 4000)

    def _rename_feature(self, feature):
        name, ok = Shell.getText(self, "Rename feature", "Name:",
                                        text=feature.name)
        if not ok or not name.strip():
            return
        self._capture()
        feature.name = name.strip()
        self.doc.dirty = True
        self.recompute()

    def _delete_feature(self, feature):
        self._capture()
        self.doc.features.remove(feature)
        self.doc.dirty = True
        self.rail.props.show_feature(None)
        self.recompute()
        self.status.showMessage(f"Deleted {feature.name} (Ctrl+Z restores)", 4000)

    def edit_sketch(self, feature):
        if self.doc is None or not self._discard_guard():
            return
        model = model_from_dict(feature.sketch)
        model.sid = feature.sid or id(model)
        self._editing_sid = model.sid
        self.sketch.set_model(model)
        self._show_page(self._sketch_page)
        self._pick_tool("select")
        self.status.showMessage(f"Editing {feature.sketch.get('name', 'Sketch')} — "
                                "X to update solid")

    def _next_sketch_name(self) -> str:
        n = sum(1 for f in self.doc.features
                if isinstance(f, (ExtrudeFeature, RevolveFeature))
                and f.sketch) + 1
        return f"Sketch{n}"

    def _discard_guard(self) -> bool:
        if self.sketch.model and (self.sketch.model.sketch.lines
                                  or self.sketch.model.sketch.circles):
            ans = QMessageBox.question(
                self, "Discard current sketch?",
                "The sketch in the editor is not in the model yet. Discard it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return False
        return True

    def _begin_sketch(self, model: SketchModel):
        self._editing_sid = None
        self.sketch.set_model(model)
        self._show_page(self._sketch_page)
        self._pick_tool("rect")     # most sketches start with a rectangle

    def action_construction_plane(self):
        """Fusion's Construct ▸ Plane: an offset copy of an origin plane,
        ready to sketch on."""
        if self.doc is None:
            return
        v = cmddialog.ask(self, "Construction Plane", [
            dict(key="base", label="Offset from", kind="combo",
                 choices=["XY", "XZ", "YZ"], group="Plane"),
            dict(key="dist", label="Distance", kind="double",
                 default=10.0, min=-1e5, max=1e5, group="Plane"),
        ], remember_key="construction_plane")
        if v is None:
            return
        base, dist = v["base"], v["dist"]
        p = self.doc.add_plane(base, dist)
        self._unsaved = True
        self.rail.tree.reload()
        self.viewport.refresh()
        self.status.showMessage(
            f"{p['name']} at {dist:+g} mm from {base} — double-click it in "
            "the browser to sketch on it", 6000)

    def action_thread(self):
        """Fusion Thread (M49b v1): click a cylindrical boss face and
        give it real bolt threads — a helical ridge cut to the minor."""
        from ..core.thread import fit_cylinder
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Thread",
                                "Nothing to thread yet — extrude or "
                                "import a solid first.")
            return
        groups = self.viewport.selected_groups()
        if len(groups) != 1:
            QMessageBox.information(
                self, "Thread",
                "Click exactly ONE cylindrical face to thread — "
                "flat faces cannot be threaded.")
            return
        tm = self.viewport._tm
        seed = int(sorted(groups[0])[0])
        tris = np.asarray(self.viewport.smooth_region(seed), int)
        pts = tm.vertices[np.asarray(tm.faces, int)[tris]].reshape(-1, 3)
        nrm = np.repeat(np.asarray(tm.face_normals, float)[tris], 3, axis=0)
        fit = fit_cylinder(pts, nrm)
        if fit is None:
            QMessageBox.information(
                self, "Thread",
                "That face is not a cylinder — Thread needs the curved "
                "face of a boss or pin.")
            return
        dia = 2.0 * fit["radius"]
        sizes = list(ISO_COARSE)
        near = min(sizes, key=lambda n: abs(float(n[1:]) - dia))
        vals = cmddialog.ask(
            self, f"Thread — boss Ø {dia:g} mm  (closest size {near})",
            [dict(key="size", label="ISO size", kind="combo",
                  choices=[f"{n} × {p:g}" for n, (p, _) in ISO_COARSE
                           .items()])])
        if vals is None:
            return
        size = vals["size"].split(" ")[0]
        pitch = ISO_COARSE[size][0]
        length = fit["zmax"] - fit["zmin"]
        if length <= 1.2 * pitch:
            QMessageBox.information(
                self, "Thread", f"That face is only {length:g} mm tall — "
                                f"too short for an {size} thread.")
            return
        if fit["radius"] - 0.5 * pitch <= 0.1:
            QMessageBox.information(
                self, "Thread", f"Ø {dia:g} is too thin for {size}: the "
                                "thread would cut away the core.")
            return
        axis = np.asarray(fit["axis"], float)
        start = np.asarray(fit["point"], float) + axis * fit["zmin"]
        self._capture()
        self.doc.add(ThreadFeature(
            name=f"Thread {size}", op="subtract",
            center=tuple(float(t) for t in start),
            axis=tuple(float(t) for t in axis),
            radius=float(fit["radius"]), pitch=float(pitch),
            length=float(length)))
        self.recompute()
        self.viewport.refresh()
        turns = int(length / pitch)
        self.status.showMessage(
            f"Thread {size} × {pitch:g} cut on the Ø {dia:g} boss — "
            f"{turns} turns, minor Ø {dia - pitch:g} mm", 6000)

    def action_section(self, spec):
        """Fusion Section Analysis: clip the body on a plane, purely
        visual (nothing is cut in the model).  Same plane twice = off."""
        cur = self.viewport.section
        if spec is not None and cur and cur.get("label") == spec:
            spec = None
        self.viewport.set_section(spec)
        if spec is None:
            self.status.showMessage("Section off — full body restored", 4000)
        else:
            self.status.showMessage(
                f"Section on {spec} — ribbon ▸ Section ▸ Flip to change "
                "side", 6000)

    def action_flip_section(self):
        self.viewport.flip_section()
        if self.viewport.section:
            self.status.showMessage("Section side flipped", 3000)

    def action_sketch_on_plane(self, name: str):
        """Sketch on a construction plane: a FACE-frame sketch carrying
        the plane's origin+basis, so X extrudes along the plane normal."""
        if self.doc is None or not self._discard_guard():
            return
        p = next((q for q in self.doc.planes if q["name"] == name), None)
        if p is None:
            return
        model = SketchModel(plane="FACE")
        model.axes = [list(p["u"]), list(p["v"])]
        model.origin = tuple(float(t) for t in p["origin"])
        model.name = self._next_sketch_name()
        self._begin_sketch(model)
        self.status.showMessage(
            f"Sketching on {p['name']} — draw, then X extrudes along its "
            "normal")

    def _cplane_menu(self, name, pos):
        menu = QMenu(self)
        menu.addAction("Sketch on plane",
                       lambda: self.action_sketch_on_plane(name))
        menu.addSeparator()
        menu.addAction("Delete construction plane",
                       lambda: self._delete_plane(name))
        menu.exec_(pos)

    def _body_menu(self, pos):
        vis = self.viewport._r.show_solid
        menu = QMenu(self)
        menu.addAction(("Hide" if vis else "Show") + " body",
                       lambda: self.viewport.set_solid_visible(not vis))
        menu.exec_(pos)

    def _delete_plane(self, name):
        if self.doc and self.doc.remove_plane(name):
            self._unsaved = True
            self.rail.tree.reload()
            self.viewport.refresh()
            self.status.showMessage(f"Deleted {name}", 3000)

    def action_new_sketch(self, plane: str = "XY"):
        if self.doc is None or not self._discard_guard():
            return
        model = SketchModel(plane=plane)
        model.name = self._next_sketch_name()
        self._begin_sketch(model)
        self.status.showMessage(f"Sketching on {plane} — R rect · L line · C circle · "
                                "O slot · Y polygon · A arc · "
                                "H/V/F/G/D/P/Q/T/I/J/M/2 constraints · "
                                "/ trim · . on-curve · U offset · W sweep · "
                                "K construction · "
                                "X extrude · Esc select")

    def _project_model_edges(self):
        """Project — Fusion's Project/Include on a mesh kernel: slice
        the current solid with the sketch's plane and land the
        contours as reference geometry under the cursor.  Replacing on
        every press keeps the canvas honest (no stacked duplicates)."""
        cv = self.sketch
        if cv is None or cv.model is None:
            return
        res = self.doc.result if self.doc is not None else None
        if res is None:
            self.status.showMessage("Nothing to project — no solid yet",
                                    4000)
            return
        cv._push_hist()
        tm = res.to_trimesh()
        n = cv.model.project(tm.vertices, tm.faces)
        cv.update()
        self.doc.dirty = True
        self.status.showMessage(
            (f"Projected {n} model contour"
             + ("s" if n != 1 else "") + " — snap to the dashed edges")
            if n else "Nothing to project — the plane misses the solid",
            5000)

    def _start_sketch_on_face(self, point, normal):
        if self.doc is None or not self._discard_guard():
            return
        u, v = face_basis(normal)
        model = SketchModel(plane="FACE")
        model.axes = [u.tolist(), v.tolist()]
        model.origin = tuple(float(t) for t in point)
        model.name = self._next_sketch_name()
        self._begin_sketch(model)
        self.status.showMessage(
            "Sketching on face — draw, then X extrudes outward from it")

    def _on_profiles(self, profiles, name, revolve=False):
        m = self.sketch.model
        payload = model_to_dict(m)
        payload["name"] = name
        sid = self._editing_sid
        if sid is not None:
            hole_owns = any(isinstance(f, HoleFeature) and f.sid == sid
                            for f in self.doc.features)
            sweep_owns = any(isinstance(f, SweepFeature) and f.sid == sid
                             for f in self.doc.features)
            loft_owns = any(isinstance(f, LoftFeature)
                            and any(s.get("sid") == sid for s in f.sections)
                            for f in self.doc.features)
            owns = hole_owns or sweep_owns or loft_owns
            if owns:
                self._capture()
            if hole_owns:
                self._sync_holes(sid, payload)
            if sweep_owns:
                self._sync_sweeps(sid, payload)
            if loft_owns:
                self._sync_lofts(sid, payload)
            self._update_sketch_features(sid, profiles, payload,
                                         capture=not owns)
            self.sketch.set_model(SketchModel())     # committed: clear editor
            self._show_page(self.viewport)
            self.recompute()
            self.status.showMessage(f"Updated {name} — solid recomputed", 5000)
            return
        if revolve:
            for outer, _holes in profiles:
                o = np.asarray(outer)
                if o[:, 0].min() < -1e-6 < o[:, 0].max():
                    QMessageBox.warning(
                        self, "Revolve",
                        "A profile crosses the sketch's vertical axis (the "
                        "u=0 line through the origin) — Fusion revolves "
                        "profiles about it, so keep each one on a side.")
                    return
            angle, ok = Shell.getDouble(
                self, "Revolve", "Angle (degrees):", 360.0, 1.0, 360.0, 1)
            if not ok:
                return
        else:
            height, ok = Shell.getDouble(
                self, "Extrude", "Height (mm):", 5.0, 0.01, 1e5, 2)
            if not ok:
                return
        self._capture()
        for i, (outer, holes) in enumerate(profiles):
            tag = name if len(profiles) == 1 else f"{name} #{i + 1}"
            face = m.plane == "FACE"
            axes = [list(map(float, a)) for a in m.axes] if face else None
            placement = tuple(m.origin) if face else (0.0, 0.0, 0.0)
            sketch = dict(payload, regions=len(profiles), region=i)
            common = dict(name=tag, outer=np.asarray(outer),
                          holes=[np.asarray(h) for h in holes],
                          op="union", plane=m.plane, axes=axes,
                          placement=placement, sketch=sketch,
                          sid=m.sid, region=i)
            self.doc.add(RevolveFeature(angle=angle, **common) if revolve
                         else ExtrudeFeature(height=height, **common))
        self.sketch.set_model(SketchModel())         # committed: clear editor
        self._show_page(self.viewport)
        self.recompute()
        self.viewport.refresh(fit=True)
        if revolve:
            self.status.showMessage(
                f"Revolved {len(profiles)} region(s) from {name} "
                f"by {angle:g}°", 6000)
        else:
            self.status.showMessage(
                f"Extruded {len(profiles)} region(s) from {name} "
                f"by {height:g} mm", 6000)

    def action_hole(self):
        """Fusion Hole: each circle in the current sketch drills one hole —
        simple, counterbore or countersink — into the existing solid."""
        if self.doc is None:
            return
        m = self.sketch.model
        circles = [c for c in m.sketch.circles if not c.construction] \
            if m is not None else []
        if not circles:
            QMessageBox.information(
                self, "Hole",
                "Draw circles first — each circle becomes one drilled hole. "
                "Sketch on a face (double-click), add the circles, run Hole.")
            return
        if not self.doc.features or self.doc.result is None:
            QMessageBox.warning(
                self, "Hole",
                "A hole cuts into an existing solid — extrude a body first.")
            return
        opts = HoleDialog.ask(self, [2 * c.r for c in circles])
        if opts is None:
            return
        self._capture()
        u, v = plane_uv(m.plane, m.axes)
        u, v = np.asarray(u, float), np.asarray(v, float)
        n = np.cross(u, v)
        origin = np.asarray(m.origin, float)
        base = self.doc.result
        lo, hi = base.bounding_box
        diag = float(np.linalg.norm(hi - lo))
        through = bool(opts["through"])
        depth = float(opts["depth"])
        cb_r = float(opts["cb_dia"]) / 2 if opts["type"] == "counterbore" else 0.0
        cs_r = float(opts["cs_dia"]) / 2 if opts["type"] == "countersink" else 0.0
        thread = opts.get("thread", "None")
        tap_pitch, tap_dia = ((0.0, 0.0) if thread == "None"
                              else ISO_COARSE[thread])
        payload = model_to_dict(m)
        owned = [f for f in self.doc.features
                 if isinstance(f, HoleFeature) and f.sid == m.sid]
        for i, c in enumerate(circles):
            w = origin + u * float(c.c.x) + v * float(c.c.y)
            rad = tap_dia / 2 if tap_pitch else float(c.r)   # tapped: tap-drill core
            L = (diag + 4 * max(rad, cb_r, cs_r)) if through else depth
            tlen = L if tap_pitch else 0.0                   # thread the full depth
            kind = (" counterbore" if cb_r > rad else
                    " countersink" if cs_r > rad else "")
            nm = f"Hole {thread}" if tap_pitch else f"Hole Ø{2 * rad:g}"
            if i < len(owned):                # re-drill: update in place
                f = owned[i]
                f.center, f.radius = tuple(w), rad
                f.depth, f.through, f.cut_length = depth, through, float(L)
                f.cb_radius, f.cb_depth = cb_r, float(opts["cb_depth"])
                f.cs_radius, f.cs_angle = cs_r, float(opts["cs_angle"])
                f.thread_pitch, f.thread_len = tap_pitch, tlen
                f.name = nm + kind
                f.sketch = dict(payload)
                continue
            # new hole: probe which side of the sketch plane has material
            inward = -n
            probe = HoleFeature(name="probe", center=tuple(w),
                                normal=tuple(inward), radius=rad,
                                cut_length=diag + 4 * rad, through=True)
            if base.intersect(probe.build()).volume <= 1e-6:
                inward = n
            self.doc.add(HoleFeature(
                name=nm + kind, op="subtract",
                center=tuple(w), normal=tuple(inward), radius=rad,
                depth=depth, through=through, cut_length=float(L),
                cb_radius=cb_r, cb_depth=float(opts["cb_depth"]),
                cs_radius=cs_r, cs_angle=float(opts["cs_angle"]),
                thread_pitch=tap_pitch, thread_len=tlen,
                sketch=dict(payload), sid=m.sid, cidx=i))
        for f in owned[len(circles):]:        # circles deleted while editing
            self.doc.features.remove(f)
        self.sketch.set_model(SketchModel())
        self._editing_sid = None
        self._show_page(self.viewport)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Drilled {len(circles)} {opts['type']} hole(s)"
            + (" — through all" if through else f" — {depth:g} mm deep"), 6000)

    def _on_face_selection(self, n: int = 0):
        """Measure-on-pick (Fusion's Inspect>Measure, live): picked faces
        answer in the status bar; no selection shows the body's numbers."""
        if self.doc is None or self.doc.result is None:
            return
        groups = self.viewport.selected_groups()
        if not groups:
            s = self.doc.result
            self.rail.props.show_stats(s.volume, s.surface_area)
            self._update_status()
            return
        try:
            stats = [face_stats(self.viewport._tm, g) for g in groups]
            u = self.doc.units if self.doc else "mm"
            if len(stats) == 1:
                msg = describe(stats[0], None, u)
            elif len(stats) == 2:
                msg = describe(stats[0], stats[1], u)
            else:
                msg = (f"{len(stats)} faces selected — keep exactly two "
                       "to measure between")
        except Exception:          # a stale selection mid-recompute: silent
            return
        self.status.showMessage(msg)

    def action_shell(self):
        """Fusion Shell: hollow the body to thin walls, removing one face
        to open it — enclosures, cases, boxes."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Shell",
                                "Nothing to shell yet — extrude or import "
                                "a solid first.")
            return
        if any(isinstance(f, ShellFeature) for f in self.doc.features):
            QMessageBox.information(self, "Shell",
                                    "This body is already shelled.")
            return
        face = self.viewport.selected_face()
        if face is None:
            QMessageBox.information(
                self, "Shell",
                "Click the face to REMOVE first — the body hollows with "
                "that face open, exactly like Fusion's Shell.")
            return
        t, ok = Shell.getDouble(self, "Shell",
                                       "Wall thickness (mm):", 2.0,
                                       0.05, 1e4, 2)
        if not ok:
            return
        openings = [(tuple(float(x) for x in face["point"]),
                     tuple(float(x) for x in face["normal"]))]
        from ..core.shell import shell_open
        try:                            # validate before touching history
            shell_open(self.doc.result, float(t), openings)
        except ValueError as e:
            QMessageBox.warning(self, "Shell", str(e))
            return
        self._capture()
        self.doc.add(ShellFeature(name="Shell", thickness=float(t),
                                  openings=openings))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(f"Shelled body with {t:g} mm walls", 5000)

    def action_split_body(self):
        """Fusion Split Body (M51): trim the body flush with a plane —
        the maker's 'cut away one half'.  The offset measures from the
        body's centre along the plane normal, so 0 splits it in two."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Split Body",
                                "Nothing to split yet — extrude or "
                                "import a solid first.")
            return
        from ..core.split import PLANES, split_solid
        lo, hi = self.doc.result.bounding_box
        c = [(float(lo[i]) + float(hi[i])) / 2.0 for i in range(3)]
        v = cmddialog.ask(self, "Split Body", [
            dict(key="plane", label="Cut on plane", kind="combo",
                 choices=["XY", "XZ", "YZ"], group="Plane"),
            dict(key="dist", label="Offset from centre", kind="double",
                 default=0.0, min=-1e5, max=1e5, decimals=3,
                 suffix=" mm", group="Plane"),
            dict(key="flip", label="Keep the other side", kind="check",
                 default=False, group="Plane"),
        ], remember_key="split_body")
        if v is None:
            return
        plane, dist, flip = v["plane"], float(v["dist"]), bool(v["flip"])
        nrm = PLANES[plane]
        axis = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
        origin = list(c)
        origin[axis] += dist
        try:                            # validate before touching history
            split_solid(self.doc.result, origin, nrm, flip)
        except ValueError as e:
            QMessageBox.warning(self, "Split Body", str(e))
            return
        self._capture()
        self.doc.add(SplitFeature(name=f"Split {plane}",
                                  origin=tuple(origin), normal=nrm,
                                  flip=flip))
        self.recompute()
        self.viewport.refresh(fit=True)
        removed_up = nrm[axis] * (-1.0 if flip else 1.0) > 0
        self.status.showMessage(
            f"Split on the {plane} plane — kept the "
            f"{'lower' if removed_up else 'upper'} half", 5000)

    def action_visual_style(self, label: str):
        """Fusion View ▸ Visual Styles (M54): the honest five — faces
        only lines, 20% ghost, plain shaded, our Blender default, and
        the blue-grey X-ray."""
        self._renderer.set_visual_style(label)
        self.viewport.update()
        self.status.showMessage(f"{label} visual style", 4000)

    def _apply_appearance(self):
        """Push the document's paint (M52) onto the renderer — the one
        place the colour lives, so undo/open/new all re-sync it."""
        app = (self.doc.appearance if self.doc else None) or None
        self._renderer.set_base_color(
            app["color"] if app else None,
            app.get("opacity", 1.0) if app else 1.0)

    def _apply_units(self):
        u = self.doc.units if self.doc and self.doc.units in units.LABEL \
            else "mm"
        self.rail.props.set_unit(u)

    # ---- 3D Print (M86) ------------------------------------------------------
    def action_3d_print(self):
        """Fusion's Utilities ▸ 3D Print: inspect print readiness, weigh
        the part at the chosen material, then export an STL ready for
        the bed (dropped onto z=0 by default).  Kernel-built parts are
        watertight by construction — the report says so honestly."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.information(self, "3D Print",
                                    "Nothing to print yet — model "
                                    "something first.")
            return
        s = QSettings()
        last = str(s.value("materials/density", "PLA (1.24)"))
        while True:
            dens = (last if last in self._MATERIAL_DENSITIES
                    else "PLA (1.24)")
            rho = float(dens.rsplit("(", 1)[1].rstrip(")"))
            rep = printcheck.print_report(self.doc.result, rho)
            x, y, z = rep["size_mm"]
            lines = [f"Triangles:  {rep['triangles']:,}",
                     f"Watertight: {'yes' if rep['watertight'] else 'NO'}",
                     f"Volume:     {rep['volume_mm3']:,.1f} mm³",
                     f"Mass @ {dens}: {rep['mass_g']:.1f} g",
                     f"Size:       {x:.1f} × {y:.1f} × {z:.1f} mm",
                     f"Islands:    {rep['islands']}"]
            lines += ["! " + w for w in rep["warnings"]]
            v = cmddialog.ask(self, "3D Print", [
                dict(key="report", kind="multiline", label="Report",
                     default="\n".join(lines)),
                dict(key="m", kind="combo", label="Material",
                     choices=self._MATERIAL_DENSITIES, default=dens),
                dict(key="drop", kind="check",
                     label="Drop to bed (rest on z=0 in the STL)",
                     default=True)])
            if v is None:
                return
            if v["m"] != dens:            # material changed: re-weigh
                last = v["m"]
                s.setValue("materials/density", last)
                continue
            break
        path, _f = QFileDialog.getSaveFileName(
            self, "Export STL for printing",
            str(Path(self.doc.title + ".stl")), "STL (*.stl)")
        if not path:
            return
        self._print_export(path, drop=bool(v["drop"]))
        self.status.showMessage(
            f"Print-ready STL written to {Path(path).name}", 5000)

    def _print_export(self, path, drop: bool = True):
        """Export the current solid as an STL, optionally resting it on
        the build plate — the document itself is never moved."""
        tm = (printcheck.drop_to_bed(self.doc.result) if drop
              else self.doc.result.to_trimesh())
        tm.export(str(path))

    def action_mass_properties(self):
        """Fusion's Inspect ▸ Mass Properties (M71): volume, surface
        area, mass at a material density, and the centre of mass —
        every maker's first question ("how heavy will this print?")."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.information(self, "Mass Properties",
                                    "Nothing to measure yet — add a "
                                    "feature first.")
            return
        s = QSettings()
        last = str(s.value("materials/density", "PLA (1.24)"))
        v = cmddialog.ask(self, "Mass Properties — material", [
            dict(key="material", label="Material density (g/cm³)",
                 kind="combo", choices=self._MATERIAL_DENSITIES,
                 default=last if last in self._MATERIAL_DENSITIES
                 else "PLA (1.24)"),
        ])
        if v is None:
            return
        mat = str(v["material"])
        s.setValue("materials/density", mat)
        dens = float(mat.split("(")[1].rstrip(")"))
        p = mass_properties(self.doc.result, dens)
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        box = QMessageBox(self)
        box.setWindowTitle("Mass Properties")
        box.setText(
            f"Volume:          {units.V(p['volume_mm3'], u)}\n"
            f"Surface area:    {units.A(p['area_mm2'], u)}\n"
            f"Material:        {mat}\n"
            f"Mass:            {p['mass_g']:,.2f} g\n"
            f"Centre of mass:  ({units.L(p['com'][0], u)}, "
            f"{units.L(p['com'][1], u)}, {units.L(p['com'][2], u)})")
        box.exec()
        self.status.showMessage(f"Mass {p['mass_g']:,.2f} g — {mat}",
                                5000)

    def action_document_measures(self):
        """Fusion Tools ▸ Document Measures (M60): choose the
        vocabulary every readout speaks — the model itself stays pure
        millimetres, the unit rides the file as metadata."""
        if self.doc is None:
            return
        names = {"Millimetre (mm)": "mm", "Centimetre (cm)": "cm",
                 "Inch (in)": "inch"}
        inv = {v: k for k, v in names.items()}
        v = cmddialog.ask(self, "Document Measures", [
            dict(key="unit", label="Length units", kind="combo",
                 choices=list(names),
                 default=inv.get(self.doc.units, "Millimetre (mm)"),
                 group="Primary units"),
        ])
        if v is None:
            return
        if names[v["unit"]] != self.doc.units:
            self.doc.units = names[v["unit"]]
            self._unsaved = True
        self._apply_units()
        self._update_status()
        self.status.showMessage(
            f"Document measures: {units.LABEL[self.doc.units]}", 4000)

    # ---- marking menu (M56) -----------------------------------------------------
    def _marking_menu(self):
        """Fusion's right-click quick menu: fit / zoom-to / the four
        views / visual styles / display toggles."""
        m = QMenu(self)
        m.addAction("Fit", lambda checked=False: self.action_view("fit"))
        m.addAction("Zoom to selection", self._zoom_to_selection)
        m.addAction("Zoom window",
                    lambda checked=False: self.action_zoom_window())
        m.addSeparator()
        for label, view in (("Isometric", "iso"), ("Front", "front"),
                            ("Top", "top"), ("Right", "right")):
            m.addAction(label, lambda checked=False, v=view:
                        self.action_view(v))
        m.addSeparator()
        vs = m.addMenu("Visual Styles")
        for label in ("Wireframe", "Ghosted", "Shaded",
                      "Shaded with edges", "X-ray"):
            vs.addAction(label, lambda checked=False, lb=label:
                         self.action_visual_style(lb))
        m.addSeparator()
        m.addAction("Toggle grid", self.action_toggle_grid)
        m.addAction("Toggle edges", self.action_toggle_edges)
        return m

    def _show_marking_menu(self, pos):
        menu = self._marking_menu()
        self._mark_menu = menu
        menu.aboutToHide.connect(
            lambda: setattr(self, "_mark_menu", None))
        menu.popup(self.viewport.mapToGlobal(pos))

    def action_zoom_window(self):
        """Fusion marking-menu Zoom window (M62): arm the rectangle
        drag — release zooms the camera onto whatever it enclosed."""
        self.viewport.begin_zoom_window()
        self.status.showMessage("Drag a window to zoom into it — click "
                                "or Esc cancels", 5000)

    def _on_zoom_window(self, payload):
        if payload.get("cancel") or "bbox" not in payload:
            self.status.showMessage(
                "Zoom window: nothing inside the box" if payload.get("empty")
                else "Zoom window cancelled", 3000)
            return
        lo, hi = payload["bbox"]
        self.viewport.camera().fit(np.asarray([lo, hi], float))
        self.viewport.update()
        self.status.showMessage("Zoom window", 2500)

    def _zoom_to_selection(self):
        bbox = self.viewport.selection_bbox()
        if bbox is None and self.doc is not None and self.doc.result:
            bbox = self.doc.result.bounding_box
        if bbox is not None:
            self.viewport.camera().fit(np.asarray(
                [list(bbox[0]), list(bbox[1])], float))
            self.viewport.update()
            self.status.showMessage("Zoomed to selection", 2500)

    def action_appearance(self):
        """Fusion's Appearance dialog (M52): paint the body with a shop
        material — steel to brass — and dial its opacity."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Appearance",
                                "Nothing to paint yet — extrude or "
                                "import a solid first.")
            return
        from ..core.appearance import MATERIALS, appearance
        cur = (self.doc.appearance or {}).get("name", "(none)")
        choices = ["(none)", "Custom…", *MATERIALS]
        v = cmddialog.ask(self, "Appearance", [
            dict(key="preset", label="Material", kind="combo",
                 choices=choices,
                 default=cur if cur in choices else "(none)",
                 group="Body"),
            dict(key="opacity", label="Opacity", kind="double",
                 default=(self.doc.appearance or {}).get("opacity", 1.0),
                 min=0.05, max=1.0, decimals=2, group="Body"),
        ], remember_key="appearance")
        if v is None:
            return
        preset, op = v["preset"], float(v["opacity"])
        self._capture()
        if preset == "(none)":
            self.doc.appearance = None
            msg = "Body unpainted"
        else:
            if preset == "Custom…":
                from PySide6.QtGui import QColor
                from PySide6.QtWidgets import QColorDialog
                old = (self.doc.appearance or {}).get("color")
                init = QColor(*(int(round(c * 255)) for c in old)) \
                    if old else QColor(160, 160, 165)
                col = QColorDialog.getColor(init, self, "Body colour")
                if not col.isValid():
                    self._undo.pop()           # colour cancelled: no edit
                    return
                app = {"name": "Custom",
                       "color": [col.red() / 255, col.green() / 255,
                                 col.blue() / 255],
                       "opacity": max(0.05, min(1.0, op))}
            else:
                app = appearance(preset, op)
            self.doc.appearance = app
            msg = f"Body painted: {app['name']}"
        self._unsaved = True
        self._apply_appearance()
        self._apply_units()
        self.viewport.refresh()
        self.status.showMessage(msg, 5000)

    def action_move_body(self):
        """Fusion Move/Copy (M53): the RGB triad appears at the body's
        centre — grab an arrow and drag, the body slides along that
        axis exactly as fast as the mouse, release commits the move as
        a parametric feature.  Esc or an empty click cancels."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Move",
                                "Nothing to move yet — extrude or "
                                "import a solid first.")
            return
        lo, hi = self.doc.result.bounding_box
        self._move_origin = (np.asarray(lo, float)
                             + np.asarray(hi, float)) / 2.0
        self._move_len = 0.4 * float(np.linalg.norm(
            np.asarray(hi, float) - np.asarray(lo, float)))
        self.viewport.begin_move(self._move_origin, self._move_len)
        self.status.showMessage(
            "Drag a triad arrow to slide the body — release commits, "
            "Esc cancels", 6000)

    def _on_move_drag(self, payload):
        """Live preview through the renderer's mesh offset (no kernel
        calls mid-drag); the release commits a MoveFeature."""
        if payload.get("cancel") or "offset" not in payload:
            self._renderer.set_mesh_offset((0.0, 0.0, 0.0))
            self.viewport.update()
            self.status.showMessage("Move cancelled", 2500)
            return
        off = np.asarray(payload["offset"], float)
        if payload.get("live"):
            self._renderer.set_mesh_offset(off)
            if self._move_origin is not None:
                self._renderer.set_triad(self._move_origin + off,
                                         self._move_len)
            self.viewport.update()
            return
        off_v = tuple(float(v) for v in off)
        self._renderer.set_mesh_offset((0.0, 0.0, 0.0))
        self._renderer.set_triad(None)
        if float(np.linalg.norm(off)) < 1e-4:
            self.viewport.update()
            self.status.showMessage("Move cancelled", 2500)
            return
        self._capture()
        is_copy = bool(payload.get("copy", False))
        self.doc.add(MoveFeature(name="Copy" if is_copy else "Move",
                                 vec=off_v, copy=is_copy))
        self.recompute()
        self.viewport.refresh()
        self.status.showMessage(
            ("Body copied — twin joined at x " if is_copy else
             "Body moved — x ")
            + f"{off_v[0]:+g}, y {off_v[1]:+g}, z {off_v[2]:+g} mm",
            5000)

    def action_rotate_body(self):
        """Fusion Move/Copy's other half (M55): RGB rings appear around
        the body — drag one and the solid spins about that axis, live;
        release commits a parametric rotate feature."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Rotate",
                                "Nothing to rotate yet — extrude or "
                                "import a solid first.")
            return
        lo = np.asarray(self.doc.result.bounding_box[0], float)
        hi = np.asarray(self.doc.result.bounding_box[1], float)
        self._rotate_center = (lo + hi) / 2.0
        self._rotate_radius = 0.6 * float(np.max(hi - lo))
        self.viewport.begin_rotate(self._rotate_center,
                                   self._rotate_radius)
        self.status.showMessage(
            "Drag a coloured ring to spin the body — release commits, "
            "Esc cancels", 6000)

    def _on_rotate_drag(self, payload):
        """Live preview through the renderer's rotation matrix; the
        release commits a RotateFeature."""
        if payload.get("cancel") or "rad" not in payload:
            self._renderer.set_preview_rot(None)
            self.viewport.update()
            self.status.showMessage("Rotate cancelled", 2500)
            return
        axis_i = int(payload["axis"])
        e = np.eye(3)[axis_i]
        c = np.asarray(payload["center"], float)
        rad = float(payload["rad"])
        if payload.get("live"):
            self._renderer.set_preview_rot((c, e, rad))
            self.viewport.update()
            return
        self._renderer.set_preview_rot(None)
        if abs(rad) < np.deg2rad(0.1):
            self.viewport.update()
            self.status.showMessage("Rotate cancelled", 2500)
            return
        deg = float(np.rad2deg(rad))
        is_copy = bool(payload.get("copy", False))
        self._capture()
        self.doc.add(RotateFeature(
            name=f"{'Copy' if is_copy else 'Rotate'} "
                 f"{'xyz'[axis_i]} {deg:+.1f}\u00b0",
            center=tuple(float(v) for v in c),
            axis=tuple(float(v) for v in e), angle_deg=deg,
            copy=is_copy))
        self.recompute()
        self.viewport.refresh()
        self.status.showMessage(
            (f"Copied & rotated {deg:+.1f}\u00b0 about "
             f"{'XYZ'[axis_i]} — twins joined" if is_copy else
             f"Body rotated {deg:+.1f}\u00b0 about "
             f"{'XYZ'[axis_i]} through its centre"), 5000)

    def action_primitive(self):
        """Fusion Create ▸ Primitive (M65): box, cylinder or sphere,
        dialled in document measures and dropped as its own parametric
        contribution — the fastest way to start (or grow) a part."""
        if self.doc is None:
            return
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        f = units.PER_MM[u]
        lab = units.LABEL[u]

        def num(key, label, mm, dec=2):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=dec, min=0.01)

        def freenum(key, label, mm):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=2)
        v = cmddialog.ask(self, "Primitive", [
            dict(key="kind", label="Shape", kind="combo",
                 choices=["Box", "Cylinder", "Cone", "Torus", "Sphere"],
                 default="Box", group=f"Size ({lab})"),
            num("dx", "length X", 40.0), num("dy", "length Y", 30.0),
            num("dz", "length Z", 15.0),
            num("radius", "radius", 10.0, 3),
            num("r1", "bottom radius", 12.0, 3),
            num("r2", "top radius", 4.0, 3),
            num("major", "ring radius", 20.0, 3),
            num("minor", "tube radius", 5.0, 3),
            num("height", "height", 30.0),
            dict(key="op", label="Operation", kind="combo",
                 choices=["Join", "Cut", "Intersect"], default="Join",
                 group="Boolean"),
            freenum("x", "place X", 0.0),
            freenum("y", "place Y", 0.0),
            freenum("z", "place Z", 0.0),
        ], remember_key="primitive")
        if v is None:
            return
        kind = {"Box": "box", "Cylinder": "cylinder", "Cone": "cone",
                "Torus": "torus",
                "Sphere": "sphere"}[str(v["kind"])]
        dims = ({"radius": float(v["radius"]) * f} if kind == "sphere"
                else {"radius": float(v["radius"]) * f,
                      "height": float(v["height"]) * f}
                if kind == "cylinder"
                else {"radius_bottom": float(v["r1"]) * f,
                      "radius_top": float(v["r2"]) * f,
                      "height": float(v["height"]) * f}
                if kind == "cone"
                else {"major": float(v["major"]) * f,
                      "minor": float(v["minor"]) * f}
                if kind == "torus"
                else {"dx": float(v["dx"]) * f, "dy": float(v["dy"]) * f,
                      "dz": float(v["dz"]) * f})
        n = sum(1 for g in self.doc.features
                if isinstance(g, PrimitiveFeature) and g.kind == kind) + 1
        self._capture()
        self.doc.add(PrimitiveFeature(
            name=f"{str(v['kind'])} {n}", kind=kind, dims=dims,
            op={"Join": "union", "Cut": "subtract",
                "Intersect": "intersect"}[str(v["op"])],
            placement=tuple(float(v[k]) * f for k in ("x", "y", "z"))))
        self.recompute()
        self.status.showMessage(
            f"Added {str(v['kind']).lower()} — placement is the box "
            "corner / cylinder-cone base / sphere-torus centre", 5000)

    def action_text(self):
        """Fusion's Sketch Text + Extrude as one honest command (M76):
        emboss or engrave a line of text.  Glyph outlines tessellate
        from the system font — every island (and its counters) lands as
        its own parametric extrude, so undo, recompute and Change
        Parameters treat them like any other wall."""
        if self.doc is None:
            return
        from ..core.text import glyph_regions
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        f = units.PER_MM[u]
        lab = units.LABEL[u]

        def num(key, label, mm, dec=2, mn=0.01):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=dec, min=mn)
        v = cmddialog.ask(self, "Text", [
            dict(key="text", label="Text", kind="text",
                 default="TRACER", group="Content"),
            num("height", "glyph height", 12.0),
            num("depth", "depth", 1.5),
            dict(key="op", label="Operation", kind="combo",
                 choices=["Emboss (join)", "Engrave (cut)"],
                 default="Emboss (join)", group="Content"),
            dict(key="plane", label="Sketch plane", kind="combo",
                 choices=["XY", "XZ", "YZ"], default="XY",
                 group="Placement"),
            num("x", "centre X", 0.0, mn=-1e6), num("y", "centre Y", 0.0,
                                                    mn=-1e6),
            num("z", "plane height", 0.0, mn=-1e6),
        ])
        if v is None:
            return
        txt = str(v["text"])
        regs = glyph_regions(txt, float(v["height"]) * f)
        if not regs:
            QMessageBox.information(self, "Text",
                                    "Nothing to draw — type some text "
                                    "first (spaces alone won't do).")
            return
        self._capture()
        op = ("subtract" if str(v["op"]).startswith("Engrave")
              else "union")
        depth = float(v["depth"]) * f
        plane = str(v["plane"])
        place = tuple(float(v[k]) * f for k in ("x", "y", "z"))
        for i, reg in enumerate(regs):
            self.doc.add(ExtrudeFeature(
                name=f"Text \u201c{txt}\u201d {i + 1}",
                outer=np.asarray(reg["outer"], float),
                holes=[np.asarray(h, float) for h in reg["holes"]],
                height=depth, plane=plane, placement=place, op=op))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"{'Engraved' if op == 'subtract' else 'Embossed'} "
            f"\u201c{txt}\u201d — {len(regs)} glyph"
            f"{'s' if len(regs) > 1 else ''}", 5000)

    def action_combine(self):
        """Fusion's Combine (M64): Join / Cut / Intersect the body with
        a placed primitive tool — bosses, gussets and trims without a
        single sketch line."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.warning(self, "Combine",
                                "Nothing to combine into yet — extrude "
                                "or import a solid first.")
            return
        lo = np.asarray(self.doc.result.bounding_box[0], float)
        hi = np.asarray(self.doc.result.bounding_box[1], float)
        c = (lo + hi) / 2.0
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        f = units.PER_MM[u]
        lab = units.LABEL[u]

        def num(key, label, mm, dec=2):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=dec)
        v = cmddialog.ask(self, "Combine", [
            dict(key="tool", label="Tool shape", kind="combo",
                 choices=["Box", "Cylinder", "Cone", "Torus", "Sphere"],
                 default="Box", group=f"Tool ({lab})"),
            num("dx", "length X", 20.0), num("dy", "length Y", 20.0),
            num("dz", "length Z", 20.0),
            num("radius", "radius", 8.0, 3),
            num("r1", "bottom radius", 12.0, 3),
            num("r2", "top radius", 4.0, 3),
            num("major", "ring radius", 15.0, 3),
            num("minor", "tube radius", 4.0, 3),
            num("height", "height", 30.0),
            dict(key="op", label="Operation", kind="combo",
                 choices=["Join", "Cut", "Intersect"], default="Join",
                 group="Boolean"),
            num("cx", "centre X", float(c[0])),
            num("cy", "centre Y", float(c[1])),
            num("cz", "centre Z", float(c[2])),
        ], remember_key="combine")
        if v is None:
            return
        tool = {"Box": "box", "Cylinder": "cylinder", "Cone": "cone",
                "Torus": "torus",
                "Sphere": "sphere"}[str(v["tool"])]
        dims = ({"radius": float(v["radius"]) * f} if tool == "sphere"
                else {"radius": float(v["radius"]) * f,
                      "height": float(v["height"]) * f}
                if tool == "cylinder"
                else {"radius_bottom": float(v["r1"]) * f,
                      "radius_top": float(v["r2"]) * f,
                      "height": float(v["height"]) * f}
                if tool == "cone"
                else {"major": float(v["major"]) * f,
                      "minor": float(v["minor"]) * f}
                if tool == "torus"
                else {"dx": float(v["dx"]) * f, "dy": float(v["dy"]) * f,
                      "dz": float(v["dz"]) * f})
        op = {"Join": "union", "Cut": "subtract",
              "Intersect": "intersect"}[str(v["op"])]
        self._capture()
        self.doc.add(CombineFeature(
            name=f"Combine {tool}", tool=tool, dims=dims, op=op,
            center=tuple(float(v[k]) * f for k in ("cx", "cy", "cz"))))
        self.recompute()
        self.status.showMessage(
            f"Combined ({str(v['op']).lower()}) a {tool} into the body",
            5000)

    def _sync_holes(self, sid, payload):
        """Sketch re-edit through the extrude path: holes stay glued to
        their circles (moved circles move holes, deleted circles delete
        theirs).  Caller captures first; returns True if anything changed.
        """
        holes = [f for f in self.doc.features
                 if isinstance(f, HoleFeature) and f.sid == sid]
        if not holes:
            return False
        m = model_from_dict(payload)
        circles = [c for c in m.sketch.circles if not c.construction]
        u, v = plane_uv(m.plane, m.axes)
        u, v = np.asarray(u, float), np.asarray(v, float)
        origin = np.asarray(m.origin, float)
        changed = False
        for f in list(holes):
            old = [c for c in (model_from_dict(f.sketch).sketch.circles
                               if f.sketch else []) if not c.construction]
            j = None
            # 1. same circle = same coords in the previous payload (survives
            #    deletions, which shift everyone else's index)
            if f.cidx < len(old):
                c0 = old[f.cidx]
                for i, c in enumerate(circles):
                    if (abs(c.c.x - c0.c.x) < 1e-9
                            and abs(c.c.y - c0.c.y) < 1e-9
                            and abs(c.r - c0.r) < 1e-9):
                        j = i
                        break
            # 2. still sitting exactly under the drilled centre
            if j is None:
                for i, c in enumerate(circles):
                    w = origin + u * float(c.c.x) + v * float(c.c.y)
                    if (np.linalg.norm(w - np.asarray(f.center, float)) < 1e-6
                            and abs(float(c.r) - f.radius) < 1e-9):
                        j = i
                        break
            # 3. nothing moved to meet it, and no circles vanished: assume
            #    the one at the same index is this hole's circle, moved
            if (j is None and old and f.cidx < len(old)
                    and len(circles) >= len(old) and f.cidx < len(circles)):
                j = f.cidx
            if j is None:
                self.doc.features.remove(f)       # its circle is gone
                changed = True
                continue
            c = circles[j]
            f.cidx = j
            f.center = tuple(origin + u * float(c.c.x) + v * float(c.c.y))
            f.radius = float(c.r)
            kind = (" counterbore" if f.cb_radius > f.radius else
                    " countersink" if f.cs_radius > f.radius else "")
            f.name = f"Hole Ø{2 * f.radius:g}" + kind
            f.sketch = dict(payload)
            changed = True
        return changed

    def action_sweep(self):
        """Fusion Sweep (v1: circular profile): the sketch's circle sweeps
        along its loose line/arc chain — tubes, handles, rods, gaskets."""
        if self.doc is None:
            return
        m = self.sketch.model
        if m is None:
            QMessageBox.information(
                self, "Sweep",
                "Sweep runs from a sketch: draw ONE circle (the profile) "
                "plus a connected chain of lines and/or arcs (the path).")
            return
        from ..core.sweep import path_chain
        try:
            pts, closed = path_chain(m)
        except ValueError as e:
            QMessageBox.warning(self, "Sweep", str(e))
            return
        r = float([c for c in m.sketch.circles
                   if not c.construction][0].r)
        payload = model_to_dict(m)
        owned = [f for f in self.doc.features
                 if isinstance(f, SweepFeature) and f.sid == m.sid]
        self._capture()
        if owned:                                   # re-sweep: update in place
            f = owned[0]
            for extra in owned[1:]:
                self.doc.features.remove(extra)
            f.radius, f.closed = r, bool(closed)
            f.path = [list(map(float, p)) for p in pts]
            f.name = f"Sweep Ø{2 * r:g}"
            f.sketch = dict(payload)
        else:
            self.doc.add(SweepFeature(
                name=f"Sweep Ø{2 * r:g}", radius=r,
                path=[list(map(float, p)) for p in pts],
                closed=bool(closed), plane=m.plane,
                placement=tuple(map(float, m.origin)), axes=m.axes,
                sketch=dict(payload), sid=m.sid))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Swept Ø{2 * r:g} tube along the "
            + ("closed path" if closed else "open path"), 5000)

    def _sync_sweeps(self, sid, payload):
        """Sketch re-edit committed: re-extract circle + path for sweeps
        born from this sketch; drop them if the recipe stopped working."""
        sweeps = [f for f in self.doc.features
                  if isinstance(f, SweepFeature) and f.sid == sid]
        if not sweeps:
            return False
        from ..core.sweep import path_chain
        m = model_from_dict(payload)
        try:
            pts, closed = path_chain(m)
            r = float([c for c in m.sketch.circles
                       if not c.construction][0].r)
        except (ValueError, IndexError):
            for f in sweeps:                        # circle/path is gone
                self.doc.features.remove(f)
            return True
        keep = sweeps[0]
        for extra in sweeps[1:]:
            self.doc.features.remove(extra)
        keep.radius, keep.closed = r, bool(closed)
        keep.path = [list(map(float, p)) for p in pts]
        keep.name = f"Sweep Ø{2 * r:g}"
        keep.sketch = dict(payload)
        return True

    def _loft_candidates(self):
        """Every sketch in the document with exactly one closed outline,
        as [(sid, label, section-dict)] in feature order."""
        from ..core.loft import section_from_payload
        cands, seen = [], set()
        for f in self.doc.features:
            sid = getattr(f, "sid", None)
            if sid is None or not getattr(f, "sketch", None) or sid in seen:
                continue
            try:
                sec = section_from_payload(sid, f.sketch)
            except ValueError:
                continue          # this sketch has no single closed profile
            seen.add(sid)
            cands.append((sid, f.sketch.get("name") or f.name, sec))
        return cands

    def action_loft(self):
        """Fusion Loft: blend the closed profiles of TWO OR MORE sketches
        — base through middles to top, optionally a closed ring, any plane."""
        if self.doc is None:
            return
        cands = self._loft_candidates()
        ans = LoftDialog.ask(self, [(s, label) for s, label, _ in cands])
        if ans is None:
            return
        if isinstance(ans, dict):              # dialog: {sids, closed}
            sids = tuple(ans["sids"])
            closed = bool(ans.get("closed", False))
        else:                                  # bare tuple (no ring)
            sids, closed = tuple(ans), False
        if len(sids) < 2 or len(set(sids)) != len(sids):
            QMessageBox.information(
                self, "Loft", "Blend two or more DIFFERENT sketches.")
            return
        by_sid = {s: sec for s, _label, sec in cands}
        secs = [dict(by_sid[s]) for s in sids]
        names = [next(l for s, l, _ in cands if s == sid) for sid in sids]
        try:                            # validate before touching history
            LoftFeature(name="loft", sections=secs, closed=closed).build()
        except ValueError as e:
            QMessageBox.warning(
                self, "Loft",
                str(e) + " — the two profiles must sit on different planes "
                         "(sketch-on-face gives the second one an offset).")
            return
        self._capture()
        if closed:
            span = f"{names[0]} \u27f3 {len(names)}"
            name = f"Ring loft {names[0]} through {len(names)}"
        elif len(names) == 2:
            span = f"{names[0]} to {names[-1]}"
            name = f"Loft {span}"
        else:
            span = f"{names[0]} through {len(names)}"
            name = f"Loft {span}"
        self.doc.add(LoftFeature(name=name, sections=secs, closed=closed))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            ("Lofted a closed ring through "
             f"{len(names)} — {span}" if closed else f"Lofted {span}"), 5000)

    def _sync_lofts(self, sid, payload):
        """A source sketch was re-edited: rebuild the loft's section for
        it; drop lofts whose profile stopped being loftable."""
        from ..core.loft import section_from_payload
        changed = False
        for f in list(self.doc.features):
            if not isinstance(f, LoftFeature):
                continue
            if not any(s.get("sid") == sid for s in f.sections):
                continue
            try:
                new = section_from_payload(sid, payload)
            except ValueError:
                self.doc.features.remove(f)      # its profile is gone
                changed = True
                continue
            f.sections = [dict(new) if s.get("sid") == sid else s
                          for s in f.sections]
            changed = True
        return changed

    def _update_sketch_features(self, sid, profiles, payload, capture=True):
        """Re-edit: swap profiles in the features born from this sketch,
        keeping each one's height/angle; add/remove features to match."""
        group = [f for f in self.doc.features
                 if isinstance(f, (ExtrudeFeature, RevolveFeature))
                 and f.sid == sid]
        if not group:
            return
        if capture:
            self._capture()
        for i, (outer, holes) in enumerate(profiles):
            if i < len(group):
                f = group[i]
                f.outer = np.asarray(outer)
                f.holes = [np.asarray(h) for h in holes]
                f.region = i
                f.sketch = dict(payload, regions=len(profiles), region=i)
            else:
                src = group[-1]
                extra = dict(name=f"{payload['name']} #{i + 1}",
                             outer=np.asarray(outer),
                             holes=[np.asarray(h) for h in holes],
                             op=src.op, plane=src.plane,
                             axes=src.axes, placement=src.placement,
                             sid=sid,
                             sketch=dict(payload, regions=len(profiles),
                                         region=i),
                             region=i)
                if isinstance(src, RevolveFeature):
                    self.doc.add(RevolveFeature(angle=src.angle, **extra))
                else:
                    self.doc.add(ExtrudeFeature(height=src.height, **extra))
        for f in group[len(profiles):]:     # regions shrank: drop stale features
            self.doc.features.remove(f)
        self.doc.dirty = True

    def _make_sketch_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(6)
        self._tool_btns = {}
        for tool, label in (("select", "Select"), ("line", "Line"),
                            ("rect", "Rect"), ("circle", "Circle"),
                            ("ellipse", "Ellipse"),
                            ("slot", "Slot"), ("poly", "Poly"), ("arc", "Arc")):
            b = QPushButton(label, checkable=True,
                            clicked=lambda checked, t=tool: self._pick_tool(t))
            b.setProperty("tb", True)
            bl.addWidget(b)
            self._tool_btns[tool] = b
        self._sketch_project_btn = QPushButton(
            "Project",
            clicked=lambda checked=False: self._project_model_edges())
        self._sketch_project_btn.setProperty("tb", True)
        self._sketch_project_btn.setToolTip(
            "Project — lay the model edges crossing this plane under "
            "the cursor as reference geometry (Fusion's Project)")
        bl.addWidget(self._sketch_project_btn)
        self._sketch_mirror_btn = QPushButton(
            "Mirror", clicked=lambda checked=False: self.sketch.act_mirror())
        self._sketch_mirror_btn.setProperty("tb", True)
        self._sketch_mirror_btn.setToolTip(
            "Mirror — Shift+M: pick a line FIRST plus the geometry, "
            "and the copies land about it")
        bl.addWidget(self._sketch_mirror_btn)
        self._snap_btn = QPushButton("Snap to grid", checkable=True,
                                     clicked=lambda c: self.sketch
                                     .set_grid_snap(c))
        self._snap_btn.setProperty("tb", True)
        self._snap_btn.setToolTip("Snap drawing clicks to grid "
                                  "intersections")
        bl.addWidget(self._snap_btn)
        # Fusion's constraint voice on the toolbar (M73): fully / dof
        self._sketch_state = QLabel("")
        self._sketch_state.setStyleSheet("color:#9ab0c8; padding:0 8px;")
        bl.addWidget(self._sketch_state)
        bl.addStretch(1)
        back = QPushButton("← Back")
        back.setProperty("tb", True)
        back.setToolTip("Return to the 3D model without extruding")
        back.clicked.connect(lambda: self._show_page(self.viewport))
        bl.insertWidget(bl.count() - 1, back)
        done = QPushButton("Extrude… (X)")
        done.setProperty("tb", True)
        done.clicked.connect(lambda: self.sketch.finish())
        bl.addWidget(done)
        rev = QPushButton("Revolve… (⇧R)")
        rev.setProperty("tb", True)
        rev.setToolTip("Sweep the profile 360° about the sketch vertical axis")
        rev.clicked.connect(lambda: self.sketch.finish(revolve=True))
        bl.addWidget(rev)
        hole = QPushButton("Hole… (Ctrl+H)")
        hole.setProperty("tb", True)
        hole.setToolTip("Drill every circle in this sketch into the solid")
        hole.clicked.connect(self.action_hole)
        bl.addWidget(hole)
        sweep = QPushButton("Sweep… (W)")
        sweep.setProperty("tb", True)
        sweep.setToolTip("Sweep this sketch's circle along its line/arc "
                         "path — tube, handle, rod")
        sweep.clicked.connect(self.action_sweep)
        bl.addWidget(sweep)
        self.sketch = SketchCanvas()
        self.sketch.profiles_ready.connect(self._on_profiles)
        self.sketch.state_changed.connect(self._on_sketch_state)
        self._wire_sketch_params(self.sketch)      # M89 fx sees the sheet
        self._snap_btn.setChecked(self.sketch._snap_grid)
        lay.addWidget(bar)
        lay.addWidget(self.sketch, 1)
        return page

    def _wire_sketch_params(self, cv):
        """M89: hand the editor a live look at the parameter sheet —
        fx is validated and applied in the document's measures, so a
        dimension speaks the same grammar as the rebuild does."""
        def provide():
            if self.doc is None or not self.doc.params:
                return {}, 1.0
            from ..core import units
            try:
                return (params.resolve(self.doc.params),
                        units.PER_MM[self.doc.units])
            except Exception:                 # broken sheet: fx declines
                return {}, 1.0
        cv._params_provider = provide

    def _on_sketch_state(self, res):
        """Toolbar constraint voice (M73): Fusion says when a sketch is
        done being tamed; so do we."""
        s = getattr(self.sketch.model, "sketch", None)
        empty = s is None or not (s.points or s.lines or s.circles
                                  or s.arcs)
        if res is None or empty:
            self._sketch_state.setText("")
        elif not res.converged or getattr(res, "conflicting", []):
            n = len(getattr(res, "conflicting", []))
            txt = (f"\u26a0 {n} conflicting constraint"
                   + ("" if n == 1 else "s")
                   if n else "\u26a0 conflicting constraints")
            if getattr(res, "redundant", []):
                txt += f" \u00b7 {len(res.redundant)} redundant"
            self._sketch_state.setText(txt)
        elif res.dof == 0:
            self._sketch_state.setText(
                "Sketch fully constrained"
                + (f" \u00b7 {len(res.redundant)} redundant"
                   if getattr(res, "redundant", []) else ""))
        else:
            self._sketch_state.setText(f"Sketch under-constrained "
                                       f"\u00b7 {res.dof} dof free"
                                       + (f" \u00b7 {len(res.redundant)} "
                                          f"redundant"
                                          if getattr(res, "redundant", [])
                                          else ""))

    def _pick_tool(self, tool: str):
        self.sketch.set_tool(tool)
        for t, b in self._tool_btns.items():
            b.setChecked(t == tool)

    # ---- document lifecycle ---------------------------------------------------
    def _capture(self):
        """Snapshot current document as an undo point (before a mutation)."""
        if self.doc is None:
            return
        import json
        self._undo.append(json.dumps(self.doc.to_dict()))
        if len(self._undo) > 60:
            self._undo.pop(0)
        self._redo.clear()
        self._unsaved = True

    def undo(self):
        import json
        if self.stack.currentWidget() is self._sketch_page:
            self.status.showMessage("Press X to update the solid before "
                                    "undoing document changes", 4000)
            return
        if not self._undo or self.doc is None:
            self.status.showMessage("Nothing to undo", 2500)
            return
        self._redo.append(json.dumps(self.doc.to_dict()))
        self.doc = Document.from_dict(json.loads(self._undo.pop()))
        self._adopt_doc()

    def redo(self):
        import json
        if self.stack.currentWidget() is self._sketch_page:
            self.status.showMessage("Finish the sketch first", 4000)
            return
        if not self._redo or self.doc is None:
            self.status.showMessage("Nothing to redo", 2500)
            return
        self._undo.append(json.dumps(self.doc.to_dict()))
        self.doc = Document.from_dict(json.loads(self._redo.pop()))
        self._adopt_doc()

    def _adopt_doc(self):
        self.rail.tree.set_document(self.doc)
        self.timeline.set_document(self.doc)
        self.viewport.set_document(self.doc)
        self.viewport.refresh(fit=False)
        if self._drawing_page is not None:            # M96: sheets too
            idx = self.drawing.sheet_idx              # keep the same sheet
            self.drawing.set_document(self.doc,
                                      idx=None if idx < 0 else idx)
        self._update_status()
        self._apply_appearance()
        self._apply_units()

    def new_document(self, doc: Document | None = None):
        self.doc = doc or Document("Untitled")
        self.file_path = None
        self._editing_sid = None
        self._unsaved = False
        self._undo.clear()
        self._redo.clear()
        self.rail.tree.set_document(self.doc)
        self.timeline.set_document(self.doc)
        self.viewport.set_document(self.doc)
        self._update_status()
        self._on_face_selection()
        self._apply_appearance()
        self._apply_units()

    # ---- autosave & crash recovery (M67) ---------------------------------------
    def _recovery_dir(self) -> Path:
        d = Path(str(QSettings().value(
            "paths/recovery_dir",
            str(Path.home() / ".local" / "share" / "tracer-studio"
                / "recovery"))))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _autosave_file(self) -> Path:
        stem = self.file_path.stem if self.file_path else "untitled"
        return self._recovery_dir() / f"{stem}.autosave.tracer"

    def _autosave(self):
        """Every successful recompute mirrors the document to disk, so a
        crash loses at most the last unsaved edit."""
        if self.doc is None:
            return
        try:
            from datetime import datetime
            self._autosave_file().write_text(json.dumps(dict(
                path=str(self.file_path) if self.file_path else None,
                saved=datetime.now().isoformat(timespec="seconds"),
                doc=self.doc.to_dict())))
        except Exception:                 # the safety net never bites
            pass

    def _clear_autosave(self):
        try:
            p = self._autosave_file()
            if p.exists():
                p.unlink()
        except Exception:
            pass

    def maybe_recover(self) -> bool:
        """Startup offer: an autosave from a previous crash can be
        restored, or thrown away. Called by tracer.app.main(), not by
        the constructor, so headless tests never see the prompt."""
        best = None
        for p in self._recovery_dir().glob("*.autosave.tracer"):
            try:
                mt = p.stat().st_mtime
            except OSError:
                continue
            if best is None or mt > best[0]:
                best = (mt, p)
        if best is None:
            return False
        p = best[1]
        try:
            payload = json.loads(p.read_text())
        except Exception:
            p.unlink(missing_ok=True)
            return False
        where = (f" for {payload['path']}" if payload.get("path")
                 else " (unsaved document)")
        ans = QMessageBox.question(
            self, "Recover unsaved work",
            f"An autosave from {payload.get('saved', 'earlier')}"
            f"{where} was found. Restore it?",
            QMessageBox.StandardButton.Open | QMessageBox.Discard,
            QMessageBox.StandardButton.Open)
        if ans != QMessageBox.StandardButton.Open:
            p.unlink(missing_ok=True)
            return False
        try:
            doc = Document.from_dict(payload["doc"])
            doc.recompute()
        except Exception as e:
            QMessageBox.warning(self, "Recovery failed", str(e))
            return False
        self.new_document(doc)
        sp = payload.get("path")
        self.file_path = Path(sp) if sp else None
        self._unsaved = True
        self._update_title()
        self.status.showMessage(
            "Recovered unsaved work — review it and save", 6000)
        return True

    def _update_title(self):
        name = self.file_path.name if self.file_path else (
            (self.doc.title if self.doc else "Untitled") + ("" if not self.doc or not self.doc.dirty else " •"))
        self.setWindowTitle(f"{name} — Tracer Studio")
        if hasattr(self, "ribbon"):
            self.ribbon.set_title(name)

    def action_save(self, as_new: bool = False):
        if self.doc is None:
            return
        if self.file_path is None or as_new:
            start = str(self.file_path or (Path.home() / f"{self.doc.title}.tracer"))
            path, _ = QFileDialog.getSaveFileName(
                self, "Save document", start, "Tracer Studio document (*.tracer)")
            if not path:
                return
            self.file_path = Path(path)
            self.doc.title = self.file_path.stem
        try:
            fio.save_document(self.doc, self.file_path)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        self.status.showMessage(f"Saved {self.file_path}", 5000)
        self.doc.dirty = False
        self._unsaved = False
        self._update_title()
        self._note_recent(self.file_path)
        self._clear_autosave()

    # ---- recent files (M58) -------------------------------------------------------
    def _recents(self):
        v = QSettings().value("files/recent", [])
        if v is None:               # PySide6 reads a stored empty list
            v = []                  # ("@Invalid()") back as None
        if isinstance(v, str):
            v = [v] if v else []
        return [Path(p) for p in v]

    def _note_recent(self, path):
        p = Path(path)
        items = [q for q in self._recents() if q != p]
        items.insert(0, p)
        QSettings().setValue("files/recent",
                             [str(q) for q in items[:8]])
        self._rebuild_recents()

    def _rebuild_recents(self):
        self.m_recent.clear()
        items = [p for p in self._recents() if p.exists()]
        if not items:
            self.m_recent.addAction("(empty)").setEnabled(False)
            return
        for p in items:
            act = self.m_recent.addAction(
                p.name, lambda checked=False, q=p: self._open_path(q))
            act.setToolTip(str(p))
        self.m_recent.addSeparator()
        self.m_recent.addAction(
            "Clear", lambda checked=False: (
                # remove, don't setValue([]): PySide6 round-trips an
                # empty list as None and poisons the next launch
                QSettings().remove("files/recent"),
                self._rebuild_recents()))

    def _open_path(self, path):
        try:
            doc = fio.load_document(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.new_document(doc)
        self.file_path = Path(path)
        self._note_recent(path)
        self._clear_autosave()
        self._update_title()
        self.status.showMessage(f"Opened {Path(path).name}", 5000)

    def action_open(self):
        start = str(self.file_path.parent if self.file_path else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open document", start,
            "Tracer Studio document (*.tracer);;Legacy Forma document (*.forma)")
        if not path:
            return
        self._open_path(path)

    def recompute(self):
        try:
            self.doc.recompute()
        except Exception as e:  # kernel error must not kill the app
            QMessageBox.warning(self, "Recompute failed", str(e))
            return
        # Keep every view following self.doc, even if a host code swapped
        # the document in directly (scripts, embedding). The viewport gets
        # attach() — refresh without re-fitting the camera.
        if self.viewport._doc is not self.doc:
            self.viewport.attach(self.doc)
        if self.rail.tree._doc is not self.doc:
            self.rail.tree.set_document(self.doc)
        if self.timeline.bar.doc is not self.doc:
            self.timeline.set_document(self.doc)
        self.viewport.refresh()
        self.rail.tree.reload()
        self.timeline.bar.update()
        if self._drawing_page is not None and \
                self.stack.currentWidget() is self._drawing_page:
            self.drawing.resolve_dims()        # M94: follow the stretch
            self.drawing.update()              # M93: live views refresh
        self._apply_appearance()
        self._apply_units()
        self._update_status()
        self._autosave()
        self._on_face_selection()

    def _update_status(self):
        n = len(self.doc.features) if self.doc else 0
        vol = ""
        if self.doc and self.doc.result is not None:
            vol = f" · volume {self.doc.result.volume:,.1f} mm³"
        self.status.showMessage(f"{self.doc.title if self.doc else ''}"
                                f" — {n} feature{'s' if n != 1 else ''}"
                                f"{vol} · units "
                                f"{units.LABEL.get(self.doc.units, 'mm')}")
        self._update_title()

    # ---- slots ---------------------------------------------------------------
    def action_new(self):
        self.new_document()
        self._clear_autosave()

    def action_view(self, kind: str):
        if kind == "fit":
            if self.viewport._bbox is not None:
                self.viewport._cam.fit(self.viewport._bbox)
        else:
            self.viewport._cam.set_view(kind)
        self.viewport.update()

    def action_toggle_grid(self):
        self._renderer.show_grid = not self._renderer.show_grid
        self.viewport.update()

    def action_toggle_edges(self):
        self._renderer.show_edges = not self._renderer.show_edges
        self.viewport.update()

    def action_export(self, ext: str = ".stl"):
        if self.doc is None or self.doc.result is None:
            QMessageBox.information(self, "Nothing to export",
                                    "Add a feature first.")
            return
        name = (self.doc.title or "model").replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {ext.upper()}", str(Path.home() / f"{name}{ext}"),
            f"{ext.upper()} (*{ext})")
        if not path:
            return
        if not Path(path).suffix:
            path += ext
        try:
            out = fio.export_mesh(self.doc.result, path)
            self.status.showMessage(f"Exported {out}", 6000)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def action_export_render(self):
        """Save what's on screen as a PNG (makers post these everywhere)."""
        name = (self.doc.title if self.doc and self.doc.title else "render")
        name = name.replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export render", str(Path.home() / f"{name}.png"),
            "PNG image (*.png)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        if self.viewport.grab().save(path):
            self.status.showMessage(f"Render saved to {path}", 6000)
        else:
            QMessageBox.warning(self, "Export failed", f"Could not write {path}")

    # ---- patterns ----------------------------------------------------------------
    def _pattern_candidates(self):
        return [f for f in self.doc.features
                if not isinstance(f, (LinearPatternFeature,
                                      CircularPatternFeature,
                                      PathPatternFeature,
                                      BodyFilletFeature))
                and not f.suppressed]

    def action_path_pattern(self):
        """Fusion Pattern-on-Path (M50): the open line/arc chain of the
        current sketch is the walk — N equally spaced copies of the
        chosen feature ride it, translation first (v1)."""
        if self.doc is None or self.doc.result is None:
            return
        m = self.sketch.model
        if m is None:
            QMessageBox.information(
                self, "Pattern on Path",
                "Run this from a sketch: draw a connected OPEN chain of "
                "lines/arcs, starting it at the feature you want to "
                "repeat.")
            return
        cands = self._pattern_candidates()
        if not cands:
            QMessageBox.information(self, "Pattern on Path",
                                    "Create a feature to pattern first.")
            return
        from ..core.sweep import path_chain
        try:
            pts, closed = path_chain(m, need_circle=False)
        except ValueError as e:
            QMessageBox.warning(self, "Pattern on Path", str(e))
            return
        if closed or len(pts) < 2:
            QMessageBox.warning(
                self, "Pattern on Path",
                "The path must be an OPEN chain of lines/arcs — v1 "
                "does not loop.")
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Pattern on Path", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="count", label="Occurrences along the path",
                 kind="int", default=4, min=2, max=200, group="Pattern"),
        ], remember_key="path_pattern")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        self._capture()
        self.doc.add(PathPatternFeature(
            name=f"Path of {src.name}", op=src.op, source_uid=src.uid,
            path=[list(map(float, p)) for p in pts],
            count=int(v["count"]), plane=m.plane,
            placement=tuple(map(float, m.origin)), axes=m.axes))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Patterned {src.name} \u00d7{v['count']} along the path", 6000)

    def action_circular_pattern(self):
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            QMessageBox.information(self, "Nothing to pattern",
                                    "Create a feature first.")
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Circular Pattern", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="cx", label="Center X", kind="double", default=0.0,
                 min=-1e5, max=1e5, group="Axis"),
            dict(key="cy", label="Center Y", kind="double", default=0.0,
                 min=-1e5, max=1e5, group="Axis"),
            dict(key="ang", label="Angle", kind="double", default=360.0,
                 min=-360.0, max=360.0, decimals=1, suffix="°",
                 group="Pattern"),
            dict(key="count", label="Occurrences", kind="int", default=6,
                 min=2, max=500, group="Pattern"),
        ], remember_key="circular_pattern")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        cx, cy = v["cx"], v["cy"]
        ang, count = v["ang"], v["count"]
        self._capture()
        self.doc.add_circular_pattern(f"Circle of {src.name}", src,
                                      (cx, cy), ang, count)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Patterned {src.name}: {count}x over {ang:g}° about "
            f"({cx:g}, {cy:g})", 6000)

    def action_linear_pattern(self):
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            QMessageBox.information(self, "Nothing to pattern",
                                    "Create a feature first.")
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Linear Pattern", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="dx", label="X spacing", kind="double", default=10.0,
                 min=-1e5, max=1e5, decimals=3, group="Direction"),
            dict(key="dy", label="Y spacing", kind="double", default=0.0,
                 min=-1e5, max=1e5, decimals=3, group="Direction"),
            dict(key="dz", label="Z spacing", kind="double", default=0.0,
                 min=-1e5, max=1e5, decimals=3, group="Direction"),
            dict(key="count", label="Occurrences", kind="int", default=3,
                 min=2, max=500, group="Pattern"),
        ], remember_key="linear_pattern")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        dx, dy, dz = v["dx"], v["dy"], v["dz"]
        count = v["count"]
        self._capture()
        self.doc.add_linear_pattern(f"Pattern of {src.name}", src,
                                    (dx, dy, dz), count)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Patterned {src.name}: {count}x at ({dx:g}, {dy:g}, {dz:g}) mm", 6000)

    def _mirror_feature(self, src, plane=None, off=None):
        """Symmetric twin of ``src`` across a datum plane offset from the
        origin. Mirroring the part's mid-plane reproduces Fusion's most
        common mirror (e.g. a one-sided lug on a bracket).  Whatever the
        caller already knows (plane from a menu, values from the ribbon
        dialog) skips the prompt — what's missing lands in ONE dialog."""
        known = plane is not None
        if off is None:
            fields = [] if known else [
                dict(key="plane", label="Mirror plane", kind="combo",
                     choices=["YZ", "XZ", "XY"], group="Plane")]
            default_off = 0.0
            if known and self.doc.result is not None:
                # default to the model's own mid-plane along that normal
                n0 = np.array(MirrorFeature.NORMALS[plane[:2]], float)
                bb = self.doc.result.bounding_box
                default_off = float((bb.mean(0) * n0).sum())
            fields.append(dict(key="off", label="Plane offset",
                               kind="double", default=default_off,
                               min=-1e6, max=1e6, group="Plane"))
            v = cmddialog.ask(self, "Mirror", fields, remember_key="mirror")
            if v is None:
                return
            plane = plane if known else v["plane"]
            off = v["off"]
        else:
            plane = plane[:2]
        n = np.array(MirrorFeature.NORMALS[plane], float)
        self._capture()
        self.doc.add_mirror(f"Mirror of {src.name}", src, plane, off)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Mirrored {src.name} across {plane} @ {off:g} mm", 6000)

    def action_mirror(self):
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            QMessageBox.information(self, "Nothing to mirror",
                                    "Create a feature first.")
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Mirror", [
            dict(key="src", label="Feature to mirror", kind="combo",
                 choices=names, group="Object"),
            dict(key="plane", label="Mirror plane", kind="combo",
                 choices=["YZ", "XZ", "XY"], group="Plane"),
            dict(key="off", label="Plane offset", kind="double",
                 default=0.0, min=-1e6, max=1e6, group="Plane"),
        ], remember_key="mirror")
        if v is None:
            return
        self._mirror_feature(cands[names.index(v["src"])],
                             v["plane"], v["off"])

    # ---- solid fillet / chamfer (kernel rims + OpenCascade edges) ------------
    def _body_fillet(self, chamfer: bool):
        """Round (or bevel) every sharp edge of the whole body: circular
        rims are revolved tools in the mesh kernel (works everywhere);
        straight edges run through the OCCT bridge when present.  Lands a
        BodyFilletFeature in the timeline; the size stays parametric
        (edit → re-run) and the baked mesh keeps the file openable
        without OCCT."""
        kind = "Chamfer" if chamfer else "Fillet"
        if self.doc is None or self.doc.result is None:
            QMessageBox.information(self, f"No body to {kind.lower()}",
                                    "Create a feature first.")
            return
        size, ok = Shell.getDouble(
            self, f"{kind} body edges",
            f"{'Distance' if chamfer else 'Radius'} (mm):",
            2.0, 0.05, 1e4, 2)
        if not ok:
            return
        self._capture()
        n = sum(isinstance(f, BodyFilletFeature)
                for f in self.doc.features) + 1
        f = BodyFilletFeature(name=f"{kind}{n}", radius=size,
                              chamfer=chamfer)
        self.doc.features.append(f)
        self.doc.dirty = True
        try:
            self.doc.recompute()           # bakes the result on success
        except Exception as e:
            self.doc.features.remove(f)
            self.doc.dirty = True
            self.recompute()
            QMessageBox.warning(
                self, f"{kind} failed",
                f"{e}\n\nTry a smaller size — each fillet must fit between "
                f"the faces around its edge.")
            return
        self.viewport.refresh(fit=True)
        self.rail.tree.reload()
        self.timeline.bar.update()
        if f.n_rims and step.available():
            how = f"{f.n_rims} circular rim(s) + solid edges"
        elif f.n_rims:
            how = f"{f.n_rims} circular rim(s); solid edges need OpenCascade"
        else:
            how = "solid edges"
        self.status.showMessage(
            f"{kind}ed body edges at {size:g} mm · {how} · volume "
            f"{self.doc.result.volume:,.1f} mm³", 6000)

    def _set_fillet_size(self, feature):
        kind = "Chamfer" if feature.chamfer else "Fillet"
        old = feature.radius
        val, ok = Shell.getDouble(self, kind, "Size (mm):",
                                         old, 0.05, 1e4, 2)
        if not ok or val == old:
            return
        self._capture()
        feature.radius = val
        self.doc.dirty = True
        try:
            self.doc.recompute()
        except Exception as e:
            feature.radius = old          # cache still holds the good bake
            self.doc.dirty = True
            QMessageBox.warning(
                self, f"{kind} failed",
                f"{e}\n\nKept {kind.lower()} at {old:g} mm. Try a smaller "
                f"size.")
            self.recompute()
            return
        self.recompute()
        self.status.showMessage(f"{feature.name}: {kind.lower()} now "
                                f"{val:g} mm", 4000)

    # ---- unsaved-changes guard ---------------------------------------------------
    def closeEvent(self, ev):
        if getattr(self, "_unsaved", False):
            ans = QMessageBox.question(
                self, "Unsaved changes",
                "This document has unsaved changes. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save)
            if ans == QMessageBox.Cancel:
                ev.ignore()
                return
            if ans == QMessageBox.Save:
                self.action_save()
                if getattr(self, "_unsaved", False):   # dialog was cancelled
                    ev.ignore()
                    return
        self._clear_autosave()      # on disk or discarded: nothing to recover
        ev.accept()

    def action_import_profile(self, path=None):
        """File ▸ Import profile (M83): a DXF/SVG drawing lands as real
        sketch entities — welded at the seams so it stitches and
        extrudes like hand-drawn geometry.  No open sketch? A fresh XY
        one starts, because that is what the file came here for."""
        if self.doc is None:
            return
        if path is None:
            from PySide6.QtWidgets import QFileDialog
            path, _flt = QFileDialog.getOpenFileName(
                self, "Import profile", "",
                "Profiles (*.dxf *.svg);;DXF (*.dxf);;SVG (*.svg)")
            if not path:
                return
        try:
            ops = import2d.read(path)
        except Exception as e:
            self.status.showMessage(f"Import refused: {e}", 6000)
            return
        cv = self.sketch
        if cv is None or cv.model is None:
            self.action_new_sketch("XY")
            cv = self.sketch
        cv._push_hist()
        n = cv.model.import_ops(ops)
        cv._solve()
        cv.update()
        self.doc.dirty = True
        self.status.showMessage(
            f"Imported {n} entities from {Path(path).name} "
            "(document measures)", 6000) if n else \
            self.status.showMessage("No profile found in that file", 5000)

    def action_export_profile(self, path=None, feature=None):
        """File ▸ Export profile (M92): hand the sketch to the laser.
        DXF carries exact primitives + units, SVG the flattened paths;
        construction geometry stays home.  Works from the live editor
        or straight off a sketch feature's payload."""
        if self.doc is None:
            return
        model = None
        if feature is not None and getattr(feature, "sketch", None):
            model = model_from_dict(feature.sketch)
        elif self.sketch is not None and self.sketch.model is not None:
            model = self.sketch.model
        if model is None:
            self.status.showMessage("Nothing to export — no sketch in "
                                    "hand", 5000)
            return
        ops = export2d.sketch_ops(model)
        if not ops:
            self.status.showMessage("That sketch is empty", 4000)
            return
        if path is None:
            from PySide6.QtWidgets import QFileDialog
            name = getattr(model, "name", "profile") or "profile"
            path, _flt = QFileDialog.getSaveFileName(
                self, "Export profile", str(Path.home() / f"{name}.dxf"),
                "DXF (*.dxf);;SVG (*.svg)")
            if not path:
                return
        try:
            if path.lower().endswith(".svg"):
                n = export2d.write_svg(ops, path)
            else:
                if not path.lower().endswith(".dxf"):
                    path += ".dxf"
                n = export2d.write_dxf(ops, path)
        except Exception as e:
            self.status.showMessage(f"Export refused: {e}", 6000)
            return
        self.status.showMessage(
            f"Exported {n} entities to {Path(path).name} "
            "(millimetres)", 6000) if n else \
            self.status.showMessage("Nothing to write", 4000)

    def action_import(self):
        """Import a body (STEP / STL / OBJ / …) as a real history feature.

        Imported solids join the feature tree: they can be Cut/Joined with
        sketched geometry, suppressed, and they save inside the .tracer
        document."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import body", str(Path.home()),
            "CAD & meshes (*.step *.stp *.stl *.obj *.ply *.3mf *.glb *.gltf)")
        if not path:
            return
        ext = Path(path).suffix.lower()
        try:
            if ext in (".step", ".stp"):
                if not step.available():
                    QMessageBox.information(
                        self, "STEP import",
                        "STEP support needs the system OpenCascade and g++.\n"
                        "On Arch: sudo pacman -S opencascade\n"
                        "STL/OBJ/3MF import works on every machine.")
                    return
                solid = step.import_step(path)
            else:
                solid = fio.import_mesh(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        tr = solid.to_trimesh()
        self._capture()
        self.doc.add(ImportedFeature(
            name=Path(path).stem, verts=tr.vertices.tolist(),
            faces=tr.faces.astype(int).tolist()))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Imported {Path(path).name} — right-click it in the browser "
            "to Cut/Join with your model", 7000)

    def action_export_step(self):
        """Boundary-rep STEP export through the OpenCascade bridge."""
        if self.doc is None or self.doc.result is None:
            QMessageBox.information(self, "Nothing to export",
                                    "Add a feature first.")
            return
        if not step.available():
            QMessageBox.information(
                self, "STEP export",
                "STEP support uses the system OpenCascade + g++, which was "
                "not found on this machine.\nSTL/OBJ/3MF export works "
                "everywhere.")
            return
        name = (self.doc.title or "model").replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export STEP", str(Path.home() / f"{name}.step"),
            "STEP (*.step *.stp)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".step"
        try:
            out = step.export_step(self.doc.result, path)
            self.status.showMessage(f"Exported {out}", 6000)
        except Exception as e:
            QMessageBox.critical(self, "STEP export failed", str(e))
