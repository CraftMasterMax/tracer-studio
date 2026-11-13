"""Application shell: menus, status bar, document <-> viewport wiring."""
from __future__ import annotations

from pathlib import Path
import json
import math
import time

import numpy as np
import trimesh
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QSettings, QTimer, Signal
from PySide6.QtGui import (QAction, QActionGroup, QCursor, QKeySequence,
                           QShortcut)
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, 
                               QLabel, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSpinBox, QSplitter,
                               QStackedWidget,
                               QToolBar, QToolButton, QVBoxLayout, QWidget,
                               QDialog)

from ..core import import2d
from ..core import export2d
from ..core import fits as iso_fits
from ..core import io as fio
from ..core import logservice
from ..core.materials import MATERIALS as _MAT
from ..core import params
from ..core import printcheck
from ..core import step
from ..core.thread import ISO_COARSE
from ..core.document import (BodyFilletFeature, CircularPatternFeature,
                             CoilFeature, CombineFeature,
                             Document, DraftFeature,
                             ExtrudeFeature, FluidVolumeFeature,
                             GeometricPatternFeature,
                             HoleFeature, OffsetFaceFeature,
                             ImportedFeature, LinearPatternFeature,
                             LoftFeature, MirrorFeature, MoveFeature,
                             PathPatternFeature, RotateFeature,
                             ScaleFeature,
                             PrimitiveFeature,
                             RevolveFeature, ShellFeature, SplitFeature,
                             SweepFeature,
                             ThickenFeature,
                             ThreadFeature)
from ..core.measure import (describe, face_stats, mass_properties,
                            principal_inertia, section_properties)
from ..core.measure import extents as solid_extents
from ..core import units
from ..core.sketch.model import (SketchModel, face_axes, face_basis,
                                 model_from_dict, model_to_dict, plane_uv)
from . import icons
from . import cmddialog
from . import cmdpanel
from .commands import (MODEL_KEYS, REPEATABLE_LABELS, REPEATABLE_TARGETS,
                       collect_commands, plain)
from .palette import CommandPalette
from .hole import HoleDialog
from .loft import LoftDialog
from .messagelog import MessageLog
from .renderer import SceneRenderer
from .panels import LeftRail
from .ribbon import RibbonBar
from .shortcuts import TourDialog
from .sketcheditor import SketchCanvas, SketchPalette
from .theme import DARK
from .timeline import TimelineHost
from .viewport import Viewport
from .cmddialog import Shell

# M201 R5/R6: the operation tails - the fold reads and writes the
# accumulator of the body a feature streams into, so "what was
# already there" is the honest object for EVERY tool that asks the
# page's Operation row (extrude R5, revolve R6). Join (and the
# empty-body intersect, which intersects with NOTHING) grow no tail:
# the rest sentences stay byte-identical to their rung-era voices.
_OP_TAILS = {"Cut": " — cut out of what was already there",
             "Intersect": " — intersected with what was already there"}


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


def _density_labels(order):
    """"Name (ρ)" labels straight from core MATERIALS — the print check
    and the BOM can never disagree again.  Water (1.00) is the print
    check's sink-or-float reference, not a material."""
    out = []
    for name in order:
        rho = _MAT.get(name)
        if rho is None and name != "Water":
            continue                       # core no longer lists it
        out.append(f"{name} ({rho if rho is not None else 1.0:.2f})")
    return out


class MainWindow(QMainWindow):
    # M188 R4 [LAW-65]: the rebuild posture. DEFAULT False = "Stop and
    # Repair" — the R1-R3 law (fail -> bar parks before the fault, one
    # modal). The gear's toggle chooses "Continue (Ignore Error)".
    # Session posture, never serialized.
    continue_on_error = False

    # Density labels DERIVED from core.materials (single source of
    # truth — the materials report flagged the old hand-typed list for
    # drifting: it invented Stainless 8.00 / Nylon 1.14 / Titanium 4.50
    # that the BOM itself refuses to print).  "Name (ρ)" format stays
    # stable so QSettings values round-trip.
    _PRINT_ORDER = [                       # filaments first — maker CAD
        "PLA", "PETG", "ABS", "Nylon PA6", "TPU", "Tough resin",
        "Water", "Aluminium", "Steel", "Stainless 304", "Brass",
        "Titanium Ti-6Al-4V", "Copper",
    ]
    _MATERIAL_DENSITIES = _density_labels(_PRINT_ORDER)  # g/cm³ in label
    # M124 print fit-mode: the δ menu. 0 default = never silently lie;
    # 0.2 = the FDM line-fit folklore the interlock grammar already uses.
    _FIT_DELTAS = ("0.0 — as-modelled", "0.1 mm", "0.2 mm — FDM line-fit",
                   "0.3 mm", "0.5 mm")

    def __init__(self, renderer: SceneRenderer | None = None):
        super().__init__()
        self.setWindowTitle("Tracer Studio")
        self.resize(1280, 800)
        self.doc: Document | None = None
        self.file_path: Path | None = None
        self._undo: list[str] = []
        self._redo: list[str] = []
        # M165 R3: the repeat/adjust ring (key, stack, kind, payload).
        # Plain attrs, house style like _undo/_redo.  Populated by the
        # recorder pass at the tail of _make_actions + the live doors.
        self._cmd_ring: list[tuple] = []
        self._renderer = renderer or SceneRenderer()
        self.viewport = Viewport(self._renderer)
        self.rail = LeftRail()
        self.rail.tree.currentItemChanged.connect(self._on_tree_select)
        # M160 (FD2-L4): row hover rides the canvas — entered() is the
        # Qt mouse-tracking signal over ROWS, viewportEntered() the
        # empty-well version, row_leave() the pointer leaving the whole
        # tree (our FeatureTree addition). All three land on hover_body.
        self.rail.tree.setMouseTracking(True)
        self.rail.tree.entered.connect(self._on_tree_hover)
        self.rail.tree.viewportEntered.connect(
            lambda: self.viewport.hover_body(None))
        self.rail.tree.row_leave.connect(
            lambda: self.viewport.hover_body(None))
        # M162 (FD3): the eyes speak — bodies toggle through the kernel
        # door (_toggle_body_visible), the Bodies folder flips the AND-
        # chain LAYER (viewport.set_solid_visible) leaving every child's
        # own state latent. Plus the inline rename commit (LAW-2.3).
        self.rail.tree.eye_toggled.connect(self._on_eye_toggled)
        self.rail.tree.feature_renamed.connect(self._on_inline_rename)
        self.rail.tree.itemDoubleClicked.connect(self._tree_activated)
        self.rail.tree.feature_menu.connect(self._feature_menu)
        self.rail.tree.cplane_menu.connect(self._cplane_menu)
        self.rail.tree.caxis_menu.connect(self._caxis_menu)
        self.rail.tree.body_menu.connect(self._body_menu)
        self.rail.tree.joint_menu.connect(self._joint_menu)
        self.rail.tree.root_menu.connect(self._root_menu)
        # M190 R4 [LAW-63]: the rollup dot is a door, not decor.
        self.rail.tree.rollup_clicked.connect(self._reveal_fault_list)
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
        # M161 wiring: LAW-15 — a chip click highlights the feature's
        # RESULT on the model (the M131 body wash is our one honest
        # door to "the result"); LAW-3 — the Options gear docks its
        # MENU here, at the strip's right edge.
        self.timeline.bar.feature_clicked.connect(self._timeline_wash)
        self.timeline.bar.gear_clicked.connect(self._timeline_gear)
        self.timeline.bar.badge_clicked.connect(self._explain_feature)
        self.viewport.face_picked.connect(self._start_sketch_on_face)
        self.viewport.face_rejected.connect(
            lambda why: self.status.showMessage(why, 5000))
        self.viewport.coords.connect(self._show_coords)
        self.viewport.press_pull.connect(self._press_pull)
        self.viewport.move_drag.connect(self._on_move_drag)
        self.viewport.rotate_drag.connect(self._on_rotate_drag)
        self.viewport.context_request.connect(self._show_marking_menu)
        self.viewport.set_wheel_commands(self._wheel_commands)
        self.viewport.zoom_window.connect(self._on_zoom_window)
        self.viewport.isolation_esc.connect(self._on_isolation_esc)
        self.viewport.home_changed.connect(self._mark_dirty)
        self.viewport.section_esc.connect(self._clear_section)
        self._mark_menu = None               # open marking menu (M56)
        self._move_origin = None             # armed Move gesture (M53)
        self._move_len = 40.0
        self._rotate_center = None           # armed Rotate (M55)
        self._rotate_radius = 40.0
        self.viewport.selection_changed.connect(self._on_face_selection)
        cl.addWidget(self.timeline)
        # M118: the Message Log — Fusion's bottom dock, with the one
        # thing Fusion never had: rows carry the feature that spoke
        self._log_panel = MessageLog(self)
        self._log_panel.setVisible(False)
        self._log_panel.goto_feature.connect(self._goto_logged_feature)
        cl.addWidget(self._log_panel)
        self.setCentralWidget(center)

        self._make_actions()
        self._make_command_search()
        self._make_toolbar()
        self.status = self.statusBar()
        self._coords = QLabel("x 0.00   y 0.00   z 0.00")
        self._coords.setObjectName("dim")
        self._coords.setMinimumWidth(170)
        self._coords.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status.addPermanentWidget(self._coords)
        # M118: the always-visible error/warning counter — the log's
        # front door, one click from anywhere
        self._log_chip = QPushButton("", self.status)
        self._log_chip.setFlat(True)
        self._log_chip.setCursor(Qt.PointingHandCursor)
        self._log_chip.setToolTip("Message Log \u2014 click to "
                                  "show / hide")
        self._log_chip.clicked.connect(self._toggle_message_log)
        # M191 R2: the edit-park memory (view state of a view state):
        # the rollback position to RESTORE when the maker leaves the
        # sketch page. ARMED is the sentinel - the remembered position
        # may LEGITIMATELY be None (home), so None can never be the
        # "not parked" flag (the first cut's collision, caught by the
        # R2 gates on its first run).
        self._edit_park_on = False
        self._edit_park: int | None = None
        self.status.addPermanentWidget(self._log_chip)
        logservice.subscribe(self._update_log_chip)
        self.destroyed.connect(
            lambda: logservice.unsubscribe(self._update_log_chip))
        self._update_log_chip()
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
            # The picked faces index the VIEWPORT's stitched mesh, not the
            # fused union — M104: ask the viewport for its own pick mesh.
            mesh = self.viewport.pick_mesh()
            if mesh is None:
                return
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
        mesh = self.viewport.pick_mesh()          # the picked-face index space
        faces = np.asarray(d["faces"], int)
        if (mesh is None or faces.size == 0
                or int(faces.max()) >= len(mesh.faces)):
            self.viewport.preview_mesh(None)         # doc changed mid-drag
            self.status.showMessage("Press-Pull: stale selection — "
                                    "grab the face again", 4000)
            return
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
        # M201 R17 [SLD-CREATE-SOLID-PRIMITIVE, verbatim]: "You can use
        # the following tools to create a solid body from a primitive
        # shape:" - Box, Cylinder, Sphere, Torus, Coil, Pipe are ONE
        # TOOL EACH ("On the toolbar, click Solid > Create > Box"), so
        # the merged M65 dialog splits: the button is the pages' FIRST
        # tool (Box) and its arrow offers the family. Coil and Pipe are
        # NOT offered - the kernel does not bake them yet and a door
        # never promises what cannot land. Cone rides last, DECLARED
        # HOUSE (no page prints a Cone).
        d("primitive", "Box — drop a parametric box",
          menu_actions=[
              ("Box…", self.action_box),
              ("Cylinder…", self.action_cylinder),
              ("Sphere…", self.action_sphere),
              ("Torus…", self.action_torus),
              ("Cone… (house tool)", self.action_cone)],
          slot=None)
        d("newbody", "New body — the next feature lands in a separate body",
          lambda checked=False: self.action_new_body())
        d("text", "Text — emboss or engrave a line of text",
          lambda checked=False: self.action_text())
        d("hole", "Hole — drill every sketch circle (Ctrl+H)",
          lambda checked=False: self.action_hole())
        d("interlock",
          "Interlock — boss / snap fit / rest / lip "
          "(Fusion's Plastic family, free here)",
          lambda checked=False: self.action_interlock())
        r.design_sep()
        d("pattern", "Rectangular pattern — grid-copy a feature",
          lambda checked=False: self.action_linear_pattern())
        d("cpattern", "Circular pattern — polar-copy a feature",
          lambda checked=False: self.action_circular_pattern())
        d("mirror", "Mirror — flip a feature across a plane or axis",
          lambda checked=False: self.action_mirror())
        d("ppattern", "Pattern on path — copies walking a sketch path",
          lambda checked=False: self.action_path_pattern())
        d("geopattern", "Geometric pattern — T·R·S lattice of copies",
          lambda checked=False: self.action_geometric_pattern())
        d("scale", "Scale — resize a feature about a base point",
          lambda checked=False: self.action_scale())
        r.design_sep()
        d("fillet", "Fillet — round every sharp edge of the body",
          menu_actions=[self.act_fillet, self.act_chamfer, self.act_shell])
        d("shell", "Shell — hollow the body, open top face removed",
          lambda checked=False: self.action_shell())
        d("thread", "Thread — cut a bolt thread on a cylindrical boss face",
          lambda checked=False: self.action_thread())
        d("coil", "Coil — helical ridge: spring or boss thread",
          lambda checked=False: self.action_coil())
        d("fluid", "Fluid Volume — the body a flow would travel "
                   "around: envelope minus its tool bodies",
          lambda checked=False: self.action_fluid_volume())
        d("split", "Split body — trim the solid flush with a plane",
          lambda checked=False: self.action_split_body())
        d("draft", "Draft — lean the body's straight walls from a "
                   "fixed plane",
          lambda checked=False: self._body_draft())
        d("offsetface", "Offset face — slide one plain face, its "
                        "neighbours follow",
          lambda checked=False: self._body_offset())
        d("move", "Move body — drag the triad to slide it (Ctrl = copy)",
          lambda checked=False: self.action_move_body())
        d("rotate", "Rotate body — drag a ring to spin it (Ctrl = copy)",
          lambda checked=False: self.action_rotate_body())
        d("combine", "Combine body — Join / Cut / Intersect a placed "
          "solid", lambda checked=False: self.action_combine())
        r.design_sep()
        d("plane", "Construction plane — offset work plane (Ctrl+Shift+P)",
          lambda checked=False: self.action_construction_plane())
        d("axis", "Work axis — datum line for patterns & mirrors "
                  "(Ctrl+Shift+O)",
          lambda checked=False: self.action_work_axis())
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
        s("trim", "Trim — click pieces away with the trim tool (T)",
          lambda checked=False: self.sketch.set_tool("trim"))
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
                        ("Thicken…", self.action_thicken),
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
                self._end_sketch_view()         # M191 R2: leaving the
                self._sync_sketch_display()     #   page un-parks FIRST
                self._show_page(self.viewport)  #   (its recompute rests
        #                                       #   dirty - eyes go after)
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
        self.act_versions = QAction("Saved &Versions…", self,
                                    triggered=self.action_versions)
        self.act_revert = QAction("Revert to &Saved", self,
                                  triggered=self.action_revert_saved)
        self.act_open = QAction("&Open…", self, shortcut=QKeySequence.Open,
                                triggered=self.action_open)
        self.act_import = QAction("&Import body…", self,
                                  triggered=self.action_import)
        m_file.addActions([self.act_new, self.act_open])
        self.m_recent = m_file.addMenu("Recent Files")
        self._rebuild_recents()
        m_file.addActions([self.act_save, self.act_save_as])
        m_file.addActions([self.act_versions, self.act_revert])
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
        self.act_extrude = QAction("&Extrude profile…\tE", self,
                                   triggered=lambda: self.sketch.finish())
        self.act_revolve = QAction("&Revolve profile…", self, shortcut="Shift+R",
                                   triggered=lambda: self.sketch.finish(revolve=True))
        self.act_hole = QAction("&Hole…\tH", self,
                                triggered=lambda checked=False: self.action_hole())
        self.act_sweep = QAction("S&weep…", self, shortcut="W",
                                 triggered=lambda checked=False: self.action_sweep())
        self.act_loft = QAction("&Loft…", self, shortcut="Ctrl+L",
                                triggered=lambda checked=False: self.action_loft())
        self.act_plane = QAction("Construction &plane…", self,
                                 shortcut="Ctrl+Shift+P",
                                 triggered=lambda checked=False:
                                 self.action_construction_plane())
        self.act_axis = QAction("Work &axis…", self, shortcut="Ctrl+Shift+O",
                                triggered=lambda checked=False:
                                self.action_work_axis())
        m_sk.addActions([self.act_new_sketch, self.act_extrude,
                         self.act_revolve, self.act_hole, self.act_sweep,
                         self.act_loft, self.act_plane, self.act_axis])

        m_cr = self.menuBar().addMenu("C&reate")
        self.act_linpat = QAction("&Rectangular pattern…", self,
                                  triggered=lambda checked=False: self.action_linear_pattern())
        self.act_cirpat = QAction("C&ircular pattern…", self,
                                  triggered=lambda checked=False: self.action_circular_pattern())
        self.act_mirror = QAction("&Mirror…", self,
                                  triggered=lambda checked=False: self.action_mirror())
        m_cr.addActions([self.act_linpat, self.act_cirpat, self.act_mirror])
        m_cr.addSeparator()
        m_cr.addAction("New &body",
                       lambda checked=False: self.action_new_body())
        m_cr.addAction("Create Drawing…",
                       lambda checked=False: self.action_create_drawing())

        m_mo = self.menuBar().addMenu("Mo&dify")
        self.act_fillet = QAction("&Fillet body edges…\tF", self,
                                  triggered=lambda checked=False: self._body_fillet(False))
        self.act_chamfer = QAction("C&hamfer body edges…", self,
                                   triggered=lambda checked=False: self._body_fillet(True))
        self.act_shell = QAction("&Shell…", self,
                                 triggered=lambda checked=False: self.action_shell())
        self.act_draft = QAction("&Draft body walls…\tD", self,
                                 triggered=lambda checked=False: self._body_draft())
        # M198 R2 [SLD-OFFSET-FACES]: the page's home is Modify > Offset
        # Face.  No mnemonic letter: "&Open…" owns Alt+O and every other
        # letter in "Offset face" is taken (the "Change Parameters…"
        # precedent: a row may ride its bare-key shortcut alone).
        self.act_offset = QAction("Offset face…\tO", self,
                                  triggered=lambda checked=False: self._body_offset())
        m_mo.addActions([self.act_fillet, self.act_chamfer, self.act_shell,
                         self.act_draft, self.act_offset])
        m_mo.addSeparator()
        m_mo.addAction("Change Parameters…",
                       lambda checked=False: self.action_change_params())
        m_mo.addAction("User Parameters…", self.action_user_parameters)
        m_mo.addAction("Configurations…", self.action_configurations)
        m_mo.addAction("Move body…\tM",
                       lambda checked=False: self.action_move_body())
        m_mo.addAction("Rotate body…",
                       lambda checked=False: self.action_rotate_body())

        m_edit = self.menuBar().addMenu("&Edit")
        self.act_undo = QAction("&Undo", self, shortcut=QKeySequence.Undo,
                                triggered=self.undo)
        self.act_redo = QAction("&Redo", self, shortcut="Ctrl+Shift+Z",
                                triggered=self.redo)
        self.act_compute = QAction("Compute All", self, shortcut="Ctrl+B",
                                   triggered=self.action_recompute)
        # M165 R3: NO shortcut= here - the keys live in MODEL_KEYS (the
        # one table) and m10's shortcut-sheet law walks the Qt properties.
        # Menu entries make both searchable with zero registration.
        self.act_repeat = QAction("Repeat last\tCtrl+Shift+R", self,
                                  triggered=self.action_repeat_last)
        self.act_adjust = QAction("Adjust last…\tF9", self,
                                  triggered=self.action_adjust_last)
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        m_edit.addAction(self.act_compute)
        m_edit.addSeparator()
        m_edit.addAction(self.act_repeat)
        m_edit.addAction(self.act_adjust)

        m_view = self.menuBar().addMenu("&View")
        view_acts = []
        for label, key, view in (("Front", "1", "front"), ("Top", "2", "top"),
                                 ("Right", "3", "right"),
                                 ("Isometric", "0", "iso"),
                                 ("Fit view", "F6", "fit")):
            a = QAction(f"{label}\t{key}", self,
                        triggered=lambda checked=False, v=view:
                        self.action_view(v))
            m_view.addAction(a)
            view_acts.append(a)
        m_view.addSeparator()
        self.act_grid = QAction("Toggle grid\tG", self,
                                triggered=self.action_toggle_grid)
        self.act_edges = QAction("Toggle edges", self,
                                 triggered=self.action_toggle_edges)
        m_view.addAction(self.act_grid)
        m_view.addAction(self.act_edges)
        # M160 doors: the pickbox knob (FD8-45, one lever for click
        # tolerance AND hover preview) and the detail-measure chip
        # (FD8-34, a preference whose absence their QA calls a bug —
        # so ours ships ON).
        m_view.addSeparator()
        self.act_pick = QAction("Pick radius\u2026", self,
                                triggered=self.action_pick_radius)
        self.act_readout = QAction(
            "Show measure readout", self, checkable=True,
            checked=self.viewport.show_readout,
            triggered=self.action_readout_toggle)
        m_view.addAction(self.act_pick)
        m_view.addAction(self.act_readout)
        m_vs = m_view.addMenu("Visual Styles")
        _STYLE_KEYS = {"Shaded": "Ctrl+4", "Shaded with edges": "Ctrl+5",
                       "Ghosted": "Ctrl+6", "Wireframe": "Ctrl+7"}
        for _label in ("Wireframe", "Ghosted", "Shaded",
                       "Shaded with edges", "X-ray"):
            a = QAction(_label, self,
                        triggered=lambda checked=False, lb=_label:
                        self.action_visual_style(lb))
            if _label in _STYLE_KEYS:
                a.setShortcut(_STYLE_KEYS[_label])
            m_vs.addAction(a)
        # M113 layout layer — Fusion's Ctrl+Alt panel voices
        m_view.addSeparator()
        for label, key, what in (
                ("Show/hide ViewCube", "Ctrl+Alt+V", "cube"),
                ("Show/hide Browser", "Ctrl+Alt+B", "browser"),
                ("Show/hide Navigation bar", "Ctrl+Alt+N", "nav"),
                ("Show/hide Datum letters", "Ctrl+Alt+D", "datums"),
                ("Reset panel layout", "Ctrl+Alt+R", "reset")):
            m_view.addAction(
                QAction(label, self, shortcut=key,
                        triggered=lambda checked=False, w=what:
                        self._layout_toggle(w)))
        m_view.addSeparator()
        # M118: the log's menu door — stays honest with the chip toggle
        ml = QAction("Message Log", self, checkable=True)
        ml.toggled.connect(self._log_panel.setVisible)
        self._log_menu = ml
        m_view.addAction(ml)

        m_tools = self.menuBar().addMenu("&Tools")
        m_tools.addAction("Manage Lost Attachments\u2026",
                          lambda checked=False: self._manage_attachments())
        m_tools.addAction("Document Measures…",
                          lambda checked=False:
                          self.action_document_measures())
        m_tools.addAction("Mass properties…",
                          lambda checked=False:
                          self.action_mass_properties())
        m_tools.addAction("Interference — where bodies clash…",
                          lambda checked=False:
                          self.action_interference())
        m_tools.addAction("As-Built Joint…",
                          lambda checked=False: self.action_joint())
        m_tools.addAction("Flat Pattern — unfold a sheet…",
                          lambda checked=False:
                          self.action_flat_pattern())
        m_tools.addAction("New Sheet — parametric sheet metal…",
                          lambda checked=False:
                          self.action_new_sheet())
        m_tools.addAction("Add Flange — fold any free edge…",
                          lambda checked=False:
                          self.action_add_flange())
        m_tools.addAction("Add Fold — bend inside a leg…",
                          lambda checked=False:
                          self.action_add_fold())
        m_tools.addAction("Place Datum Identifier…",
                          lambda checked=False:
                          self.action_datum_identifier())
        m_tools.addAction("Show Extents…",
                          lambda checked=False:
                          self.action_show_extents())
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

        # M165 R3: the recorder pass - ONE post-build walk (NOT a wrapper
        # at each creation site), same traversal collect_commands uses.
        # Slots connect AFTER each command's own triggered-lambda, and
        # Qt fires in connection order: the ring holds what RAN.  The
        # palette bypass (run=act.trigger) and menu clicks ride the very
        # same slots - the recon's flagged bypass is what records.
        self._repeatable: dict[str, QAction] = {}
        for a in self._menu_action_walk():
            lab = plain(a.text())
            if lab in REPEATABLE_LABELS:
                self._repeatable[lab] = a
                a.triggered.connect(                     # noqa: B023 - the
                    lambda _c=False, k=lab: self._note_cmd(   #  default IS
                        k, "doc", "action", k))                #  the bind

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
    def _body_name_for_row(self, item):
        """Which body a browser row speaks for — the ONE resolver for
        both the M131 click wash and the M160 hover wash: a body row
        means itself, a feature/sketch row means its owning body, a
        datum or folder row means nothing (None)."""
        role = item.data(0, Qt.UserRole) if item is not None else None
        if role and self.doc is not None:
            kind, arg = role
            if kind == "body":
                return arg
            if kind in ("feature", "sketch") and isinstance(arg, int):
                feats = list(self.doc.features)
                if 0 <= arg < len(feats):
                    return getattr(feats[arg], "body", None)
        return None

    def _on_tree_select(self, cur, *_):
        """Row chosen in the browser: refresh properties (the M72 path)
        AND wash the body that row builds (M131) — a body row washes
        itself, a feature/sketch row washes its owning body, a datum or
        folder row washes nothing (clears)."""
        self.rail.props.show_feature(self.rail.tree.current_feature())
        self.viewport.emphasize_body(self._body_name_for_row(cur))

    def _on_tree_hover(self, index):
        """M160 (FD2-L4): a browser row UNDER THE MOUSE live-highlights
        its body in the canvas with the SAME glow as canvas hover — the
        probe's own words: hovering the row is "the same thing as
        hovering over the body in the design workspace". Visual only."""
        item = self.rail.tree.itemFromIndex(index)
        self.viewport.hover_body(self._body_name_for_row(item))

    def _tree_activated(self, item, col):
        role = item.data(0, Qt.UserRole) if item else None
        if not role:
            return
        # M162's crash fix (coredump 125155, QTreeView::mouseDoubleClick
        # Event on the stack): this handler runs INSIDE Qt's double-click
        # dispatch, and Qt keeps using the model index after the signal
        # returns. Every door below can rebuild the tree (activate
        # reloads it; sketch/drawing pages recompute) — freeing the rows
        # under Qt's feet was a use-after-free SIGSEGV, reachable by any
        # real double-click ever since M104 (the old tests only EMITTED
        # the signal, which has no Qt frame to straddle; M162's
        # expandsOnDoubleClick(False) repair made the live path land).
        # The role is PLAIN data, so capture it here and ride to the
        # next event-loop tick — one tick later, zero frames dangling.
        QTimer.singleShot(0, lambda: self._activate_role(role))

    def _activate_role(self, role):
        """The deferred half of _tree_activated — dispatched OUTSIDE any
        Qt event frame, so it is free to rebuild the model."""
        if self.doc is None:
            return
        kind, arg = role
        if kind == "plane":
            self.action_new_sketch(arg)
        elif kind == "cplane":
            self.action_sketch_on_plane(arg)
        elif kind == "caxis":
            self.status.showMessage(
                f"{arg}: a work axis — patterns and mirrors take it by "
                "name; right-click to delete", 5000)
        elif kind == "sketch":
            self._feature_activated(self.doc.features[arg])
        elif kind == "sheet":                 # M96: double-click a sheet
            self._open_drawing(arg)
        elif kind == "body":                  # M104: double-click → activate
            self.action_activate_body(arg)

    def _feature_activated(self, feature):
        # M161 LAW-10: "Edit Sketch... automatically rolls the timeline
        # marker back to this position, temporarily suppressing all
        # later features" — a feature HIDDEN behind the marker cannot
        # be edited, so entering its edit first rolls the marker to
        # it. (Rolling when the marker is already AT THE END is the
        # probe's [observed] extension — banked by name, not assumed.)
        if self.doc is not None:
            rb = self.doc.rollback_to
            i = (self.doc.features.index(feature)
                 if feature in self.doc.features else -1)
            if rb is not None and 0 <= i and rb <= i:
                # M191 R2: this roll MOVES the maker's band - capture
                # their spot into the park memory BEFORE it moves, so
                # leaving restores where THEY were, not where this
                # gate parked. (edit_sketch then finds the memory
                # armed and keeps it.)
                if not self._edit_park_on:
                    self._edit_park_on = True
                    self._edit_park = rb
                self._apply_rollback(i + 1)
                self.status.showMessage(
                    f"Rolled to '{feature.name}' to edit it — later "
                    "features are hidden by the marker, not deleted "
                    "(LAW-8)", 5000)
        if (isinstance(feature, (ExtrudeFeature, RevolveFeature, HoleFeature))
                and feature.sketch):
            self.edit_sketch(feature)
        elif isinstance(feature, BodyFilletFeature):
            self._set_fillet_size(feature)      # reopen the size dialog
        elif isinstance(feature, ExtrudeFeature):
            self._set_distance(feature)         # e.g. Press-Pull: no sketch
        elif isinstance(feature, OffsetFaceFeature):
            # M198 R4 [SLD-OFFSET-FACES]: "a new Offset Face feature
            # is created within the Timeline, which gives you an
            # opportunity to COME BACK AND EDIT IT LATER BY DOUBLE-
            # CLICKING ITS ICON".  The chip opens the record's OWN
            # lever (plural checks / legacy combo - one record one
            # voice); the marker law above has already parked.
            self.action_change_params(feature)
        else:
            self.status.showMessage("Feature has no editable sketch (yet)", 3000)

    # ---- M191 R2 [LAW-10, completed]: EDIT PARKS THE MARKER --------------------
    # The vendor's API doc names the behavior outright: "This process
    # mimics the behavior you see in the user interface when you
    # manually edit a sketch where Fusion AUTOMATICALLY ROLLS THE
    # TIMELINE BACK while you're editing the sketch." M161 LAW-10
    # shipped the half where the target sits BEHIND the marker; the
    # whole law is: entering ANY feature's edit parks the marker just
    # past that feature (downstream hidden, never deleted - LAW-8's
    # words), and leaving sends it HOME - or back to wherever the
    # maker had parked it BEFORE the edit. The marker is view state
    # (M88: never serialized), so the park can never poison a file.
    def _park_marker_for_edit(self, feature):
        if self.doc is None or feature not in self.doc.features:
            return
        i = self.doc.features.index(feature)
        # "just past the LAST feature" IS home (the band's OWN law,
        # _rollback_to's words); and a stale at-the-end NUMBER is
        # normalized to None, because doc.rollback_to may hold either
        # spelling of home (document.py stores int(n) unguarded).
        target = i + 1 if i + 1 < len(self.doc.features) else None
        cur = self.doc.rollback_to
        if cur is not None and cur >= len(self.doc.features):
            cur = None
        if cur != target:
            self._apply_rollback(target)

    def _end_sketch_view(self):
        """ONE un-park seam: every door that leaves the sketch page
        (Back, the Design tab, every commit path) routes here FIRST;
        outside an edit it says nothing and changes nothing."""
        if not self._edit_park_on:
            return
        prev, self._edit_park = self._edit_park, None
        self._edit_park_on = False
        if self.doc is not None and self.doc.rollback_to != prev:
            self._apply_rollback(prev)

    def _leave_sketch_page(self):
        self._end_sketch_view()       # the un-park may recompute, and
        self._sync_sketch_display()   #   recompute rests doc.dirty -
        self._show_page(self.viewport)  # so the EYES sync AFTER, and
        #                               #   their debt survives to save

    def _sync_sketch_display(self):
        """M191 R3 [per-sketch display truth]: the display flags are
        the SKETCH'S OWN EYES, stored in the file (the vendor's API
        puts isProjectedGeometryShown/areConstraintsShown on the
        Sketch object, not on the viewer) - so the Back door's discard
        drops STROKES but keeps them, exactly as M162's visibility
        rides every rollback untouched. The commit paths need no
        help: model_to_dict already carries vis into the payload.
        Deliberately NOT doc-history (eyes are not design, M162): no
        _capture here."""
        if self.doc is None or self._editing_sid is None:
            return
        vis = dict(getattr(self.sketch.model, "vis", {}) or {})
        if not vis:
            return
        for f in self.doc.features:
            if getattr(f, "sid", None) == self._editing_sid \
                    and getattr(f, "sketch", None) is not None:
                if f.sketch.get("vis") != vis:
                    f.sketch["vis"] = vis
                    self.doc.dirty = True
                return

    def _set_sketch_dims(self, feature, on):
        """M192 R7 [SKT-CREATE-DIMENSIONS, Browser tip]: the row is the
        FOURTH door on the ONE vis mouth (paint, the canvas right-click
        and the Sketch Palette eyes own the other three). A sketch OPEN
        on the canvas flips through the canvas's set_show_layer, so
        EVERY door hears it (the palette eye follows, the labels leave)
        and the file debt is paid by the M191 R3 sync. A CLOSED sketch
        flips its stored dict - that IS its truth while closed, and
        model_from_dict wakes it faithfully on open. Eyes are not
        design (M162): no doc-history row, only the dirty bit."""
        if not isinstance(getattr(feature, "sketch", None), dict):
            return
        if (feature.sid is not None and feature.sid == self._editing_sid
                and self.sketch is not None):
            self.sketch.set_show_layer("dims", on)
            self._sync_sketch_display()
            return
        vis = feature.sketch.setdefault("vis", {})
        if bool(vis.get("dims", True)) != bool(on):
            vis["dims"] = bool(on)
            if self.doc is not None:
                self.doc.dirty = True

    # ---- repeat last / adjust last (M165 R3) --------------------------------    # The memory is a ring of (key, stack, kind, payload), newest last.
    # Entries are NOT lambdas holding references: they carry strings that
    # RE-RESOLVE at replay, and a dead action/feature/dim is dropped -
    # never replayed at a stale object (the palette recents' self-heal).
    # The recorder pass connects to `triggered` AFTER each command's own
    # lambda; triggered slots fire in connection order, so the ring holds
    # what RAN, not what was attempted (plan law).  The palette bypass
    # rides the same slots (cmd:221 run=act.trigger).
    # The two-stack law applied: a replay invokes a door that ALREADY
    # journals - doc doors _capture() (doc stack), sketch doors
    # _push_hist (sketch stack).  M165 adds ZERO new capture calls.

    _RING_CAP = 12

    def _note_cmd(self, key: str, stack: str, kind: str, payload):
        e = (key, stack, kind, payload)
        if self._cmd_ring and self._cmd_ring[-1][:2] == e[:2]:
            self._cmd_ring[-1] = e          # the same command wears ONE
        else:                               #  line: replay refreshes
            self._cmd_ring.append(e)
        del self._cmd_ring[:-self._RING_CAP]

    def _menu_action_walk(self):
        """The SAME traversal collect_commands walks - menu is the source
        of truth (the law reused): submenus entered, separators skipped,
        top-level actions without a submenu included."""
        for top in self.menuBar().actions():
            sub = top.menu()
            if sub is None:
                if not top.isSeparator():
                    yield top
                continue
            walk = [sub]
            while walk:
                m = walk.pop()
                for a in m.actions():
                    if a.isSeparator():
                        continue
                    child = a.menu()
                    if child is not None:
                        walk.append(child)
                    else:
                        yield a

    def action_repeat_last(self):
        if not self._cmd_ring:
            self.status.showMessage("Nothing to repeat yet", 2500)
            return
        key, stack, kind, payload = self._cmd_ring[-1]
        on_sketch = self.stack.currentWidget() is self._sketch_page
        if stack == "doc" and on_sketch:      # two-stack guard, the undo
            self.status.showMessage(          #  law (mw:5722 family):
                f"'{key}' edits the solid - press X to finish "
                "the sketch first", 4000)     #   no silent drop
            return
        if stack == "sketch" and not on_sketch:
            self.status.showMessage(f"'{key}' belongs to the sketch - "
                                    "open one first", 3000)
            return
        if kind == "action":
            a = self._repeatable.get(key)     # re-resolve by LABEL, not
            if a is None or not a.isEnabled():#  by captured reference
                self._cmd_ring.pop()
                self.status.showMessage(f"'{key}' is gone - dropped "
                                        "from the ring", 3000)
                return
            a.trigger()                       # the door journals itself
        elif kind == "tool":                  # re-arming the dim/angle
            door = {"tool:dim": self.sketch.act_dim,
                    "tool:angle": self.sketch.act_angle}.get(payload)
            if door is not None:
                door()                        #  tool IS the repeat
        else:                                 # "chip": the editor goes
            d = self.sketch._last_dim         #  back on the last EDITED
            if (d is None or self.sketch.model is None
                    or not any(cc is d for cc in
                               self.sketch.model.sketch.constraints)):
                self._cmd_ring.pop()          #  dim died in the solve -
                self.status.showMessage("The last dimension is gone - "
                                        "dropped from the ring", 3000)
                return
            self.sketch._open_dim_editor(d)   #  honest re-seat

    def action_adjust_last(self):
        """F9 adjusts the last ARTIFACT. The PAGE decides where it lives
        - deliberate deviation from the plan's ring-head rule: the head
        may come from the other page's history, and F9 owes the user the
        artifact under their eyes. Doors are REUSED, never forked: doc
        rides the double-click door (its LAW-10 rollback applies), the
        sketch re-seats the inline chip editor."""
        if self.stack.currentWidget() is self._sketch_page:
            cv = self.sketch
            d = cv._last_dim
            if d is None or cv.model is None or not any(
                    cc is d for cc in cv.model.sketch.constraints):
                self.status.showMessage("Nothing to adjust in this "
                                        "sketch (yet)", 2500)
                return
            cv._open_dim_editor(d)
            return
        if self.doc is None or not self.doc.features:
            self.status.showMessage("Nothing to adjust yet", 2500)
            return
        feat = self.doc.features[-1]
        # M162's law: this may ride a palette trigger INSIDE a menu
        # dispatch frame - one clean tick, zero dangling views
        QTimer.singleShot(0, lambda: self._feature_activated(feat))

    # ---- feature management (context menus: timeline + browser) --------------
    def _feature_menu(self, feature, pos):
        menu = self._feature_menu_build(feature)   # M192 R7: the canvas
        menu.exec(pos)                             #  _build_menu seam

    def _feature_menu_build(self, feature):
        """The feature menu BUILT (parent-owned, not exec'd) - the same
        door the right-click rides, headless-testable: the modal exec
        belongs to the caller, so gates trigger these actions directly
        (the M164/m192 canvas-menu pattern)."""
        menu = QMenu(self)
        sketchy = (isinstance(feature, (ExtrudeFeature, RevolveFeature,
                                        HoleFeature))
                   and feature.sketch)
        if sketchy:
            menu.addAction("Edit sketch", lambda: self.edit_sketch(feature))
            act_dims = menu.addAction("Show Dimensions")   # M192 R7
            act_dims.setCheckable(True)                    #  [SKT-CREATE-
            live = (feature.sid is not None                #  DIMENSIONS,
                    and feature.sid == self._editing_sid)  #  Browser tip:
            stored = feature.sketch.get("vis") or {}       #  "right-click
            act_dims.setChecked(bool((self.sketch.model.vis if live
                                      else stored).get("dims", True)))
            act_dims.triggered.connect(                    #  a sketch and
                lambda on, f=feature:                      #   select Show
                    self._set_sketch_dims(f, bool(on)))    #   Dimensions")
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
        # (M192 R7 FIX: this function used to RE-import HoleFeature here;
        # a name imported ANYWHERE in a function is local THROUGHOUT it,
        # so the sketchy check at the top died with UnboundLocalError on
        # EVERY browser right-click since M150 - hidden because the
        # modal menu was never EXECuted by a gate (PySide swallows slot
        # exceptions headless). The Browser menu now walks a real gate.)
        if isinstance(feature, HoleFeature):
            self._datum_menu_rows(menu, "hole-axis", feature.uid,
                                  f"hole {feature.name}")
        menu.addAction("Rename…", lambda: self._rename_feature(feature))
        # M162 LAW-5.1: Find in Browser — the row lights with the dash.
        menu.addAction("Find in Browser",
                       lambda: self._find_in_browser(feature))
        menu.addSeparator()
        menu.addAction("Unsuppress" if feature.suppressed else "Suppress",
                       lambda: self._toggle_suppress(feature))
        menu.addAction("Rollback to here",
                       lambda: self._rollback_to(feature))
        if self.doc is not None and self.doc.rollback_to is not None:
            menu.addAction("End rollback",
                           lambda: self._apply_rollback(None))
        menu.addAction("Delete feature", lambda: self._delete_feature(feature))
        return menu

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

    def _timeline_wash(self, feature):
        """M161 LAW-15: a single click on a timeline chip highlights
        that feature's result on the model — through the M131 body wash
        (the feature's RESULT is the body it builds; picking the exact
        new faces of a boolean is banked with the feature-tree work).
        An empty-strip click (None) clears the highlight."""
        name = getattr(feature, "body", None) if feature is not None \
            else None
        self.viewport.emphasize_body(name)

    def _timeline_gear(self, pos):
        """M161 LAW-3: the Options button at the strip's RIGHT opens
        the timeline settings — built by _build_gear_menu (the door and
        its contents are one honest source), shown at the click."""
        self._build_gear_menu().exec(pos)

    def _build_gear_menu(self):
        """M188 R2 (LAW-64): the gear menu as a REAL QMenu, so the
        repair WALK gets its named verbs — the vendor's own words:
        "Roll to Previous" steps the marker back one feature, "Roll To
        End" sends it home and the healed band RUNS, riding to the next
        error. Each verb is enabled only when it can do something: at
        the end, End has nothing to end; with no features, Previous has
        nowhere to step. M188 R3 (LAW-65) adds the diagnostic door —
        "What's Wrong?" answers only while a fault is queued. M161
        LAW-3 owns the settings entry above, and LAW-12's destructive
        sibling below stays confirm-guarded."""
        menu = QMenu(self)
        act = menu.addAction("Hide all inactive features")
        act.setCheckable(True)
        act.setChecked(self.timeline.bar.hide_inactive)
        act.toggled.connect(lambda on: (
            setattr(self.timeline.bar, "hide_inactive", on),
            self.timeline.bar.update()))
        # M188 R4 [LAW-65]: the stop/continue CHOICE lives in the same
        # settings group - System Options, Tracer-sized. Named like the
        # vendor names it; the doc-default (unchecked) is Stop and
        # Repair, R1-R3's law.
        cont = menu.addAction("Continue rebuilding after errors")
        cont.setCheckable(True)
        cont.setChecked(self.continue_on_error)
        cont.toggled.connect(
            lambda on: setattr(self, "continue_on_error", bool(on)))
        rb = self.doc.rollback_to if self.doc is not None else None
        total = len(self.doc.features) if self.doc is not None else 0
        menu.addSeparator()
        prev = menu.addAction("Roll to Previous")
        prev.setEnabled(total > 0)
        prev.setToolTip("Step the rollback marker back one feature")
        prev.triggered.connect(self._roll_to_previous)
        end = menu.addAction("Roll To End")
        end.setEnabled(rb is not None)
        end.setToolTip("Show the whole history: the healed band runs "
                       "and rides to the next error"
                       if rb is not None else "")
        end.triggered.connect(lambda: self._apply_rollback(None))
        ff = self.doc.failed_feature if self.doc is not None else None
        wrong = menu.addAction("What's Wrong?")
        wrong.setEnabled(ff is not None)
        wrong.setToolTip("Quote the kernel's own refusal for the "
                         "queued fault" if ff is not None else "")
        wrong.triggered.connect(self._whats_wrong)
        menu.addSeparator()
        dng = menu.addAction("Delete All Features After Marker")
        dng.setEnabled(rb is not None and rb < total)
        dng.triggered.connect(self._delete_after_marker)
        return menu

    def _roll_to_previous(self):
        """LAW-64 verb one: the marker steps ONE slot back. From the
        end it lifts the last feature out of the live band; at the
        front it stays — the marker never runs off the front."""
        if self.doc is None or not self.doc.features:
            return
        cur = self.doc.rollback_to
        if cur is None:
            cur = len(self.doc.features)
        self._apply_rollback(max(0, cur - 1))

    def _whats_wrong(self):
        """M188 R3 (LAW-65): the gear's diagnostic door — the vendor's
        own name, aimed at the QUEUE HEAD. Passive by law: asking runs
        nothing."""
        if self.doc is None:
            return
        ff = self.doc.failed_feature
        if ff is None:
            return
        if ff[0] < len(self.doc.features):
            self._explain_feature(self.doc.features[ff[0]])

    def _explain_feature(self, feat):
        """M188 R5 (LAW-63): the SHARED explanation voice - the gear
        door aims it at the queue head, a chip's red BADGE DOT aims it
        at THAT feature ("never a dead badge": the icon is a button).
        LAW-67 owns the copy: state + cause + next action, at most two
        sentences, mechanistic and directive. The CAUSE is not
        paraphrased — the kernel already speaks it, so this QUOTES the
        scar verbatim and names the rung-2 verb as the next step.
        Nothing REBUILDS: no recompute, no log line. Since M190 R1 the
        door MOVES: the tree and timeline land on the culprit first
        (LAW-63 - an error report that does not navigate is a poster)."""
        if self.doc is None or feat is None:
            return
        cause = getattr(feat, "error", None)
        if not cause:
            return                      # no scar, no story
        # M190 R1 [LAW-63]: the explanation IS a door. The class does
        # not merely talk about errors - "clicking any entity in that
        # list ADVANCES YOU DIRECTLY to that feature in the tree". So
        # the click lands on the culprit BEFORE the voice speaks: the
        # tree row lights, scrolls centre and flashes (M162's reveal),
        # the timeline chip selects (M118's Message-Log idiom). When
        # the reader dismisses the sentence, the guilty row is under
        # their cursor already.
        self.rail.tree.reveal_feature(feat)
        self.timeline.bar.select_feature(feat)
        QMessageBox.information(
            self, "What's Wrong?",
            f"{feat.name} failed to rebuild: {cause}. Fix {feat.name}, "
            "then Roll To End in the timeline gear — the band runs the "
            "repair and rides to the next error.")

    def _delete_after_marker(self):
        """M161 LAW-12: the destructive sibling of the marker — a
        DISTINCT command, confirm-guarded (the probe's own boundary:
        the marker itself never deletes)."""
        if self.doc is None:
            return
        rb = self.doc.rollback_to
        total = len(self.doc.features)
        if rb is None or rb >= total:
            return
        reply = QMessageBox.warning(
            self, "Delete All Features After Marker",
            f"This permanently removes {total - rb} feature(s) after "
            f"the marker ({rb} remain). This is NOT the rollback — it "
            "cannot be undone by dragging the marker back.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        for f in list(self.doc.features)[rb:]:
            self.doc.features.remove(f)       # the house removal path
        self.doc.dirty = True
        self.doc.rollback_to = None
        self.recompute()
        self.status.showMessage(
            f"Deleted {total - rb} feature(s) after the marker "
            "(LAW-12: the destructive sibling, not the rollback)", 5000)

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
        # M162 LAW-5.3: visibility is INDEPENDENT of history — the eyes
        # ride every rollback untouched (they are document truth). The
        # PICK washes are the opposite: faces past the cutoff stop
        # existing, so the ancestry underline is cleared here (the mesh
        # refresh already retires _hover/_sel with the new face ids).
        self.rail.tree.set_ancestry(None)
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

        def dbl(key, label, mm, dec=2, mn=0.0, ang=False, plain=False):
            if plain:                 # dimensionless factor: no unit story
                # M201 R11 [UNIT-SUFFIX LAW, film-caught]: ask() DEFAULTS
                # every double to a " mm" suffix, so clearing it must be
                # EXPLICIT or a ratio wears millimetres - the R1b lesson
                # ("no millimetre suffix on an angle, anywhere") general-
                # ised: NO unit suffix on a dimensionless row, anywhere.
                # One fix here heals every plain row in the house (the
                # scale factors, the geometric pattern's scale-per-step,
                # the coil's turns) at its single source.
                spec = dict(key=key, kind="double", decimals=dec,
                            label=label, default=float(mm), suffix="")
                if mn is not None:
                    spec["min"] = mn
                fld.append(spec)
                return
            spec = dict(key=key, kind="double", decimals=dec,
                        label=f"{label} ({'\u00b0' if ang else lab})")
            spec["default"] = float(mm) if ang else round(mm / sc, 6)
            if mn is not None:
                spec["min"] = mn if ang else mn / sc
            if ang:
                # M196 R1b (film-caught lie): ask() hands every double
                # row the " mm" suffix unless it says otherwise, so the
                # angle levers read "45.0 mm" UNDER their own degree
                # label - one door, two mouths, two units.  Degrees
                # wear degrees; the millimetre rows ride the default.
                spec["suffix"] = "\u00b0"
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
            # M201 R2 [SLD-REF-EXTRUDE]: the page's Direction row and
            # its two CONDITIONAL rows (Measurement reads for Symmetric
            # only; the second distance belongs to Two Sides - "Adjust
            # the settings in step 6 independently for each side").
            # A legacy record (direction "") shows its EFFECTIVE voice,
            # so the lever never contradicts the rail.
            # M201 R4 [SLD-REF-EXTRUDE, verbatim]: "Offset (Offset or
            # Object start only): Specify distance to offset extrusion
            # from profile plane" - the Start/Offset numeric, grown in
            # PAGE ORDER (the page lists Start before Direction). The
            # page words no sign rule (silence is silence) so the
            # number is SIGNED, the house coin; the rest is whatever
            # the RECORD says (0.0 for every record ever made before
            # this rung - the lever echoes, never contradicts).
            dbl("offset", "offset from the plane", feature.offset,
                mn=None)
            combo("direction", "direction",
                  ("one", "two", "symmetric"),
                  feature._effective_direction())
            combo("measurement", "measurement (symmetric)",
                  ("whole", "half"), feature.measurement)
            # M201 R9 [SLD-REF-EXTRUDE, verbatim] "Extent Type:
            # Establishes the end point of the extrusion. Distance:
            # Extrudes to a distance that you specify | All: Extrudes
            # through all visible bodies along the extrusion
            # direction." PAGE ORDER: Extent Type (#9) sits AFTER
            # Measurement (#8) and BEFORE the distance rows. "To
            # Object" is the page's PICK and stays unpromised (R4's
            # coin). A legacy record shows the "distance" it always
            # spoke - the lever echoes, never contradicts.
            combo("extent", "extent", ("distance", "all"),
                  feature.extent)
            dbl("height2", "height 2 (second side)", feature.height2,
                mn=0.0)
            # M201 R9 [SLD-REF-EXTRUDE, verbatim] "Flip (All extent
            # type only): Flips the extrusion over the selected
            # profile plane" - the RE-AIM house coin (measured pair
            # 13,400/8,600). The WIDGET IS THE HOUSE'S (the page
            # never says checkbox or icon). Gated to All by its OWN
            # qualifier: at the distance rest the word is stored and
            # INERT (R2's conditional-row coin) - the modal lever
            # cannot open and close rows mid-command.
            check("flip", "flip (all extent only)", feature.flip)
            # M201 R8 [SLD-REF-EXTRUDE]: the thin-wall family edits
            # where it was born - PAGE ORDER puts the wall rows AFTER
            # the distance rows (Wall Thickness #14, Wall Location
            # #15). The location word opens for every record (the
            # modal lever cannot gate rows - the conditional-row law,
            # stored-and-inert at wall 0, R2's coin).
            dbl("wall", "wall thickness (0 = whole area)",
                feature.wall, mn=0.0)
            combo("wall_location", "wall location",
                  ("side 1", "side 2", "center"),
                  feature.wall_location)
        elif isinstance(feature, RevolveFeature):
            dbl("angle", "angle", feature.angle, dec=1, ang=True)
        elif isinstance(feature, HoleFeature):
            dbl("radius", "radius", feature.radius, dec=3, mn=0.05)
            check("through", "through all", feature.through)
            dbl("depth", "depth", feature.depth, mn=0.05)
            # M201 R7: the drill point edits where it was born (page
            # order after the depth rows; degrees wear degrees - the
            # M196 unit law). A value the point cannot be (>= 180)
            # meets the kernel's named refusal at recompute, the same
            # honest channel the revolve's angle has always used.
            dbl("tip_angle", "tip angle", feature.tip_angle, dec=1,
                mn=0.0, ang=True)
        elif isinstance(feature, BodyFilletFeature):
            dbl("radius", "radius", feature.radius)
            check("chamfer", "chamfer, not fillet", feature.chamfer)
            if feature.chamfer and feature.dist2 is not None:
                # M196 R3 [SLD-REF-CHAMFER]: "Two Distance: Bevels
                # edges based on a different distance to each side" +
                # "you can specify two different distance values".  The
                # Type is ONE choice, so this record speaks its second
                # leg in MILLIMETRES (ask()'s default suffix rides -
                # the R1b law is about not LYING, and mm is the truth
                # here) and the angle row does NOT open at all.
                dbl("dist2", "second distance (other face)",
                    feature.dist2, mn=0.05)
            elif feature.chamfer:
                # M196 R1 [SLD-REF-CHAMFER, verbatim]: "Angle (Distance
                # And Angle chamfer type only)" - the row exists only
                # for the bevel record, exactly as the page's parenthetical
                # says.  A legacy record opens at 45.0: the equal-
                # distance bevel IS forty-five degrees, geometrically.
                dbl("angle_deg", "bevel angle from the cap",
                    feature.angle_deg if feature.angle_deg is not None
                    else 45.0, dec=1, mn=0.1, ang=True)
                fld[-1]["max"] = 89.9
        elif isinstance(feature, DraftFeature):
            # M197 R1 [SLD-REF-DRAFT]: "Angle Specify the draft angle"
            # - the row wears degrees (the R1b unit law rides ang=True)
            # - plus the page's Fixed Plane choice, spoken plainly as
            # the body's own bottom or top: rung one leans straight
            # walls about the line where they meet that plane.
            # M197 R3: a PARTING LINE record speaks its own two rows
            # only (one record one voice, the M196 law): the angle and
            # the parting tool plain as a height above the body's own
            # bottom.  It never opens the fixed-plane combo - under a
            # parting line that row is noticed and never written.
            if feature.parting is None:
                # M201 R10 [SLD-REF-DRAFT, verbatim]: "Angle Mode
                # (Fixed Plane draft type only)" - the page GATES the
                # row to the fixed-plane voice, and the lever CAN
                # honour page gates by the record's own voice (the
                # M196 chamfer precedent: "the row exists only for
                # the bevel record"). A parting record never opens
                # it. Page order: Angle Mode (#3) stands BEFORE the
                # Angle row (#8). Rests at the record's own word -
                # the lever echoes, never contradicts; the two words
                # MEASURE identical on straight walls (the kernel
                # field speaks the law), so no difference is faked.
                combo("angle_mode", "angle mode (fixed plane only)",
                      ("Relative", "Absolute"), feature.angle_mode)
                dbl("angle_deg", "draft angle from the fixed plane",
                    feature.angle_deg, dec=1, mn=-89.9, ang=True)
                fld[-1]["max"] = 89.9
                combo("fixed", "fixed plane", ("bottom", "top"),
                      feature.fixed)
            elif feature.angle2 is None:
                dbl("angle_deg", "draft angle from the parting line",
                    feature.angle_deg, dec=1, mn=-89.9, ang=True)
                fld[-1]["max"] = 89.9
                dbl("parting", "parting line above the bottom",
                    float(feature.parting), mn=0.05)
            else:
                # M197 R5 [SLD-REF-DRAFT, verbatim]: the note's TWO
                # angle settings - "labeled Angle 1 and Angle 2" -
                # ride the record's own rows: Angle 1 leans the side
                # BELOW the parting line, Angle 2 the side above (the
                # plain-speech mapping the door documented).  A
                # SYMMETRIC parting record never opens this branch -
                # its single angle is rung three's row, untouched.
                dbl("angle_deg", "Angle 1: draft angle below the "
                                 "parting line",
                    feature.angle_deg, dec=1, mn=-89.9, ang=True)
                fld[-1]["max"] = 89.9
                dbl("angle2", "Angle 2: draft angle above the "
                              "parting line",
                    float(feature.angle2), dec=1, mn=-89.9, ang=True)
                fld[-1]["max"] = 89.9
                dbl("parting", "parting line above the bottom",
                    float(feature.parting), mn=0.05)
        elif isinstance(feature, OffsetFaceFeature):
            # M198 R1 [SLD-OFFSET-FACES]: "Select a single face ...
            # and specify the Offset distance" - the face spoken by
            # the plain names this kernel rotates (the Draft law),
            # and the distance WEARING MILLIMETRES, signed: positive
            # slides the face OUTWARD along its own normal.
            # M197 R3 precedent, R3 here: a PLURAL record speaks its
            # own rows only (one record one voice) - the checks row
            # with its own names ticked; a legacy record never opens
            # it, a plural one never opens the combo.
            if feature.faces:
                fld.append(dict(key="faces", kind="checks",
                                label="faces to shift",
                                choices=["bottom", "top", "wall",
                                         "+x", "-x", "+y", "-y"],
                                checked=list(feature.faces)))
            else:
                combo("face", "face to shift",
                      ("bottom", "top", "wall", "+x", "-x", "+y", "-y"),
                      feature.face)
            dbl("dist", "offset distance", float(feature.dist),
                dec=3, mn=-1000.0, plain=False)
        elif isinstance(feature, ShellFeature):
            dbl("thickness", "wall thickness", feature.thickness, mn=0.05)
        elif isinstance(feature, ThreadFeature):
            dbl("pitch", "pitch", feature.pitch, dec=3)
            dbl("length", "length", feature.length)
        elif isinstance(feature, LinearPatternFeature):
            ints("count", "occurrences", feature.count)
            for i, k in enumerate("xyz"):
                dbl(f"v{i}", f"offset {k}", feature.vector[i], mn=None)
            # M200 [SLD-REF-PATTERN]: the page's two typed rows ride
            # EVERY linear pattern record (both voices always belong
            # to it) - spoken in the record's own lowercase voice.
            combo("dist", "distribution", ("spacing", "extent"),
                  feature.distribution)
            combo("dir", "direction", ("one", "symmetric"),
                  feature.direction)
            # M201 [SLD-REF-PATTERN]: the second direction rides EVERY
            # linear record - the page gives the tool two axes, and a
            # record with Quantity 2 = 1 says so in its own rows.
            ints("count2", "occurrences 2", feature.count2, mn=1)
            for i, k in enumerate("xyz"):
                dbl(f"w{i}", f"offset 2 {k}", feature.vector2[i],
                    mn=None)
            combo("dist2", "distribution 2", ("spacing", "extent"),
                  feature.distribution2)
            combo("dir2", "direction 2", ("one", "symmetric"),
                  feature.direction2)
        elif isinstance(feature, CircularPatternFeature):
            ints("count", "occurrences", feature.count)
            # M200 R2 [SLD-REF-PATTERN]: the page's circular
            # Distribution row rides every record (the record's own
            # lowercase voice).  A FULL record never opens the Angle
            # row - the page's Full takes no angle ("360 degrees
            # around the axis"), so its angle speaks nothing (one
            # record one voice, the draft law); auto/partial/
            # symmetric all speak theirs.
            # M201 R15 [audit stamp]: the page prints THREE words
            # {Full | Partial | Symmetric}; "auto" is a FOURTH CHOICE
            # THAT IS OURS - the rung-era legacy record voice for a
            # plain N*angle sweep, kept because old records wear it
            # and the lever shows a record its own face.  The lever's
            # "one"/"symmetric" spellings are likewise the record's
            # house voice, not the door's printed rows.
            combo("dist", "distribution", ("auto", "full", "partial",
                                           "symmetric"),
                  feature.distribution)
            if feature.distribution != "full":
                dbl("angle", "angle", feature.angle, dec=1, mn=1.0,
                    ang=True)
        elif isinstance(feature, PathPatternFeature):
            ints("count", "occurrences", feature.count)
            # M200 R3 [SLD-REF-PATTERN]: the page's Orientation row
            # rides every path record (the record's own voice).
            combo("orient", "orientation", ("identical", "path"),
                  feature.orientation)
        elif isinstance(feature, GeometricPatternFeature):
            ints("n1", "count 1", feature.n1, mn=1)
            ints("n2", "count 2", feature.n2, mn=1)
            dbl("t1", "translate 1", feature.t1, mn=None)
            dbl("t2", "translate 2", feature.t2, mn=None)
            dbl("r1", "rotate 1", feature.r1, dec=1, mn=None, ang=True)
            dbl("r2", "rotate 2", feature.r2, dec=1, mn=None, ang=True)
            dbl("k1", "scale per step 1", feature.k1, dec=3, mn=0.01,
                plain=True)
            dbl("k2", "scale per step 2", feature.k2, dec=3, mn=0.01,
                plain=True)
        elif isinstance(feature, ScaleFeature):
            for i, axl in enumerate("XYZ"):
                dbl(f"k{i}", f"factor {axl}", feature.factors[i], dec=3,
                    mn=None, plain=True)
            # M201 R11 [GUID-D3F6F79B...]: the page's "pick a fixed
            # anchor point for the scaling" spoken plainly as three
            # numbers (the door's Base point row is the same plain
            # speech - DOUBLES here, not text: a lever formula never
            # raises mid-write, and three axis rows match the k0/k1/
            # k2 shape this lever has always had). They echo the
            # record's own anchor (the lever never contradicts the
            # rail) and the writes below are GUARDED (R4's coin).
            # UNIT-SUFFIX LAW, other edge: an anchor IS a millimetre
            # DISTANCE, so it wears the house unit like every length
            # row (plain=True would strip an honest "mm" - the law
            # clears units only from DIMENSIONLESS rows).
            for i, axl in enumerate("XYZ"):
                dbl(f"b{i}", f"anchor {axl}", feature.base[i], dec=3,
                    mn=None)
        elif isinstance(feature, CoilFeature):
            # M201 R12 [SLD-REF-COIL]: the Type word opens too - it
            # is the record's OWN mouth about which two numbers the
            # door was asked for (the numbers below are what stands
            # either way: the record keeps the classic pair and
            # height stays derived). The lever echoes, never
            # contradicts; page order: Type is row one.
            combo("coil_type", "coil type (two of three)",
                  ("Revolution And Height", "Revolution And Pitch",
                   "Height And Pitch"), feature.coil_type)
            dbl("diam", "centre diameter", feature.diameter)
            dbl("pitch", "pitch", feature.pitch, dec=3)
            dbl("turns", "turns", feature.turns, dec=1, mn=0.5,
                plain=True)
            dbl("size", "section size", feature.size, dec=3, mn=0.01)
        elif isinstance(feature, FluidVolumeFeature):
            # M201 R13 [SLD fluid volume page]: the fluid record
            # speaks its OWN rows in PAGE ORDER - the Volume word
            # (the only one here: Internal stays gated, refused by
            # name at the door), the tool check-list with its own
            # names ticked, the Shape word, the page's gated pair
            # (direction rides STORED-AND-INERT under Box - the
            # page's own gate cannot be enforced by a form, and a
            # lying row is the old sin; the fold proves the shape's
            # truth anyway), and the one distance. Offset is a
            # DISTANCE ("the distance between the outer faces...")
            # so it wears mm with the guarded mm() write - the
            # UNIT-SUFFIX LAW's other edge (R12's turn count had
            # none; this one must).
            combo("volume", "volume", ("External",), feature.volume)
            fld.append(dict(key="tools", kind="checks",
                            label="tool bodies",
                            choices=[b["name"]
                                     for b in self.doc.body_list()],
                            checked=list(feature.tools)))
            combo("shape_type", "shape type",
                  ("Box", "Cylinder", "Hemisphere"),
                  feature.shape_type)
            combo("shape_direction", "shape direction",
                  ("X-Axis", "Y-Axis", "Z-Axis"),
                  feature.shape_direction)
            check("flip", "flip direction", feature.flip)
            dbl("offset", "offset", feature.offset, dec=3, mn=0.0)
        elif isinstance(feature, MirrorFeature):
            combo("plane", "mirror plane",
                  ("YZ", "XZ", "XY") + tuple(p["name"]
                                             for p in self.doc.planes),
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
            if feature.tool_bodies:
                # M201 R14 [SLD-REF-COMBINE]: the body-tool record
                # speaks its OWN voice in the lever - the page's
                # Operation word, the named Tool Bodies check-list
                # ("the bodies that change the model") and the Keep
                # Tools flag ("Retains the tool bodies after the
                # combine results").  The primitive rows belong to
                # the legacy voice and never open on this record.
                fld.append(dict(key="tools", kind="checks",
                                label="tool bodies",
                                choices=[b["name"] for b in
                                         self.doc.body_list()],
                                checked=list(feature.tool_bodies)))
                combo("op", "operation", ("Join", "Cut", "Intersect"),
                      {"union": "Join", "subtract": "Cut",
                       "intersect": "Intersect"}.get(feature.op,
                                                     "Join"))
                check("keep", "keep tools", feature.keep_tools)
            else:
                combo("tool", "tool shape", ("Box", "Cylinder", "Cone",
                                             "Torus", "Sphere"),
                      {"box": "Box", "cylinder": "Cylinder",
                       "cone": "Cone", "torus": "Torus",
                       "sphere": "Sphere"}.get(feature.tool, "Box"))
                combo("op", "operation", ("Join", "Cut", "Intersect"),
                      {"union": "Join", "subtract": "Cut",
                       "intersect": "Intersect"}.get(feature.op,
                                                     "Join"))
                dbl("dx", "length X", feature.dims.get("dx", 20.0))
                dbl("dy", "length Y", feature.dims.get("dy", 20.0))
                dbl("dz", "length Z", feature.dims.get("dz", 20.0))
                dbl("radius", "radius",
                    feature.dims.get("radius", 8.0), dec=3)
                dbl("r1", "bottom radius",
                    feature.dims.get("radius_bottom", 12.0), dec=3)
                dbl("r2", "top radius",
                    feature.dims.get("radius_top", 4.0), dec=3, mn=0.0)
                dbl("major", "ring radius",
                    feature.dims.get("major", 15.0), dec=3)
                dbl("minor", "tube radius",
                    feature.dims.get("minor", 4.0), dec=3, mn=0.01)
                dbl("height", "height",
                    feature.dims.get("height", 30.0))
                for i, k in enumerate("xyz"):
                    dbl(f"c{i}", f"centre {k}", feature.center[i],
                        mn=None)
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
            # M201 R2: the page's three new rows write ONLY when they
            # opened the lever (the count2 law) - a script driving the
            # rung-era five rows keeps the bool as its whole mouth and
            # never invents a direction word. An explicit word SYNCS
            # its paper copy: the bool is the rail's echo of the word.
            if "direction" in v:
                feature.direction = str(v["direction"])
                feature.symmetric = (feature.direction == "symmetric")
            if "measurement" in v:
                feature.measurement = str(v["measurement"])
            if "extent" in v:             # M201 R9: guarded writes -
                feature.extent = str(v["extent"])   #  a lever scripted
            if "height2" in v:                       #  before the rows
                feature.height2 = mm("height2")      #  keeps the words
            if "flip" in v:                          #  the record was
                feature.flip = bool(v["flip"])       #  born with
            if "offset" in v:
                # M201 R4: the same guarded coin - a script driving the
                # rung-era rows never invents an offset.
                feature.offset = mm("offset")
            if "wall" in v:               # M201 R8: guarded writes -
                feature.wall = mm("wall")  #  a lever scripted before
            if "wall_location" in v:       #  the rows keeps the wall
                feature.wall_location = str(v["wall_location"])
                #                          the record was born with
        elif isinstance(feature, RevolveFeature):
            feature.angle = float(v["angle"])
        elif isinstance(feature, HoleFeature):
            feature.radius = mm("radius")
            feature.through = bool(v["through"])
            feature.depth = mm("depth")
            if "tip_angle" in v:          # M201 R7: guarded write -
                #                            a lever scripted before
                #                            the row existed keeps
                #                            the point it was born
                #                            with (R4's law)
                feature.tip_angle = float(v["tip_angle"])
        elif isinstance(feature, BodyFilletFeature):
            feature.radius = mm("radius")
            feature.chamfer = bool(v["chamfer"])
            if "angle_deg" in v:
                # M196 R1: the row only opens for a chamfer record (see
                # _feature_params), so a write here is always the
                # vendor's Distance And Angle row. It stores the typed
                # number AS TYPED - 45.0 typed becomes a 45.0 record,
                # which is geometrically the equal bevel but not the
                # legacy branch (tan 45 is 0.9999999999999999, and
                # identity is not approximation).
                feature.angle_deg = float(v["angle_deg"])
            if "dist2" in v:
                # M196 R3: the second-leg row opens ONLY for a Two
                # Distance record (see _feature_params), so a write
                # here is always that vendor type's typed distance.
                feature.dist2 = float(v["dist2"])
        elif isinstance(feature, DraftFeature):
            # M197 R1 [SLD-REF-DRAFT]: the rows that opened the lever
            # are this record's own - the draft angle stored AS TYPED
            # (degrees, the R1b law) and, per type, the fixed plane or
            # the parting height it leans from (R3: one record one
            # voice, so exactly one of the two mouths is present).
            # R5: a TWO-SIDE record also rode its Angle 2 row; the
            # angle2 key in v means exactly that voice was open - a
            # symmetric or fixed record never shows it and so is
            # never written by it.
            feature.angle_deg = float(v["angle_deg"])
            if "fixed" in v:
                feature.fixed = str(v["fixed"])
            if "angle_mode" in v:          # M201 R10: guarded write -
                feature.angle_mode = str(v["angle_mode"])   #  a script
                                                           #  driving
                                                           #  the rung-
                                                           #  era rows
                                                           #  keeps the
                                                           #  record's
                                                           #  own word
            if "parting" in v:
                feature.parting = float(v["parting"])
            if "angle2" in v:
                feature.angle2 = float(v["angle2"])
        elif isinstance(feature, OffsetFaceFeature):
            # M198 R1 [SLD-OFFSET-FACES]: the rows that opened the
            # lever are this record's own - the plain face name (or
            # the ticked NAMES, R3) and the signed distance, AS
            # TYPED.  One record one voice: exactly one of the two
            # mouths is ever present (the draft precedent).
            if "faces" in v:
                feature.faces = tuple(str(x) for x in v["faces"])
            if "face" in v:
                feature.face = str(v["face"])
            feature.dist = float(v["dist"])
        elif isinstance(feature, ShellFeature):
            feature.thickness = mm("thickness")
        elif isinstance(feature, ThreadFeature):
            feature.pitch = mm("pitch")
            feature.length = mm("length")
        elif isinstance(feature, LinearPatternFeature):
            feature.count = int(v["count"])
            feature.vector = tuple(mm(f"v{i}") for i in range(3))
            # M200: the two new rows write ONLY when they opened the
            # lever (guarded like draft's fixed/parting mouths) - a
            # script driving the rung-era rows never invents a voice.
            if "dist" in v:
                feature.distribution = str(v["dist"])
            if "dir" in v:
                feature.direction = str(v["dir"])
            # M201: the second direction's rows are guarded the same
            # way - a script driving the rung-era six rows never
            # invents an axis it never asked for.
            if "count2" in v:
                feature.count2 = int(v["count2"])
            if "w0" in v:
                feature.vector2 = tuple(mm(f"w{i}") for i in range(3))
            if "dist2" in v:
                feature.distribution2 = str(v["dist2"])
            if "dir2" in v:
                feature.direction2 = str(v["dir2"])
        elif isinstance(feature, CircularPatternFeature):
            feature.count = int(v["count"])
            # M200 R2: the angle row opens on every voice EXCEPT a
            # full record's (the page's Full takes no angle); guarded
            # like every rung-one mouth - a script driving the
            # rung-era rows never invents a voice.
            if "angle" in v:
                feature.angle = float(v["angle"])
            if "dist" in v:
                feature.distribution = str(v["dist"])
        elif isinstance(feature, PathPatternFeature):
            feature.count = int(v["count"])
            # M200 R3: guarded like every mouth since rung one - a
            # script driving the rung-era rows never invents a voice.
            if "orient" in v:
                feature.orientation = str(v["orient"])
        elif isinstance(feature, GeometricPatternFeature):
            feature.n1, feature.n2 = int(v["n1"]), int(v["n2"])
            feature.t1, feature.t2 = mm("t1"), mm("t2")
            feature.r1, feature.r2 = float(v["r1"]), float(v["r2"])
            feature.k1, feature.k2 = float(v["k1"]), float(v["k2"])
        elif isinstance(feature, ScaleFeature):
            feature.factors = tuple(float(v[f"k{i}"]) for i in range(3))
            if "b0" in v:               # M201 R11: guarded anchor write
                # anchors are DISTANCES - they ride the unit-spoken
                # mm() path (the factors above stay raw: a ratio has
                # no unit to convert).
                feature.base = tuple(mm(f"b{i}") for i in range(3))
        elif isinstance(feature, CoilFeature):
            feature.diameter = mm("diam")
            feature.pitch = mm("pitch")
            feature.turns = float(v["turns"])
            feature.size = mm("size")
            if "coil_type" in v:          # M201 R12: guarded word
                feature.coil_type = str(v["coil_type"])
        elif isinstance(feature, FluidVolumeFeature):
            # M201 R13: guarded writes. The tool list and the shape
            # words ride the same guard the faces row taught (R3's
            # plural law: a record that opened its checks row owns
            # the answer); offset is a DISTANCE — mm() on this
            # mouth, exactly the door's suffix (UNIT-SUFFIX LAW).
            if "tools" in v:
                feature.tools = tuple(str(t) for t in v["tools"])
            if "shape_type" in v:
                feature.shape_type = str(v["shape_type"])
            if "shape_direction" in v:
                feature.shape_direction = str(v["shape_direction"])
            if "flip" in v:
                feature.flip = bool(v["flip"])
            feature.offset = mm("offset")
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
            feature.op = {"Join": "union", "Cut": "subtract",
                          "Intersect": "intersect"}[str(v["op"])]
            if feature.tool_bodies:
                # M201 R14: the body voice answers with the Tool
                # Bodies check-list and the Keep Tools flag; the
                # primitive rows never opened, so never read them.
                if "tools" in v:
                    feature.tool_bodies = tuple(
                        str(t) for t in (v.get("tools") or []))
                if "keep" in v:
                    feature.keep_tools = bool(v["keep"])
            elif "tool" in v:
                feature.tool = {"Box": "box", "Cylinder": "cylinder",
                                "Cone": "cone", "Torus": "torus",
                                "Sphere": "sphere"}[str(v["tool"])]
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
        pub = QPushButton("Publish PDF\u2026")           # M143
        pub.setProperty("tb", True)
        pub.setToolTip("Every sheet, one vector PDF — true paper, "
                       "1:1, selectable text")
        pub.clicked.connect(self.action_publish_pdf)
        bl.addWidget(pub)
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
        secb = QPushButton("Section\u2026")              # M102 cut
        secb.setProperty("tb", True)
        secb.setToolTip("Cut the body on a plane and draught the "
                        "wound: a live hatched section view (A-A) "
                        "that re-derives with the model")
        secb.clicked.connect(self.action_section_view)
        bl.addWidget(secb)
        slb = QPushButton("Cut\u2011line")               # M136 tool
        slb.setProperty("tb", True)
        slb.setCheckable(True)
        slb.setToolTip("Draw the cutting line ON a view: two clicks "
                       "on the top, front or right view stand a "
                       "section there — the lettered child view (A-A…) "
                       "arrives hatched in the extra band; Shift at "
                       "the closing click flips the kept half, Alt "
                       "sets a square corner so the line can JOG "
                       "around bores (double-click finishes), and "
                       "double-clicking the child opens its depth, "
                       "hidden-line and scale props")
        slb.toggled.connect(lambda on: self.drawing.set_section_mode(on))
        bl.addWidget(slb)
        self._sec_btn = slb
        tbb = QPushButton("Title\u2026")                 # M108 title block
        tbb.setProperty("tb", True)
        tbb.setToolTip("Fill the drawing title block — number, title, "
                       "drawn-by, date and material (scale, sheet size "
                       "and sheet number are added for you)")
        tbb.clicked.connect(self.action_title_block)
        bl.addWidget(tbb)
        rotb = QPushButton("Rotate\u2026")                # M109 view spin
        rotb.setProperty("tb", True)
        rotb.setToolTip("Rotate one view about its centre (display only — "
                        "every dimension still measures true millimetres)")
        rotb.clicked.connect(self.action_rotate_view)
        bl.addWidget(rotb)
        balb = QPushButton("Balloon")                  # M110 item pin
        balb.setProperty("tb", True)
        balb.setCheckable(True)
        balb.setToolTip("Click a view to pin the next item balloon — "
                        "numbered against the parts list, travelling "
                        "with the body through moves and spins")
        balb.toggled.connect(
            lambda on: (self.drawing.set_balloon_mode(on),
                        on and dimb.setChecked(False)))
        bl.addWidget(balb)
        self._balloon_btn = balb
        bomb = QPushButton("Parts list")               # M110 BOM
        bomb.setProperty("tb", True)
        bomb.setCheckable(True)
        bomb.setToolTip("Dock the ISO parts list on the title block: "
                        "item, description, qty, material, mass — "
                        "derived live from the model (paper only)")
        bomb.toggled.connect(self._toggle_bom)
        bl.addWidget(bomb)
        self._bom_btn = bomb
        hnb = QPushButton("Hole notes")                # M129 hole table
        hnb.setProperty("tb", True)
        hnb.setCheckable(True)
        hnb.setToolTip("Tabulate every Hole feature and tag it on the "
                       "sheet — It./Hole/Qty/Depth/Drill from feature "
                       "metadata (never mesh chords), a centreline cross "
                       "+ item bubble down each bore. On by default")
        hnb.toggled.connect(self._toggle_hole_notes)
        bl.addWidget(hnb)
        self._hole_btn = hnb
        fitb = QPushButton("Fit\u2026")                # M114 callout
        fitb.setProperty("tb", True)
        fitb.setCheckable(True)
        fitb.setToolTip("Click a dimension bubble to attach an ISO 286 "
                        "fit class — Ø30 H7 (+0.021/0) on paper; the "
                        "model stays nominal: a dimension carries truth")
        fitb.toggled.connect(
            lambda on: (self.drawing.set_fit_mode(on),
                        on and dimb.setChecked(False),
                        on and balb.setChecked(False)))
        bl.addWidget(fitb)
        self._fit_btn = fitb
        gtb = QPushButton("GD&T\u2026")                # M144 FCF frame
        gtb.setProperty("tb", True)
        gtb.setCheckable(True)
        gtb.setToolTip("Click a dimension bubble to pin a feature "
                       "control frame — symbol painted from vectors, "
                       "ISO-checked cells; the model stays nominal")
        gtb.toggled.connect(
            lambda on: (self.drawing.set_gdt_mode(on),
                        on and dimb.setChecked(False),
                        on and balb.setChecked(False),
                        on and fitb.setChecked(False),
                        on and slb.setChecked(False)))
        bl.addWidget(gtb)
        self._gdt_btn = gtb
        dimb.toggled.connect(                          # M110: one tool
            lambda on: on and balb.setChecked(False))
        dimb.toggled.connect(lambda on: on and fitb.setChecked(False))
        balb.toggled.connect(lambda on: on and fitb.setChecked(False))
        for other in (dimb, balb, fitb):               # M136: four-way
            slb.toggled.connect(                       # exclusion — the
                lambda on, o=other: on and o.setChecked(False))
            other.toggled.connect(
                lambda on: on and slb.setChecked(False))
        for peer in (dimb, balb, fitb, slb):           # M144: the web
            peer.toggled.connect(                      #     grew one —
                lambda on, o=gtb: on and o.setChecked(False))   # five-way
        bl.addStretch(1)
        lay.addWidget(bar)
        from .drawingview import DrawingCanvas
        self.drawing = DrawingCanvas()
        self.drawing.dim_added.connect(self._add_dim)     # M94 bubbles
        self.drawing.balloon_added.connect(               # M110 pins
            self._add_balloon)
        self.drawing.fit_requested.connect(               # M114 ISO 286
            self._annotate_fit)
        self.drawing.gdt_requested.connect(               # M144 FCF
            self._annotate_gdt)
        self.drawing.view_drag_begin.connect(            # M96 undo capture
            self._capture)
        self.drawing.view_scale_requested.connect(       # M100 scales
            self._on_view_scale)
        self.drawing.section_added.connect(              # M136 cut line
            self._on_section_line)
        self.drawing.section_edit_requested.connect(     # M137 props
            self._on_section_edit)
        self.drawing.tool_note.connect(                  # M136 guidance
            lambda t: self.status.showMessage(t, 6000))
        lay.addWidget(self.drawing, 1)
        # M113 queue-closer: the sheet's own voices — D dimension, B
        # balloon, F fit callout, Esc stands every tool down (Fusion
        # drawing keys; page-scoped so they sleep outside the sheet)
        for seq, fn in (("D", dimb.click), ("B", balb.click),
                        ("F", fitb.click), ("S", slb.click),
                        ("G", gtb.click)):
            QShortcut(QKeySequence(seq), page, activated=fn)
        QShortcut(QKeySequence(Qt.Key_Escape), page,
                  activated=self._stand_down_drawing)
        return page

    def _stand_down_drawing(self):
        """Esc on the sheet: every armed tool back in its rack. M136:
        a half-drawn cutting line is its own rung — the first Esc
        erases the started line and the tool keeps its seat; the next
        stands the tools down. (The page's Esc is a QShortcut, so the
        ladder lives HERE, where the key actually lands.)"""
        if self.drawing.restart_section_line():
            return
        for b in (self._dim_btn, self._balloon_btn, self._fit_btn,
                  self._sec_btn, self._gdt_btn):       # M136/M144 join
            if b.isChecked():
                b.setChecked(False)

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
        """The CREATION PRIMITIVE behind the Create Drawing door
        (M93; door M201 R20): a sheet of live silhouette views of the
        body - top, front, right, iso, fitted to the page. No dialog:
        the tests and the door call this directly; the UI's ONE
        drawing mouth is Create > Create Drawing, which gathers the
        page's rows and lands here. A direct call builds the stamped
        house sheet: ISO A3 Landscape - the sheet-size page prints
        defaults for Standard and Units but NEVER a default size, so
        A3-and-landscape is OURS, the same rest every sheet has worn
        since M93."""
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
        self._sync_bom_btn()                            # new sheet state
        self._sync_hole_btn()
        self._show_page(self._drawing_page)
        self.recompute()
        self.status.showMessage(
            f"{name} created \u2014 top \u00b7 front \u00b7 right \u00b7 iso"
            " \u00b7 live off the model", 6000)

    def action_create_drawing(self):
        """Create > Create Drawing (M201 R20), the door the pages
        print [DWG-REF-CREATE-DRAWING + DWG-REF-SHEET-SIZE +
        DWG-REF-DOCUMENT-SETTINGS, verbatim]: "In the Create Drawing
        dialog, set the Destination options, and click OK." Rows:
        Base Document {From Scratch | Template} - only FROM SCRATCH is
        offered, the kernel keeps no template files and a door never
        promises what cannot land; Standard {ISO | ASME} resting
        where the page itself prints it ("The default is ISO.");
        Sheet size, typed in the chosen family's OWN words - the ISO
        page prints A4..A0, the ASME page A..E, plus "Custom WxH",
        capped by the page's "The maximum value is 200in or 5000mm."
        (that pair is a vendor DEFECT - 200 in is 5080 mm - we honour
        the millimetre member); Orientation {Landscape | Portrait},
        the page's pair, resting at the house sheet's Landscape (no
        default prints for it). The inch family members convert by
        the exact 25.4 law, computed off the built sheet.
        UNOFFERED, declared: Units {in | mm} (the dimension voice
        rides the design's own units - and note the page pair
        "default is ISO" with "default is in (inches)", the
        vendor's own contradiction, DEFECT flagged), Sheet Count
        ("Default is 1." is printed - and one sheet per drawing is
        exactly what the kernel builds, so the row would only dress
        the truth), Drawing Type/Contents/Representation/
        Destination/Sheet/Storyboard/Automation (references,
        storyboards and multi-sheet destinations are kernels we do
        not have). "Open Drawing After Generation" is the page's
        row; its rest (open) is OURS - the page prints no default."""
        from ..core import drawing
        if self.doc is None:
            return
        if self.doc.result is None:
            self.status.showMessage("Nothing to draw — build a body "
                                    "first", 5000)
            return
        from . import cmddialog
        v = cmddialog.ask(self, "Create Drawing", [
            dict(key="base", label="Base Document", kind="combo",
                 choices=["From Scratch"], default="From Scratch"),
            dict(key="standard", label="Standard", kind="combo",
                 choices=["ISO", "ASME"], default="ISO",
                 group="Sheet"),
            dict(key="size", label="Sheet size", kind="text",
                 default="A3", group="Sheet"),
            dict(key="orient", label="Orientation", kind="combo",
                 choices=list(drawing.ORIENTATIONS),
                 default="Landscape",
                 group="Sheet"),
            dict(key="open", label="Open Drawing After Generation",
                 kind="check", default=True)],
            remember_key="create_drawing")
        if v is None:
            return
        size = str(v["size"]).strip()
        orient = str(v["orient"])
        fam = drawing.SHEET_FAMILIES[str(v["standard"])]
        if not (size in fam or size.startswith("Custom")):
            self.status.showMessage(
                f"Sheet size {size!r} is not in the {v['standard']} "
                "family the page prints: " + ", ".join(fam)
                + ", or Custom <W>x<H>", 7000)
            return
        key = size if orient == "Landscape" else f"{size} {orient}"
        try:
            W, H = drawing.sheet_size(key)
        except ValueError as e:
            self.status.showMessage(f"Sheet refused: {e}", 7000)
            return
        before = len(self.doc.drawings)
        self.action_new_drawing()
        if len(self.doc.drawings) == before:
            return                                   # the primitive refused
        g = self.doc.drawings[-1]
        g["page"] = (size if orient == "Landscape"
                     else f"{size} {orient}")
        g["standard"] = str(v["standard"])
        self.doc.dirty = True
        self.drawing.page = g["page"]
        self.drawing.set_document(self.doc)
        if not bool(v.get("open", True)):
            self._show_page(self.viewport)
        self.status.showMessage(
            f"{g['name']} created \u2014 {v['standard']} {g['page']}, "
            f"{W:g} x {H:g} mm on the sheet", 6000)

    def _on_view_scale(self, view: str):
        """M100: the Scale dialog landed on a view — Fit hands it back
        to the layout assistant; a ratio rides on the drawing entry."""
        from ..core.drawing import parse_scale
        g = self.drawing.sheet()
        if not g:
            return
        cur = (g.get("vscale") or {}).get(view)
        choice = self.drawing._scale_dialog(cur)
        if choice is None:
            return
        try:
            factor = parse_scale(choice)
        except ValueError as e:
            self.status.showMessage(f"Scale no good: {e}", 4000)
            return
        self._capture()
        vs = g.setdefault("vscale", {})
        if factor is None:
            vs.pop(view, None)
            if not vs:
                del g["vscale"]
            label = "Fit (layout assistant)"
        else:
            vs[view] = float(factor)
            from .drawingview import scale_label
            label = scale_label(float(factor))
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage(f"{view} view scale: {label}", 4000)

    def action_section_view(self):
        """M102: the sheet's stored cut — dialog picks the plane, the
        half beyond it lands as a live view (A-A, B-B...) whose chains,
        bubbles, hidden ink, moves and scales all re-derive on every
        repaint. Not to be confused with Inspect ▸ Section, which only
        clips the viewport display."""
        if self.doc is None or self.doc.result is None:
            return
        g = self.drawing.sheet()
        if not g:
            return
        from . import cmddialog
        bb = self.doc.result.bounding_box
        v = cmddialog.ask(self, "Section view", [
            dict(key="action", kind="combo", label="Action",
                 choices=["New section", "Remove last section"]),
            dict(key="axis", kind="combo", label="Cut plane normal",
                 choices=["Y (front cut)", "X (side cut)",
                          "Z (horizontal cut)"]),
            dict(key="at", kind="double", label="Cut position",
                 default=float(0.5 * (bb[0][2] + bb[1][2])),
                 min=-1e6, max=1e6, decimals=2)])
        if v is None:
            return
        secs = list(g.get("sections") or [])
        if str(v["action"]).startswith("Remove"):
            if not secs:
                self.status.showMessage("No section views on this "
                                        "sheet", 4000)
                return
            self._capture()
            gone = secs.pop()
            g["sections"] = secs
            if not secs:
                del g["sections"]
            self.doc.dirty = True
            self.drawing.update()
            self.status.showMessage(f"Section {gone['name']} removed",
                                    4000)
            return
        axis = str(v["axis"]).strip()[0].upper()
        if axis not in ("X", "Y", "Z"):
            axis = "Y"
        from ..core import drawing as _d
        letter = _d.section_letter(len(secs))          # M136: one
        name = f"{letter}-{letter}"                    # alphabet now
        self._capture()
        secs.append({"name": name, "axis": axis, "at": float(v["at"])})
        g["sections"] = secs
        self.doc.dirty = True
        self.drawing.update()
        msg = f"Section {name} ({axis} = {float(v['at']):.2f} mm)"
        # M117: the cut carries numbers too — area, boundary perimeter,
        # holes. Fusion's Section Analysis has none of this [—V]: the
        # shoelace readout is pure beat.
        try:
            from ..core import drawing as _dr
            sp = section_properties(
                _dr.section(self.doc.result, axis,
                            float(v["at"]))["cut"])
        except Exception:
            sp = None
        if sp:
            msg += (f" \u00b7 {sp['area_mm2']:.2f} mm\u00b2, perimeter "
                    f"{sp['perimeter_mm']:.2f} mm")
            if sp["holes"]:
                msg += f", {sp['holes']} hole"
        self.status.showMessage(msg, 6000)

    def _on_section_line(self, entry):
        """M136: the two-click cutting line becomes a lettered section
        entry — same registry and alphabet as the dialog cuts, same
        undo, and the child view lands with the sheet's live views:
        chains, hatch, hidden ink, bubbles and moves all re-derive on
        every repaint because a section is a PROJECTION, never a
        picture. The status tells the cut's numbers (M117's readout,
        the line form earns it too)."""
        if self.doc is None or self.doc.result is None:
            return
        g = self.drawing.sheet()
        if not g:
            return
        secs = list(g.get("sections") or [])
        from ..core import drawing as _dr
        letter = _dr.section_letter(len(secs))
        name = f"{letter}-{letter}"
        entry = dict(entry, name=name)
        self._capture()
        secs.append(entry)
        g["sections"] = secs
        self.doc.dirty = True
        self.drawing.update()
        msg = (f"Section {name} on {entry['parent']}"
               + (f" ({len(entry['pts']) - 1}-leg jog)"
                  if entry.get("pts") else "")
               + (" (flipped)" if entry.get("flip") else "")
               + " — drag it like any view, double-click it for "
               "depth & props")
        try:
            sp = section_properties(self.drawing._sec_cut(entry)["cut"])
        except Exception:
            sp = None
        if sp:
            msg += (f" \u00b7 {sp['area_mm2']:.2f} mm\u00b2, perimeter "
                    f"{sp['perimeter_mm']:.2f} mm")
            if sp["holes"]:
                msg += f", {sp['holes']} hole"
        self.status.showMessage(msg, 7000)

    def _on_section_edit(self, name):
        """M137: the section's own properties dialog (rung two of the
        vendor's grammar): the tri-modal DEPTH — full half, slice (the
        wound alone), distance slab — the kept side, hidden lines (OFF
        is how a section reads, and the default; an entry can opt back
        in), and the per-view scale the M100 double-click already
        knew. Cancelling changes nothing; every edit rides _capture
        exactly like the line that made the section."""
        sec = next((s for s in self.drawing.sections()
                    if s["name"] == name), None)
        if sec is None:
            return
        from . import cmddialog
        from ..core.drawing import parse_scale
        line = "parent" in sec
        g = self.drawing.sheet()
        cur_sc = (g.get("vscale") or {}).get(name)
        modes = ["Full (everything behind the line)",
                 "Slice (the cut face alone)",
                 "Distance (a slab from the line)"]
        to_key = {modes[0]: "full", modes[1]: "slice",
                  modes[2]: "distance"}
        to_name = {v: k for k, v in to_key.items()}
        fields = []
        if line:
            fields += [
                dict(key="mode", kind="combo", label="Depth",
                     choices=modes,
                     default=to_name.get(str(sec.get("mode", "full")))),
                dict(key="dist", kind="double",
                     label="Slab depth (Distance only)",
                     default=float(sec.get("dist") or 10.0),
                     min=0.01, max=1e4, decimals=2),
                dict(key="flip", kind="check",
                     label="Flip the kept side",
                     default=bool(sec.get("flip"))),
            ]
        fields += [
            dict(key="hidden", kind="check",
                 label="Show hidden lines (sections omit them)",
                 default=bool(sec.get("hidden"))),
            dict(key="scale", kind="text",
                 label="Scale (blank = fit with the sheet)",
                 default=("" if not cur_sc else
                          f"1:{1 / float(cur_sc):g}")),
        ]
        names = sorted(self.doc.body_solids())
        if len(names) > 1:
            # M139: the vendor's "Objects to Cut" tree, at our scale —
            # an INCLUSION list, all ticked by default. Unticked bodies
            # stand in the child WHOLE and unhatched (the ASME
            # standard-parts look; _sec_src does the add-back).
            fields.append(dict(
                key="cut", kind="checks", label="Bodies to cut",
                choices=names,
                checked=[n for n in names
                         if n not in (sec.get("exclude") or [])]))
        v = cmddialog.ask(self, f"Section {name}", fields)
        if v is None:
            return
        exc = sorted(set(names) - set(v["cut"])) if "cut" in v else None
        if exc is not None and len(v["cut"]) == 0:
            self.status.showMessage("A section must cut at least one "
                                    "body — nothing would hatch", 5000)
            return                       # refuse BEFORE the capture
        self._capture()
        bits = []
        if line:
            mode = to_key.get(str(v["mode"]), "full")
            if mode == str(sec.get("mode", "full")):
                pass
            elif mode == "full":
                sec.pop("mode", None)
                sec.pop("dist", None)
            else:
                sec["mode"] = mode
                if mode == "distance":
                    sec["dist"] = float(v.get("dist") or 10.0)
                else:
                    sec.pop("dist", None)
            if bool(v.get("flip")) != bool(sec.get("flip")):
                sec["flip"] = bool(v["flip"])
                bits.append("flipped")
            shown = mode
            if mode == "distance":
                shown = f"slab {float(sec.get('dist') or 0):g} mm"
            bits.append({"full": "full depth",
                         "slice": "slice \u2014 the wound alone"
                         }.get(mode, shown))
        if bool(v["hidden"]) != bool(sec.get("hidden")):
            sec["hidden"] = bool(v["hidden"])
            bits.append("hidden lines " + ("on" if v["hidden"]
                                           else "off"))
        try:
            factor = parse_scale(str(v["scale"]))
        except ValueError as e:
            self.status.showMessage(f"Scale no good: {e} \u2014 the "
                                    "rest of the edit stands", 6000)
        else:
            vs = g.setdefault("vscale", {})
            if factor is None:
                vs.pop(name, None)
                if not vs:
                    g.pop("vscale", None)
            elif factor != cur_sc:
                vs[name] = factor
        if exc is not None and exc != sorted(
                str(n) for n in (sec.get("exclude") or [])):
            if exc:
                sec["exclude"] = exc
            else:
                sec.pop("exclude", None)
            bits.append(f"cutting {len(names) - len(exc)} of "
                        f"{len(names)} bodies")
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage(
            f"Section {name} \u2014 " + (", ".join(bits) if bits
                                         else "unchanged"), 5000)

    def action_title_block(self):
        """M108: fill the sheet's ISO title block.  Only the human fields
        are stored (number/title/author/date/material); scale, sheet size
        and the sheet number are derived from the drawing at draw time, so
        they can never go stale.  Cancelling changes nothing; the block
        rides the document's undo and the JSON save for free."""
        if self.doc is None or not self.doc.drawings:
            self.status.showMessage("Create a drawing first", 3000)
            return
        g = self.drawing.sheet() or self.doc.drawings[-1]
        block = dict(g.get("block") or {})
        from . import cmddialog
        v = cmddialog.ask(self, "Title block", [
            dict(key="number", kind="text", label="Drawing no.",
                 default=block.get("number", "")),
            dict(key="title", kind="text", label="Title",
                 default=block.get("title", g.get("name", ""))),
            dict(key="author", kind="text", label="Drawn by",
                 default=block.get("author", "")),
            dict(key="date", kind="text", label="Date",
                 default=block.get("date", "")),
            dict(key="material", kind="text", label="Material",
                 default=block.get("material", ""), group="Part")])
        if v is None:
            return
        self._capture()
        clean = {k: str(v.get(k, "")).strip() for k in
                 ("number", "title", "author", "date", "material")}
        clean = {k: val for k, val in clean.items() if val}
        if clean:
            g["block"] = clean
        else:
            g.pop("block", None)
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage("Title block updated", 3000)

    def action_rotate_view(self):
        """M109: spin one view on the sheet about its own centre.  This is
        pure PRESENTATION — the model is untouched, so every dimension on
        the view keeps measuring the true millimetres (bubbles live in
        model space and re-project through the rotation).  0° hands the
        view back to the layout assistant; the angle rides undo + save."""
        if self.doc is None or not self.doc.drawings:
            self.status.showMessage("Create a drawing first", 3000)
            return
        names = list(self.drawing.views().keys())
        if not names:
            self.status.showMessage("The sheet has no views to rotate", 5000)
            return
        g = self.drawing.sheet() or self.doc.drawings[-1]
        rots = g.get("rot") or {}
        from . import cmddialog
        v = cmddialog.ask(self, "Rotate view", [
            dict(key="view", kind="combo", label="View", choices=names),
            dict(key="angle", kind="double", label="Angle", default=0.0,
                 min=-360.0, max=360.0, decimals=1, suffix="\u00b0")])
        if v is None:
            return
        view = str(v["view"])
        deg = float(v["angle"]) % 360.0
        if deg > 180.0:
            deg -= 360.0
        self._capture()
        rots = g.setdefault("rot", {})
        if abs(deg) < 1e-6:
            rots.pop(view, None)
        else:
            rots[view] = deg
        if not rots:
            g.pop("rot", None)
        self.doc.dirty = True
        self.drawing.update()
        shown = "reset to 0\u00b0" if abs(deg) < 1e-6 else f"{deg:g}\u00b0"
        self.status.showMessage(f"{view} view rotated {shown}", 4000)

    def _sync_bom_btn(self):
        """Mirror the visible sheet's parts-list flag onto the button
        (undo, redo and sheet swaps all route through _adopt_doc)."""
        btn = getattr(self, "_bom_btn", None)
        if btn is None:
            return
        on = False
        if self.doc is not None and self.doc.drawings:
            on = bool(self.doc.drawings[-1].get("bom"))
        btn.blockSignals(True)
        btn.setChecked(on)
        btn.blockSignals(False)

    def _sync_hole_btn(self):
        """Hole notes ride the same rails as the parts list, with one
        difference the painter owns: the flag is default-ON, so an
        untouched sheet shows its holes and only an explicit False (or
        no sheet at all) dims the button."""
        btn = getattr(self, "_hole_btn", None)
        if btn is None:
            return
        on = False
        if self.doc is not None and self.doc.drawings:
            on = bool(self.doc.drawings[-1].get("hole_notes", True))
        btn.blockSignals(True)
        btn.setChecked(on)
        btn.blockSignals(False)

    def _toggle_hole_notes(self, on: bool):
        """Hole table on/off for THIS sheet (M129): like the BOM, the
        rows derive — the sheet only carries the decision to show."""
        if self.doc is None or not self.doc.drawings:
            return
        self._capture()
        self.doc.drawings[-1]["hole_notes"] = bool(on)
        self.doc.dirty = True
        self.drawing.update()

    def _toggle_bom(self, on: bool):
        """Parts list on/off for THIS sheet (M110): the rows themselves
        stay derived — the sheet only carries the decision to show."""
        if self.doc is None or not self.doc.drawings:
            return
        self._capture()
        self.doc.drawings[-1]["bom"] = bool(on)
        self.doc.dirty = True
        self.drawing.update()

    def _add_balloon(self, view: str, pt: tuple, item: int):
        """A balloon pin (M110): stored in MODEL millimetres per view —
        the same truth the bubbles measure from, so a rotated or
        dragged view carries its balloons and the numbers still point
        at the part they were pinned to."""
        if self.doc is None or not self.doc.drawings:
            return
        self._capture()
        g = self.doc.drawings[-1]
        g.setdefault("balloons", {}).setdefault(view, []).append(
            {"item": int(item), "x": float(pt[0]), "y": float(pt[1])})
        self.doc.dirty = True
        self.drawing.update()

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
        elif opts.get("radius"):                 # M103: the arc bubble
            r = float(opts["r"])
            entry = {"view": view, "radius": True,
                     "center": [float(x) for x in opts["center"]],
                     "dir": [float(x) for x in opts["dir"]],
                     "r": r,
                     "a": [float(a[0]), float(a[1])],
                     "b": [float(b[0]), float(b[1])],
                     "text": "R %.2f" % r}
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

    def _annotate_fit(self, view: str, idx: int):
        """M114: the ISO 286 class picker for one dimension bubble —
        paper furniture over nominal geometry (Fusion keeps the model
        true and lets the sheet carry the fit)."""
        from . import cmddialog
        if self.doc is None or not self.doc.drawings:
            return
        g = self.drawing.sheet()
        dims = g.get("dims", [])
        if not 0 <= idx < len(dims):
            return
        d = dims[idx]
        if d.get("radius"):
            self.status.showMessage("Fit classes are diameters — an R "
                                    "bubble can't wear one", 4000)
            return
        nom = (2.0 * float(d["r"]) if d.get("diameter")
               else math.dist(d["a"], d["b"]))
        v = cmddialog.ask(self, "Fit callout \u2014 ISO 286", [
            dict(key="cls", kind="combo", label=f"Class on \u00d8{nom:.2f}",
                 choices=["(none \u2014 plain dimension)",
                          "H7", "H8", "H9", "h6", "h7", "h8",
                          "g6", "k6", "n6", "p6",
                          "H7/g6", "H7/h6", "H7/k6", "H7/n6", "H7/p6",
                          "Custom\u2026"])])
        if v is None:
            return
        cls = str(v["cls"]).strip()
        if cls == "Custom\u2026":
            v = cmddialog.ask(self, "Fit class", [
                dict(key="cls", kind="text", label="Class (hole H7, "
                     "shaft g6, or a pair H7/g6)", default="H7")])
            if v is None:
                return
            cls = str(v["cls"]).strip()
        self._capture()
        if cls.startswith("(none"):
            d.pop("fit", None)
            d.pop("fit_nom", None)
            msg = "fit callout removed"
        else:
            try:
                text = iso_fits.callout(nom, cls)
            except ValueError as e:
                self._undo.pop()             # rejected: no edit happened
                # M189 R5 [LAW-61(a)]: the callout grammar refused a
                # typed class - INPUT; kernel words join the
                # "<Noun> refused:" family.
                self.status.showMessage(f"Fit refused: {e}", 6000)
                return
            d["fit"] = cls
            d["fit_nom"] = round(nom, 3)
            msg = f"\u00d8{nom:.2f} {text}"
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage(msg, 4000)

    def _annotate_gdt(self, view: str, idx: int):
        """M144: the feature control frame picker for one dimension
        bubble — the frame is the dim's paper suit, worn over nominal
        geometry. The validator in core.gdt is the ONE choke and it
        raises naming the broken law; the fit flow's capture/warning/
        undo-pop shape is copied verbatim because it is right."""
        from . import cmddialog
        from ..core import gdt
        if self.doc is None or not self.doc.drawings:
            return
        g = self.drawing.sheet()
        dims = g.get("dims", [])
        if not 0 <= idx < len(dims):
            return
        d = dims[idx]
        frames = list(d.get("gdt") or [])
        second = len(frames) >= 2            # edit-by-index (cl.6.4)
        cur = frames[1] if second else (frames[0] if frames else {})
        target_disp = {}
        for label, uid in self._gdt_targets():
            target_disp[uid] = label
        names = ["\u2014 none \u2014"] + [r["name"]
                                          for r in gdt.CONTROL_TABLE.values()]
        v = cmddialog.ask(self, "Feature control frame \u2014 GD&T", [
            dict(key="sym", kind="combo", label="Control",
                 default=gdt.CONTROL_TABLE[cur["sym"]]["name"]
                 if cur.get("sym") in gdt.CONTROL_TABLE else names[0],
                 choices=names),
            dict(key="tol", kind="text",
                 label="Tolerance (\u2300 0.2 or S\u2300 0.3)",
                 default=str(cur.get("tol", ""))),
            dict(key="mod", kind="combo", label="Modifier",
                 default=str(cur.get("mod", "") or ""),
                 choices=["", "M", "L"]),
            dict(key="angle", kind="text",
                 label="True angle (deg) \u2014 required for "
                 "Angularity, illegal elsewhere",
                 default=str(cur.get("angle", "") or "")),
            dict(key="datums", kind="text",
                 label="Datums (A, A-B; comma separated)"
                 + (" — registered: " + " ".join(
                     d["letter"] for d in self.doc.datums)
                     if self.doc.datums else ""),
                 default=", ".join(cur.get("datums", []))),
            dict(key="size", kind="text",
                 label="Size limits (9.995/10.010 or a fit class, "
                 "e.g. H7) \u2014 the \u24c2 bonus computes from them",
                 default=cur.get("size") if isinstance(
                     cur.get("size"), str) else ""),
            dict(key="proj", kind="text",
                 label="Projected zone height (mm; blank = none) "
                 "\u2014 position/orientation only; \u2265 the mating "
                 "part\u2019s thickness",
                 default=str(cur.get("proj", "") or "")),
            dict(key="target", kind="combo",
                 label="Target feature (the frame measures THIS)",
                 default=target_disp.get(
                     (cur.get("target") or {}).get("uid", ""),
                     "\u2014 none \u2014"),
                 choices=["\u2014 none \u2014"]
                         + [n for n, _ in self._gdt_targets()]),
            dict(key="stack", kind="check",
                 label="Edit the SECOND stacked frame (ISO cl.6.4; "
                 "a stack is at most two)",
                 default=bool(second)),
            dict(key="basic", kind="check", label="Basic dimension "
                 "(boxed) \u2014 the true exact of ISO cl.11",
                 default=bool(d.get("basic")))])
        if v is None:
            return
        label = str(v["sym"]).strip()
        datums = [s.strip().upper()
                  for s in str(v["datums"]).replace(";", ",").split(",")
                  if s.strip()]
        self._capture()
        if bool(v["basic"]) and d.get("fit"):
            self._undo.pop()
            # M189 R5 [LAW-61(a)]: a refused combo of typed choices -
            # undo already unwound; the sentence drops to tier (a).
            self.status.showMessage("Frame refused: a boxed BASIC "
                                    "dimension takes its tolerance from "
                                    "the frame — strip the fit class",
                                    6000)
            return
        if label == "\u2014 none \u2014":
            d.pop("gdt", None)                         # strip, as a
            msg = "frame removed"                      # fit strip
        else:
            entry = {"sym": gdt.key_for_name(label),
                     "tol": str(v["tol"]).strip(),
                     "mod": str(v["mod"]).strip(),
                     "datums": datums}
            if str(v.get("angle", "")).strip():
                entry["angle"] = str(v.get("angle", "")).strip()
            if str(v.get("proj", "")).strip():
                entry["proj"] = str(v.get("proj", "")).strip()
            size_txt = str(v.get("size", "")).strip()
            if size_txt:
                entry["size"] = size_txt     # the TEXT the shop typed
            ans_t = str(v.get("target", "\u2014 none \u2014"))
            uid = dict(self._gdt_targets()).get(ans_t, None)
            if ans_t != "\u2014 none \u2014" and uid is None:
                self._undo.pop()
                # M189 R5 [LAW-61(a)]: a vanished pick is INPUT - the
                # sentence keeps its words, drops its voice.
                self.status.showMessage("Frame refused: that target "
                                        "feature is gone", 6000)
                return
            if uid is not None:
                entry["target"] = {"uid": uid, "role": "axis"}
            hint_lines: list[str] = []
            try:
                warns = list(gdt.gdt_validate(entry))
                # M152: the grammar gate stays UNTOUCHED; the registry
                # speaks BESIDE it, painted-not-evaluated, never a
                # refusal. §2.3 CITE-THE-MOVE: hints never outrank a
                # COMPUTED sentence (M150's arithmetic line is the
                # louder truth) — they ride the log and take the
                # status line only when nothing else speaks.
                hint_lines = gdt.datum_hints(
                    entry["datums"],
                    {d["letter"] for d in self.doc.datums})
            except (ValueError, params.ParamError) as e:
                self._undo.pop()             # rejected: no edit happened
                # M189 R5 [LAW-61(a)]: the frame grammar refused typed
                # INPUT - kernel words, tier (a) voice.
                self.status.showMessage(f"Frame refused: {e}", 6000)
                return
            frames = list(d.get("gdt") or [])
            i = 1 if v.get("stack") else 0
            if i == 1 and not frames:
                self._undo.pop()
                # M189 R5 [LAW-61(a)]: the stack order rule is INPUT
                # advice with the undo already unwound - tier (a).
                self.status.showMessage("Frame refused: a stack hangs "
                                        "off a FIRST frame - annotate "
                                        "the first before stacking",
                                        6000)
                return
            if len(frames) < i + 1:
                frames = frames + [entry]
            else:
                frames = frames[:i] + [entry] + frames[i + 1:]
            d["gdt"] = frames
            msg = "FCF " + label
            if entry["tol"]:
                msg += " " + entry["tol"]
            if entry["mod"]:
                msg += " " + entry["mod"]
            say, size_warns = self._gdt_arithmetic(entry)
            if say:
                msg += " \u00b7 " + say
            warns += size_warns
            if warns:
                msg = warns[0]
            elif hint_lines:
                # §2.3 CITE-THE-MOVE: the hint JOINS the line rather
                # than replacing it — the readback (and any computed
                # arithmetic) is the confirmation, the registry's
                # reminder is the footnote. Grammar still outranks
                # everything: a refusal replaces the line outright.
                msg += " \u2014 " + hint_lines[0]
            for hl in hint_lines:
                logservice.warn(hl, source="annotate")
        if bool(v["basic"]):
            d["basic"] = True
        else:
            d.pop("basic", None)
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage(msg, 5000)

    # ---- GD&T rung 2 (M150): targets, arithmetic, datum letters ----
    def _gdt_targets(self) -> list:
        """(display, uid) for the features an FCF can honestly
        MEASURE: hole axes and cylindrical bosses — the publishing
        family (walls/revolve/curved carry no parametric axis yet,
        the named continuation). The dialog combo shows displays,
        the entry stores the UID: names are display, ids are
        identity (M146's law), so a renamed target cannot lie."""
        from ..core.document import HoleFeature, PrimitiveFeature
        out = []
        for f in self.doc.features:
            if isinstance(f, HoleFeature):
                out.append((f"{f.name} · axis Ø{2 * f.radius:g}"
                            f" ({f.body})", f.uid))
            elif isinstance(f, PrimitiveFeature) and f.kind == "cylinder":
                out.append((f"{f.name} · axis Ø"
                            f"{2 * float(f.dims.get('radius', 0)):g}"
                            f" ({f.body})", f.uid))
        return out

    def _gdt_arithmetic(self, entry: dict):
        """The shop numbers a computed frame owes: bonus, allowed,
        virtual condition, size breach. Returns (one spoken line,
        warnings) - FORMULA truth only (stored strings + parametric
        size), never a mesh chord (the SM3 census law)."""
        from ..core import gdtzones
        mod = entry.get("mod")
        if mod not in ("M", "L") or self.doc is None:
            return "", []
        uid = (entry.get("target") or {}).get("uid")
        feat = next((f for f in self.doc.features
                     if getattr(f, "uid", None) == uid), None)
        if feat is None:
            return "", ["the target feature is gone — (M) is "
                        "painted, not evaluated, on this frame"]
        from ..core.document import HoleFeature
        internal = isinstance(feat, HoleFeature)
        d_act = (2.0 * float(feat.radius) if internal
                 else 2.0 * float(feat.dims.get("radius", 0.0)))
        size = entry.get("size")
        lo = hi = None
        txt = str(size)
        if "/" in txt:
            try:
                lo, hi = (float(s) for s in txt.split("/", 1))
            except ValueError:
                raise ValueError(
                    f"size limits '{txt}' must read lo/hi (e.g. "
                    "9.995/10.010)") from None
        elif txt:
            from ..core import fits
            try:                              # the class rides the
                lo, hi = fits.limits(round(d_act, 1), txt)  # NOMINAL,
            except (ValueError, KeyError):    # never the as-built
                raise ValueError(
                    f"'{txt}' is neither lo/hi nor a fit class the "
                    "table knows") from None
        if lo is None:
            return "", ["(M) is painted, not evaluated, without "
                        "size limits — type lo/hi or a fit class"]
        tol = str(entry.get("tol", "")).strip()
        for junk in ("S⌀", "SØ", "⌀", "Ø"):
            tol = tol.replace(junk, "")
        t = float(tol)                               # validator passed
        d_mms, d_lms = (lo, hi) if internal else (hi, lo)
        if mod == "M":
            bonus = (gdtzones.bonus_internal(d_act, d_mms) if internal
                     else gdtzones.bonus_external(d_act, d_mms))
        else:
            bonus = (gdtzones.bonus_lmc_internal(d_act, d_lms)
                     if internal
                     else gdtzones.bonus_lmc_external(d_act, d_lms))
        allowed = t + bonus
        vc = (gdtzones.virtual_internal(d_mms, t) if internal
              else gdtzones.virtual_external(d_mms, t))
        warns = []
        if not lo - 1e-12 <= d_act <= hi + 1e-12:
            warns.append(
                f"Ø{d_act:g} BREACHES its limits "
                f"{lo:g}/{hi:g} — the frame reports the size, "
                "never hides it")
        kind = "hole" if internal else "pin"
        say = (f"{allowed:.4f} allowed on Ø{d_act:g} {kind} "
               f"({'+' if bonus >= 0 else ''}{bonus:.4f} bonus, "
               f"VC Ø{vc:.4f})")
        return say, warns

    def _register_datum(self, kind: str, ref: str, label: str):
        """Browser affordance: a row becomes a LETTER the frames on
        this sheet can speak. Guard-first: the CORE resolves now (a
        letter that names nothing never registers) and collides in
        its own voice; undo captures the registry change."""
        if self.doc is None:
            return
        from . import cmddialog
        from ..core.drawing import RESERVED_LETTERS
        v = cmddialog.ask(self, "Register datum", [
            dict(key="letter", kind="text",
                 label=f"Letter for {label} (A–Z, not "
                       + " ".join(RESERVED_LETTERS) + ")")])
        if v is None:
            return
        self._capture()
        try:
            d = self.doc.datum_register(str(v["letter"]), kind, ref)
        except params.ParamError as e:
            self._undo.pop()
            # M189 R1 [LAW-61]: a double-booked letter is RECOVERABLE
            # INPUT - the kernel's cure ("one letter, one datum")
            # rides the status line instead of an app-modal pop.
            self.status.showMessage(f"Datum not registered: {e}", 6000)
            return
        self._unsaved = True
        self.status.showMessage(
            f"Datum {d['letter']} := {label} — frames may now "
            "reference it", 6000)

    def _unregister_datum(self, letter: str, label: str):
        if self.doc is None:
            return
        self._capture()
        self.doc.datum_remove(letter)
        self._unsaved = True
        self.status.showMessage(
            f"Datum {letter} ({label}) unregistered — painted "
            "frames keep standing and say so when annotated", 6000)

    def _datum_letters(self, ref: str):
        return [d["letter"] for d in (self.doc.datums if self.doc
                                      else []) if d["ref"] == ref]

    def _datum_menu_rows(self, menu, kind, ref, label):
        """One choke: a row that is a datum shows its letters to
        retire; a row that is not, offers registration (M150)."""
        letters = self._datum_letters(ref)
        if letters:
            for x in letters:
                menu.addAction(
                    f"Unregister datum {x}",
                    lambda checked=False, L=x: self._unregister_datum(
                        L, label))
        else:
            menu.addAction(
                "Register as Datum\u2026",
                lambda: self._register_datum(kind, ref, label))

    def action_datum_identifier(self):
        """Tools ▸ Place Datum Identifier (M150): the vendor
        keeps the IDENTIFIER separate from the frame, so it is its
        own annotation — letter-in-a-square on the paper, its
        anchor in MODEL space so it travels and spins for free.
        Guard-first: a sheet and a registered letter come first."""
        if self.doc is None or not self.doc.drawings:
            self.status.showMessage(
                "Datum identifier needs a drawing sheet — "
                "Create > Create Drawing", 6000)
            return
        letters = [d["letter"] for d in self.doc.datums]
        if not letters:
            self.status.showMessage(
                "No datum letters yet — right-click a plane, "
                "axis or hole row and Register as Datum…", 7000)
            return
        from . import cmddialog
        views = sorted(self.drawing.views())
        if not views:
            return
        v = cmddialog.ask(self, "Datum Identifier", [
            dict(key="letter", kind="combo", label="Datum letter",
                 choices=letters),
            dict(key="view", kind="combo", label="View",
                 choices=views),
            dict(key="x", kind="double", label="Anchor X (model mm)",
                 default=0.0),
            dict(key="y", kind="double", label="Anchor Y (model mm)",
                 default=0.0),
            dict(key="lead", kind="check",
                 label="Leader to a stamp offset up-right",
                 default=True)])
        if v is None:
            return
        self._capture()
        g = self.drawing.sheet()
        g.setdefault("datums", []).append({
            "letter": str(v["letter"]), "view": str(v["view"]),
            "anchor": [float(v["x"]), float(v["y"])],
            "leader": ([float(v["x"]) + 8.0, float(v["y"]) + 8.0]
                       if v["lead"] else None)})
        self.doc.dirty = True
        self.drawing.update()
        self.status.showMessage(
            f"Datum identifier {v['letter']} placed on {v['view']}",
            5000)

    def _open_drawing(self, idx: int):
        if self.doc is None or not (0 <= idx < len(self.doc.drawings)):
            return
        self.drawing.set_document(self.doc, idx=idx)
        self._sync_bom_btn()                            # per-sheet flags
        self._sync_hole_btn()
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
                for name in placed:            # M97: hidden lines travel
                    for c in self.drawing.hidden_page(name):
                        if len(c) > 1:
                            ops.append(("poly", [tuple(p) for p in c],
                                        False))
                for name in placed:            # M147: one line-poly per
                    for c in self.drawing.bends_page(name):   # bend of
                        ops.append(("poly", [tuple(p) for p in c],  # the flat
                                    False))
                for name in placed:            # SM3: bend labels travel
                    for at, txt in self.drawing.bend_labels(name):
                        ops.append(("text", txt, tuple(at), 2.5))
                # M102: section hatching travels as honest line geometry
                from ..core import drawing as _dr
                for loops in self.drawing.cuts_page().values():
                    for ha, hb in _dr.hatch_region(loops):
                        ops.append(("poly", [tuple(ha), tuple(hb)],
                                    False))
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
                        if d.get("radius"):         # M103: one leader
                            ops.append(("line", A, B))
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
    def action_publish_pdf(self):
        """M143: Publish PDF — the whole drawing set as ONE vector
        PDF, one page per sheet in creation order (the vendor's
        bundle law: many sheets, one filename, chosen once). Sheet
        scopes (Current/Selected/Range) are the named continuation;
        v1 says honestly what it does."""
        if self.doc is None or not self.doc.drawings:
            self.status.showMessage("Nothing to publish — add a "
                                    "drawing sheet first", 5000)
            return
        default = f"{self.doc.drawings[0]['name']}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Publish PDF",
                                              default, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            n = self.drawing.publish_pdf(path)
        except OSError as e:
            self.status.showMessage(f"Publish failed — {e}", 6000)
            return
        import os                                   # the basename voice
        self.status.showMessage(
            f"Published {n} sheet(s) to "
            f"{os.path.basename(path)} — vector, 1:1", 6000)

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
        """M152: the thin UI arm of Document.rename_feature — what
        was a raw string write is now M130's counted relink, so a
        rename retargets every name-bound face handle and the status
        line counts them (the buried-boss rot cannot recur).
        M162: the kernel moved to _apply_rename — the F2 dialog and
        LAW-2.3's inline field are two doors, ONE truth."""
        if self.doc is None:
            return
        old = feature.name
        name, ok = Shell.getText(self, "Rename feature", "Name:",
                                        text=old)
        if not ok or not name.strip() or name.strip() == old:
            return
        self._apply_rename(feature, name.strip())

    def _apply_rename(self, feature, new_name):
        """The rename kernel door: undo point BEFORE, counted relink,
        refusal rolls the capture back, success recomputes and reloads.
        M162's inline commit (feature_renamed) lands here too."""
        if self.doc is None:
            return
        old = feature.name
        self._capture()                            # undo point BEFORE
        try:
            n = self.doc.rename_feature(old, new_name)
        except Exception as e:                     # name taken
            self._undo.pop()                       # refusal mutates
            self._redo.clear()                     #   nothing
            # M189 R1 [LAW-61]: tier (a) - a taken name is RECOVERABLE
            # INPUT, not data loss. The kernel sentence rides the
            # status line, where the eye already is; the refusal and
            # the unwound capture are unchanged.
            self.status.showMessage(f"Rename refused: {e}", 6000)
            return
        self.doc.dirty = True
        self.recompute()
        self.rail.tree.reload()
        self.status.showMessage(
            f"Renamed {old!r} → {new_name!r}"
            + (f" — {n} reference{'s' if n != 1 else ''} retargeted"
               if n else " — no handles referenced it"), 6000)

    def _rename_datum(self, kind: str, old: str):
        """Construction-plane / work-axis rename (M130): the datum store
        row was read-only before, yet every named mirror, pattern rail
        and coil binds to it BY NAME. The core relink rewrites those
        references atomically, so a rename keeps the model green — the
        status line counts the retargeted bindings so the draughtsman
        sees the ripple, and a collision is refused, never auto-
        disambiguated (one name must mean exactly one datum here)."""
        if self.doc is None:
            return
        new, ok = Shell.getText(self, f"Rename {kind}", "New name:",
                                text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        self._capture()                            # undo point BEFORE
        try:
            n = self.doc.rename_datum(old, new)
        except Exception as e:                     # ParamError: name taken
            self._undo.pop()                       # refusal mutates nothing
            self._redo.clear()
            # M189 R1 [LAW-61]: same tier case as the feature rename -
            # the datum collision speaks on the status line.
            self.status.showMessage(f"Rename refused: {e}", 6000)
            return
        self.doc.dirty = True
        self.recompute()
        self.status.showMessage(
            f"Renamed {old!r} \u2192 {new!r}"
            + (f" — {n} reference{'s' if n != 1 else ''} retargeted"
               if n else " — no features referenced it"), 6000)

    def _delete_feature(self, feature):
        # SM4 (M151): flanges that HANG on this leg go orphan at
        # recompute — warn by name like _datum_delete_ok. uid, not
        # name: identity is what survives a rename (G14's law).
        from ..core.document import FlangeFeature
        if self.doc is not None and isinstance(feature, FlangeFeature):
            refs = self.doc.flange_references(feature.uid)
            if refs:
                ans = QMessageBox.question(
                    self, "Flanges still hang here",
                    f"{feature.name} carries {len(refs)} flange(s):\n  "
                    + "\n  ".join(refs)
                    + "\n\nDeleting it orphans them at recompute "
                      "until they are edited or removed.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ans != QMessageBox.Yes:
                    self.status.showMessage(
                        f"{feature.name} kept — {refs[0]} still hangs "
                        "on it", 5000)
                    return
        self._capture()
        self.doc.features.remove(feature)
        self.doc.dirty = True
        self.rail.props.show_feature(None)
        self.recompute()
        self.status.showMessage(f"Deleted {feature.name} (Ctrl+Z restores)", 4000)

    def _centerline_axis_from_lines(self, lines, points):
        """M191 R5: the ONE dialect-free reading of declared centerlines.
        lines are the (a,b[,construction[,centerline]]) pairs - live Line
        objects OR the file dict's entries; points only needed for the
        dict dialect. Returns (axis | None, error | None): exactly one
        declaration -> the axis; none -> None (the legacy V-axis world
        stands); MANY -> the maker must pick one, and the commit REFUSES
        rather than guess whose axis it bent the model around."""
        cl = [l for l in lines
              if (getattr(l, "centerline", False) if hasattr(l, "a")
                  else len(l) > 3 and bool(l[3]))]
        if not cl:
            return None, None
        if len(cl) > 1:
            return None, (f"{len(cl)} centerlines declare {len(cl)} axes - "
                          "a revolve turns about exactly ONE; delete the "
                          "others")
        if hasattr(cl[0], "a"):
            a, b = cl[0].a, cl[0].b
            pair = [[float(a.x), float(a.y)], [float(b.x), float(b.y)]]
        else:
            pa, pb = points[cl[0][0]], points[cl[0][1]]
            pair = [[float(pa[0]), float(pa[1])], [float(pb[0]), float(pb[1])]]
        if abs(pair[1][0] - pair[0][0]) + abs(pair[1][1] - pair[0][1]) < 1e-9:
            return None, None               # degenerate: cannot be an axis
        return pair, None

    def _sketch_revolve_axis(self, m):
        """M191 R5 [SKT-CENTERLINE-GEOMETRY]: the declared centerline of
        a live sketch, as (axis | None, error | None) - see
        _centerline_axis_from_lines for the law."""
        if m is None:
            return None, None
        return self._centerline_axis_from_lines(m.sketch.lines, None)

    def _axis_from_payload(self, payload):
        """The same law read from the FILE dialect (the region-update
        door only has the dict) - so preview, refusal and re-commit can
        never disagree about which line is the axis."""
        return self._centerline_axis_from_lines(
            (payload or {}).get("lines", []),
            (payload or {}).get("points", []))

    def _profile_crosses_axis(self, outer, axis):
        """Dry-run mirror of RevolveFeature.build's refusal: does this
        profile straddle the CENTERLINE (None = the sketch u=0 line)?
        Measured in the SAME frame the kernel sweeps, so the dialog's
        yes can never disagree with the build's result."""
        o = np.asarray(outer, float)
        if axis is None:
            u = o[:, 0]
        else:
            a1 = np.asarray(axis[0], float)
            a2 = np.asarray(axis[1], float)
            d = a2 - a1
            nrm = math.hypot(d[0], d[1])
            if nrm < 1e-9:
                return False
            u = (o - a1) @ np.array([d[1], -d[0]]) / nrm
        return bool(u.min() < -1e-6 < u.max())

    def edit_sketch(self, feature):
        if self.doc is None or not self._discard_guard():
            return
        model = model_from_dict(feature.sketch)
        model.sid = feature.sid or id(model)
        self._editing_sid = model.sid
        # M191 R2: the memory arms BEFORE any roll (M161's gate in
        # _feature_activated may already have moved the marker - the
        # maker's position is the one from BEFORE the visit).
        if not self._edit_park_on:              # FIRST edit of the visit
            # home has TWO spellings in this field (None and any number
            # >= the feature count); normalize BEFORE the memory, or a
            # stale number would be "restored" on leaving.
            cur = self.doc.rollback_to
            if cur is not None and cur >= len(self.doc.features):
                cur = None
                self.doc.rollback_to = None
            self._edit_park_on = True
            self._edit_park = cur
        self._park_marker_for_edit(feature)     # M191 R2: editing parks
        self.sketch.set_model(model)            #   the marker at THIS
        self._show_page(self._sketch_page)      #   feature (LAW-10 full)
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

    # ---- construction geometry (M125) — planes get methods, axes join ------
    @staticmethod
    def _pt(txt) -> list[float]:
        """Parse a 'x,y,z' dialog field; refuse anything else loudly."""
        try:
            vals = [float(t) for t in str(txt).replace(";", ",").split(",")]
        except ValueError:
            raise params.ParamError(f"points are 'x,y,z' — got {txt!r}")
        if len(vals) != 3:
            raise params.ParamError(f"points are 'x,y,z' — got {txt!r}")
        return vals

    def action_construction_plane(self):
        """Fusion's Construct ▸ Plane, unified dialog (M125): offset, at
        angle, through three points, or midplane between two planes."""
        if self.doc is None:
            return
        names = ["XY", "XZ", "YZ"] + [p["name"] for p in self.doc.planes]
        v = cmddialog.ask(self, "Construction Plane", [
            dict(key="how", label="Method", kind="combo", group="Method",
                 choices=("Offset from origin plane", "At angle about hinge",
                          "Through three points", "Midplane between two")),
            dict(key="base", label="Offset from / rotate", kind="combo",
                 choices=["XY", "XZ", "YZ"], group="Plane"),
            dict(key="dist", label="Distance (offset)", kind="double",
                 default=10.0, min=-1e5, max=1e5, group="Plane"),
            dict(key="angle", label="Angle (at angle)", kind="double",
                 default=45.0, min=-359.9, max=359.9, suffix="°",
                 group="Plane"),
            dict(key="hinge", label="Hinge (at angle)", kind="combo",
                 choices=("u — plane's own X", "v — plane's own Y"),
                 group="Plane"),
            dict(key="p1", label="Point 1", kind="text", default="0,0,0",
                 group="Three points"),
            dict(key="p2", label="Point 2", kind="text", default="10,0,0",
                 group="Three points"),
            dict(key="p3", label="Point 3", kind="text", default="0,10,10",
                 group="Three points"),
            dict(key="pa", label="Plane A (midplane)", kind="combo",
                 choices=names, group="Midplane"),
            dict(key="pb", label="Plane B (midplane)", kind="combo",
                 choices=names[1:] + names[:1], group="Midplane"),
        ], remember_key="construction_plane")
        if v is None:
            return
        how = v["how"]
        try:
            if how.startswith("Offset"):
                p = self.doc.add_plane(v["base"], v["dist"])
                say = f"{p['name']} at {v['dist']:+g} mm from {v['base']}"
            elif how.startswith("At angle"):
                p = self.doc.add_plane_angle(
                    v["base"], v["angle"],
                    "u" if v["hinge"].startswith("u") else "v")
                say = (f"{p['name']} — {v['base']} tipped {v['angle']:g}° "
                       f"about its {p['hinge']}")
            elif how.startswith("Through"):
                p = self.doc.add_plane_3pt(self._pt(v["p1"]),
                                           self._pt(v["p2"]),
                                           self._pt(v["p3"]))
                say = f"{p['name']} through the three picked points"
            else:
                p = self.doc.add_plane_mid(v["pa"], v["pb"])
                say = f"{p['name']} midway between {v['pa']} and {v['pb']}"
        except params.ParamError as exc:
            self.status.showMessage(f"Plane refused: {exc}", 6000)
            return
        self._unsaved = True
        self.rail.tree.reload()
        self.viewport.refresh()
        self.status.showMessage(
            f"{say} — double-click it in the browser to sketch on it", 6000)

    def action_work_axis(self):
        """Fusion's Construct ▸ Axis, the cheap-half v1 (M125): through
        two points, or where two planes meet. Axes are named, first-class
        datums — patterns and mirrors take them by name at recompute."""
        if self.doc is None:
            return
        names = ["XY", "XZ", "YZ"] + [p["name"] for p in self.doc.planes]
        v = cmddialog.ask(self, "Work Axis", [
            dict(key="how", label="Method", kind="combo", group="Method",
                 choices=("Through two points",
                          "Intersection of two planes")),
            dict(key="p1", label="Point 1", kind="text", default="0,0,0",
                 group="Two points"),
            dict(key="p2", label="Point 2", kind="text", default="0,0,10",
                 group="Two points"),
            dict(key="pa", label="Plane A", kind="combo", choices=names,
                 group="Two planes"),
            dict(key="pb", label="Plane B", kind="combo",
                 choices=names[1:] + names[:1], group="Two planes"),
        ], remember_key="work_axis")
        if v is None:
            return
        try:
            if v["how"].startswith("Through"):
                a = self.doc.add_axis_2pt(self._pt(v["p1"]),
                                          self._pt(v["p2"]))
                say = f"{a['name']} from ({v['p1']}) to ({v['p2']})"
            else:
                a = self.doc.add_axis_2planes(v["pa"], v["pb"])
                say = f"{a['name']} — where {v['pa']} and {v['pb']} meet"
        except params.ParamError as exc:
            self.status.showMessage(f"Axis refused: {exc}", 6000)
            return
        self._unsaved = True
        self.rail.tree.reload()
        self.viewport.refresh()
        self.status.showMessage(
            f"{say} — patterns and mirrors can reference it by name", 6000)

    def _delete_axis(self, name):
        if self.doc and self._datum_delete_ok(name) and \
                self.doc.remove_axis(name):
            self._unsaved = True
            self.rail.tree.reload()
            self.recompute()
            self.status.showMessage(f"Deleted {name}", 3000)

    def _caxis_menu(self, name, pos):
        menu = QMenu(self)
        menu.addAction("Rename…",
                       lambda: self._rename_datum("work axis", name))
        self._datum_menu_rows(menu, "axis", name, f"work axis {name}")
        menu.addSeparator()
        menu.addAction("Delete work axis", lambda: self._delete_axis(name))
        menu.exec_(pos)

    def action_thread(self):
        """Fusion Thread (M49b v1): click a cylindrical boss face and
        give it real bolt threads — a helical ridge cut to the minor."""
        from ..core.thread import fit_cylinder
        if self.doc is None or self.doc.result is None:
            # M189 R3 [LAW-61(a)]: precondition -> tier (a) voice.
            self.status.showMessage("Nothing to thread yet — extrude "
                                    "or import a solid first", 5000)
            return
        groups = self.viewport.selected_groups()
        if len(groups) != 1:
            # M189 R4 [LAW-61(a)]: guidance is INPUT - same words, tier
            # (a) voice; the information verb was never earned either.
            self.status.showMessage("Click exactly ONE cylindrical face "
                                    "to thread — flat faces cannot be "
                                    "threaded", 5000)
            return
        tm = self.viewport._tm
        seed = int(sorted(groups[0])[0])
        tris = np.asarray(self.viewport.smooth_region(seed), int)
        pts = tm.vertices[np.asarray(tm.faces, int)[tris]].reshape(-1, 3)
        nrm = np.repeat(np.asarray(tm.face_normals, float)[tris], 3, axis=0)
        fit = fit_cylinder(pts, nrm)
        if fit is None:
            # M189 R4 [LAW-61(a)]: the flat-face pick is fixable INPUT.
            self.status.showMessage("That face is not a cylinder — Thread "
                                    "needs the curved face of a boss or "
                                    "pin", 5000)
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
            # M189 R4 [LAW-61(a)]: a too-short boss is a MEASURED input
            # refusal - numbers ride the status line like R2's kernels.
            self.status.showMessage(f"That face is only {length:g} mm "
                                    f"tall — too short for an {size} "
                                    "thread", 5000)
            return
        if fit["radius"] - 0.5 * pitch <= 0.1:
            # M189 R4 [LAW-61(a)]: ditto the too-thin core.
            self.status.showMessage(f"Ø {dia:g} is too thin for {size}: "
                                    "the thread would cut away the core",
                                    5000)
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
        model.host = p["name"]        # M152: the WITNESS — display +
        #   relink + warn material only; the frame stays the frozen
        #   copy and the letter is looked up through the registry
        self._begin_sketch(model)
        self.status.showMessage(
            f"Sketching on {p['name']}{self._datum_badge(p['name'])}"
            " — draw, then X extrudes along its normal")

    def _datum_badge(self, ref: str) -> str:
        """" [A]" when a registered plane/axis letter answers to
        this NAME (hole refs are uids and never ride this path). One
        registry, one truth: the letter is LOOKED UP, never stored."""
        if self.doc is None:
            return ""
        for dt in self.doc.datums:
            if dt["kind"] in ("plane", "axis") and dt["ref"] == ref:
                return f" [{dt['letter']}]"
        return ""

    def _cplane_menu(self, name, pos):
        stored = name not in ("XY", "XZ", "YZ")   # origin planes: section
        menu = QMenu(self)                        # yes, rename/delete no
        menu.addAction("Sketch on plane" + self._datum_badge(name),
                       lambda: self.action_sketch_on_plane(name))
        menu.addSeparator()
        # M135: section rides named planes — datum renames (M130)
        # relink the cut for free, which is why it is a row command.
        menu.addAction("Section: cut here",
                       lambda checked=False: self._section_here(name))
        if self.doc is not None and self.doc.section_active():
            if self.doc.section_plane() == name:
                menu.addAction("Flip section", self._flip_section)
            menu.addAction("Clear section", self._clear_section)
        self._datum_menu_rows(menu, "plane", name,
                              f"plane {name}")
        if stored:
            menu.addSeparator()
            menu.addAction("Rename…",
                           lambda: self._rename_datum("construction plane",
                                                      name))
            menu.addSeparator()
            menu.addAction("Delete construction plane",
                           lambda: self._delete_plane(name))
        menu.exec_(pos)

    def _body_menu(self, name, pos):
        """M104 browser body menu: make this the active body, or the
        per-body bulb.  One node per real body now, so the menu carries
        the name (pre-M104 there was only ever one and it was theatre)."""
        if self.doc is None:
            return
        entry = next((b for b in self.doc.body_list()
                      if b["name"] == name), None)
        vis = True if entry is None else bool(entry.get("visible", True))
        menu = QMenu(self)
        menu.addAction("Activate " + name,
                       lambda checked=False: self.action_activate_body(name))
        menu.addAction("Paint " + name + "…",
                       lambda checked=False: self.action_paint_body(name))
        menu.addAction(("Hide" if vis else "Show") + " " + name,
                       lambda checked=False: self._toggle_body_visible(name))
        # M134: Isolate — the suppressive overlay, offered on body rows.
        # (Fusion's own body-row isolate is officially broken for
        # multi-body components; our strict per-row predicate is the
        # differentiator, per the probe.)
        menu.addAction("Isolate " + name,
                       lambda checked=False: self._isolate_body(name))
        grounded = bool((entry or {}).get("grounded"))
        menu.addAction(("Unground " if grounded else "Ground ") + name,
                       lambda checked=False: self._toggle_grounded(name))
        if self.doc.isolation_active():
            menu.addAction("Unisolate All", self._unisolate_all)
        # M201 R16 [MESH-SAVE-AS-MESH, verbatim]: "In the Design
        # workspace, right-click a component or body in the Browser.
        # Select Save As Mesh." - the page's trigger is the Browser
        # right-click, so that is the ONLY mouth this tool gets (no
        # menu bar entry: "File > Export" appears on NEITHER page of
        # this family, and the page's component half waits for the
        # components rung - our body row is the shape the page's
        # second sentence already licenses: "Right-click the solid,
        # surface, or mesh body to export").
        menu.addSeparator()
        menu.addAction("Save As Mesh…",
                       lambda checked=False: self.action_save_as_mesh(name))
        mat = menu.addMenu("Material")
        from ..core.materials import NAMES as MAT_NAMES
        cur = (entry or {}).get("material") if entry else None
        grp = QActionGroup(mat)
        for choice, label in ((None, "None"),
                              *[(m, m) for m in MAT_NAMES]):
            act = QAction(label, mat)
            act.setCheckable(True)
            act.setChecked((cur or None) == choice)
            grp.addAction(act)
            act.triggered.connect(lambda checked=False, c=choice:
                                  self._set_body_material(name, c))
            mat.addAction(act)
        menu.exec_(pos)

    def _move_blocker_msg(self):
        """LAW R choke (§5.4): a grounded or jointed body refuses the
        Move/Rotate gesture AT ARM TIME — the triad never appears,
        because a refused COMMIT would leave the user holding a
        half-dragged preview to explain. The core says why; we say
        it in the status line."""
        if self.doc is None:
            return None
        nm = self.doc.active_body
        try:
            return self.doc.move_blocker(nm) if nm else None
        except KeyError:
            return None

    def _toggle_grounded(self, name):
        """M146: ground is a body flag and a FILE fact (the vendor's
        per-occurrence boolean) — it refuses drags, never rewrites
        geometry, and needs no recompute."""
        if self.doc is None:
            return
        cur = next((x for x in self.doc.body_list()
                    if x["name"] == name), None)
        if cur is None:
            return
        self._capture()
        on = not bool(cur.get("grounded"))
        self.doc.ground_body(name, on)
        self.rail.tree.reload()
        self.status.showMessage(
            f"{name} " + ("grounded — it anchors its joint tree and "
                          "refuses drags" if on else
                          "ungrounded — it may be dragged again"), 5000)

    def _joint_menu(self, joint_id, pos):
        """M146 browser joint-row menu, mirrored M201 R19 onto the
        page's list [ASM-JOINTS, verbatim]: "You can right-click any
        existing joint... Edit Joint: Opens the Edit Joint dialog and
        lets you edit all settings associated with the joint." |
        "Suppress: Temporarily removes the joint to prevent it from
        acting upon the components." FOUR of the page's six stay
        UNOFFERED, each gated by a page's own sentence: "Edit Joint
        Limits" waits for "a Joint Type that has more than one degree
        of motion" and Rigid carries none (the limits gate, quoted at
        the R18 door); "Lock: Locks the current position and settings
        of the joint" holds what nothing moves; "Animate Joint" and
        "Animate Model" have no motion to show on a 0-DOF lock and no
        animator. "Delete Joint" is OURS, stamped - the page's six do
        not print it, and v1's row menu has had it since M146."""
        if self.doc is None:
            return
        j = next((x for x in self.doc.joints if x["id"] == joint_id), None)
        if j is None:
            return
        menu = QMenu(self)
        menu.addAction("Edit Joint",
                       lambda checked=False: self._edit_joint(joint_id))
        menu.addAction("Unsuppress" if j.get("suppressed") else "Suppress",
                       lambda checked=False:
                       self._toggle_joint_suppress(joint_id))
        menu.addSeparator()
        menu.addAction("Delete Joint",
                       lambda checked=False: self._delete_joint(joint_id))
        menu.exec_(pos)

    def _edit_joint(self, joint_id):
        """The page's "Edit Joint dialog... edit all settings": every
        setting this kernel holds is the PAIR (ground is a body flag
        and lives on the body row), so the door re-opens titled Edit
        Joint, pre-filled from the record, and OK re-runs the whole
        add_joint contract on the new pair - the same refusal voice
        and the same unwinds as creation, and nothing at all on a
        Cancel."""
        j = next((x for x in self.doc.joints if x["id"] == joint_id), None)
        if j is None:
            return
        names = [b["name"] for b in self.doc.body_list()
                 if not b.get("derived")]
        base = self.doc._body_by_id(j["a"])
        mover = self.doc._body_by_id(j["b"])
        if base is None or mover is None:
            return
        from . import cmddialog
        v = cmddialog.ask(self, "Edit Joint", [
            dict(key="base", kind="combo", label="Base body",
                 choices=names, default=base["name"], group="Components"),
            dict(key="mover", kind="combo", label="Moving body",
                 choices=names, default=mover["name"],
                 group="Components")])
        if v is None:
            return
        self._capture()
        try:
            self.doc.edit_joint(joint_id, str(v["base"]), str(v["mover"]))
        except ValueError as e:      # ParamError IS a ValueError
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Joint refused: {e}", 6000)
            return
        self.recompute()
        self.viewport.refresh()
        self.rail.tree.reload()
        self.status.showMessage(
            "Joint edited — the same relation, re-captured where the "
            "bodies stand now", 5000)

    def _toggle_joint_suppress(self, joint_id):
        """The house words are the browser's own (features Suppress /
        Unsuppress since the early eras); the SEMANTICS are the page's
        sentence. The row's glyph is the established suppressed circle;
        the folder still counts the joint - suppression hides its act,
        not its existence."""
        j = next((x for x in self.doc.joints if x["id"] == joint_id), None)
        if j is None:
            return
        on = not bool(j.get("suppressed"))
        self._capture()
        self.doc.suppress_joint(joint_id, on)
        self.recompute()
        self.viewport.refresh()
        self.rail.tree.reload()
        self.status.showMessage(
            "Joint suppressed — it acts on nothing while the body "
            "rides its own placement" if on else
            "Joint restored — the captured pose is re-applied", 5000)

    def _delete_joint(self, joint_id):
        if self.doc is None:
            return
        self._capture()
        self.doc.remove_joint(joint_id)
        self.recompute()
        self.viewport.refresh()
        self.rail.tree.reload()
        self.status.showMessage(
            "Joint deleted — the body keeps its placed pose", 5000)

    def _set_body_material(self, name, material):
        """M110: the physical material behind the parts list.  'Paint'
        (M106) is how a body LOOKS; this is what it's MADE OF — mass on
        the BOM follows this one, and the name ships in the JSON."""
        if self.doc is None:
            return
        b = next((x for x in self.doc.body_list()
                  if x["name"] == name), None)
        if b is None:
            return
        if (b.get("material") or None) == (material or None):
            return
        self._capture()
        if material:
            b["material"] = material
        else:
            b.pop("material", None)
        self.doc.dirty = True
        if self._drawing_page is not None:
            self.drawing.update()          # a live parts list re-weighs

    def action_paint_body(self, name):
        """M106: give ONE body its own material (Fusion's Appearance can
        target a body).  This is the per-body layer; the whole-part doc
        appearance (M52) stays the default for bodies that carry none."""
        if self.doc is None:
            return
        b = next((x for x in self.doc.body_list()
                  if x["name"] == name), None)
        if b is None:
            return
        from ..core.appearance import MATERIALS, appearance
        cur = (b.get("appearance") or {}).get("name", "(default)")
        choices = ["(default)", "Custom…", *MATERIALS]
        v = cmddialog.ask(self, f"Paint {name}", [
            dict(key="preset", label="Material", kind="combo",
                 choices=choices,
                 default=cur if cur in choices else "(default)",
                 group=name)], remember_key=f"paint:{name}")
        if v is None:
            return
        preset = v["preset"]
        self._capture()
        if preset == "(default)":
            self.doc.set_body_appearance(name, None)
            msg = f"{name}: default appearance"
        elif preset == "Custom…":
            from PySide6.QtGui import QColor
            from PySide6.QtWidgets import QColorDialog
            old = (b.get("appearance") or {}).get("color")
            init = QColor(*(int(round(c * 255)) for c in old)) \
                if old else QColor.fromRgbF(*DARK["solid_base"])
            col = QColorDialog.getColor(init, self, f"{name} colour")
            if not col.isValid():
                self._undo.pop()
                return
            app = {"name": "Custom",
                   "color": [col.red() / 255, col.green() / 255,
                             col.blue() / 255], "opacity": 1.0}
            self.doc.set_body_appearance(name, app)
            msg = f"{name} painted: Custom"
        else:
            self.doc.set_body_appearance(name, appearance(preset, 1.0))
            msg = f"{name} painted: {preset}"
        self._unsaved = True
        self.rail.tree.reload()
        self.viewport.refresh()
        self.status.showMessage(msg, 4000)

    def _toggle_body_visible(self, name):
        doc = self.doc
        if doc is None:
            return
        vis = next((bool(b.get("visible", True)) for b in doc.body_list()
                    if b["name"] == name), True)
        if not doc.set_body_visible(name, not vis):
            return
        self._unsaved = True
        self.rail.tree.reload()
        self.viewport.refresh()
        self.status.showMessage(f"{name} " + ("hidden" if vis else "shown"),
                                3000)

    # ---- isolation (M134) ---------------------------------------------------
    def _refresh_visibility(self):
        self.rail.tree.reload()
        # M162 LAW-1.3's choke: the Bodies-folder layer follows the
        # tree's view state on EVERY refresh, so folder eye, renderer
        # and browser never disagree — one truth, one path.
        self.viewport.set_solid_visible(self.rail.tree.folder_vis)
        self.viewport.refresh()

    # ---- the browser eyes (M162, FD3) ---------------------------------------
    def _on_eye_toggled(self, role):
        """One door for both eyes: a body row writes the document
        kernel (it is DATA — serialized, undo-tracked by its own paths);
        the Bodies folder flips VIEW state (the layer) and changes
        nothing about the children — their eyes keep their latent say
        (LAW-1.3's AND-chain, the probe's decisive phrasing)."""
        kind, arg = role
        if kind == "body":
            self._toggle_body_visible(arg)
        elif kind == "folder" and arg == "bodies":
            self.rail.tree.folder_vis = not self.rail.tree.folder_vis
            self._refresh_visibility()
            self.status.showMessage(
                "Bodies layer hidden — the eyes below are unchanged, "
                "the folder is overruling them (LAW-1.3)"
                if not self.rail.tree.folder_vis else
                "Bodies layer on — every latent eye speaks again", 5000)

    def _on_inline_rename(self, feature, new_name):
        """LAW-2.3's commit: the inline field lands on the SAME kernel
        door F2 uses — counted relinks, undo point, the lot."""
        if new_name and new_name != feature.name:
            self._apply_rename(feature, new_name)

    def _find_in_browser(self, feature) -> bool:
        """M162 LAW-5.1: from a feature's context menu — reveal its
        browser row with the dashed flash. If the walk finds no row
        (a row kind the browser does not list), the status says so."""
        found = self.rail.tree.reveal_feature(feature)
        if not found:
            self.status.showMessage(
                f"'{feature.name}' has no browser row to find (yet)",
                4000)
        return found

    def _isolate_body(self, name):
        doc = self.doc
        if doc is None:
            return
        scope = doc.isolate([name])
        if not scope:
            return
        self._refresh_visibility()
        self.status.showMessage(
            f"Isolating {', '.join(scope)} — Esc pops back, Show All is "
            "the lossy recovery", 5000)

    def _unisolate_all(self):
        doc = self.doc
        if doc is None or doc.unisolate_all() == 0:
            return
        self._refresh_visibility()
        self.status.showMessage("Isolation ended — rows hidden before "
                                "it came back hidden, exactly", 5000)

    def _show_all_bodies(self):
        doc = self.doc
        if doc is None:
            return
        dropped = doc.isolation_depth()
        shown = doc.show_all()
        if dropped or shown:
            self._unsaved = True    # Show All WRITES eye state — it is
            self._refresh_visibility()   # model-visible, unlike
            # (hence unsaved)  isolation's pure overlay
            self.status.showMessage(
                f"Show All: {shown} body(s) forced on"
                + (f", {dropped} isolation level(s) ended" if dropped
                   else "")
                + " — unisolate would have kept the pre-isolate darks",
                6000)

    def _on_isolation_esc(self):
        doc = self.doc
        if doc is None or not doc.unisolate():
            return
        self._refresh_visibility()
        if doc.isolation_active():
            self.status.showMessage(
                f"Isolation {doc.isolation_depth()} deep → "
                f"{', '.join(doc.isolation_names())}", 4000)
        else:
            self.status.showMessage("Isolation ended — pre-isolate "
                                    "visibility restored exactly", 4000)

    # ---- section view (M135) -------------------------------------------------
    def _section_here(self, name):
        doc = self.doc
        if doc is None:
            return
        try:
            doc.set_section(name)            # resolves by NAME now: an
        except Exception as e:               # unknown/broken datum cuts
            self.status.showMessage(str(e), 5000)   # nothing and says why
            return
        self.viewport.refresh()
        self.status.showMessage(
            f"Section on {name} — Esc or Clear section ends it; face "
            "picking is suspended while the model is cut", 6000)

    def _flip_section(self):
        doc = self.doc
        if doc is None or not doc.section_active():
            return
        doc.set_section(doc.section_plane(), flip=not doc._section["flip"])
        self.viewport.refresh()
        self.status.showMessage("Section flipped — the kept half is the "
                                "other one now", 4000)

    def _clear_section(self):
        if self.doc is None or not self.doc.clear_section():
            return
        self.viewport.refresh()
        self.status.showMessage("Section cleared — the whole model is "
                                "back, picks with it", 4000)

    def _root_menu(self, pos):
        """Document-row menu (M134): the always-findable exits. Leaving
        an isolation must never require finding the isolated row — the
        probe made that Fusion's documented annoyance, so Show All and
        Unisolate All live on the root, permanently."""
        if self.doc is None:
            return
        menu = QMenu(self)
        menu.addAction("Show All", self._show_all_bodies)
        if self.doc.isolation_active():
            menu.addAction("Unisolate All", self._unisolate_all)
        if self.doc.attachment_issues:      # M153: the badge's door —
            #   offered ONLY when issues exist (a door onto nothing is
            #   noise); the dialog reads the structured twins (§1.2).
            menu.addSeparator()
            menu.addAction("Manage Lost Attachments\u2026",
                           self._manage_attachments)
        self._root_menu_open = menu               # inspectable, like
        menu.popup(pos)                           # _mark_menu

    def _manage_attachments(self):
        """M153: rung D's dialog — the amber badge becomes a door. The
        rows are STRUCTURED ISSUE RECORDS, never parsed prose (M152
        pinned the sentences byte-exact; this is their twin); every
        verb is a kernel state-layer method, and each act recomputes
        through the normal bridge so badges, tree and status all get
        the last word."""
        d = self.doc
        if d is None:
            return
        if not d.attachment_issues:
            self.status.showMessage("No lost attachments to manage — "
                                    "every host is home", 4000)
            return
        _AttachmentsDialog(self).exec()

    def action_activate_body(self, name):
        """M104: make `name` the body every new feature lands in."""
        if self.doc is None or not self.doc.set_active_body(name):
            return
        self.rail.tree.reload()
        self.status.showMessage(f"Active body: {name} — new features land "
                                "here", 4000)

    def action_new_body(self):
        """Create ▸ New body (M104): a fresh body becomes active, so the
        next feature builds its own solid instead of joining the current
        one — the first step of a multi-body part."""
        if self.doc is None:
            return
        self._capture()
        b = self.doc.add_body()
        self.rail.tree.reload()
        self.viewport.refresh()
        self.status.showMessage(
            f"{b['name']} is now active — the next feature builds there",
            5000)

    def _datum_delete_ok(self, name: str) -> bool:
        """M125 part 3: deleting a datum that features bind BY NAME is
        Fusion territory for silent corruption — we warn first and name
        every feature that will fail at recompute.  No references, no
        ceremony."""
        if self.doc is None:
            return False
        refs = self.doc.datum_references(name)
        if not refs:
            return True
        ans = QMessageBox.question(
            self, "Datum still referenced",
            f"{name} is used by {len(refs)} feature(s):\n  "
            + "\n  ".join(refs)
            + "\n\nDeleting it makes them fail at recompute until they "
              "are edited or removed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            self.status.showMessage(
                f"{name} kept — {refs[0]} still depends on it", 5000)
            return False
        return True

    def _delete_plane(self, name):
        if self.doc and self._datum_delete_ok(name) and \
                self.doc.remove_plane(name):
            self._unsaved = True
            self.rail.tree.reload()
            self.recompute()      # M125: may now fail honestly — the
            self.status.showMessage(f"Deleted {name}", 3000)  # M118 badge

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

    def _start_sketch_on_face(self, point, normal, body=None,
                              tri=None):
        """M140 rung A: the frame is DERIVED, never clicked. Origin
        = the picked body's bbox anchor PROJECTED onto the face
        plane — the natural corner the body was built from, so the
        same face yields the same frame whatever the cursor
        touched (the click-point origin was half the complaint);
        axes ride the nearest-axis law (face_axes). M141 rung B-lite:
        the host face's OWN loop lands as refs the moment the
        sketch opens (vendor law, live-verified: the face speaks
        first; the P key's full-section project() stays opt-in)."""
        if self.doc is None or not self._discard_guard():
            return
        n = np.asarray(normal, float)
        n = n / max(np.linalg.norm(n), 1e-12)
        u, v = face_axes(n)
        p = np.asarray(point, float)
        o = p                              # no body to anchor on:
        solids = self.doc.body_solids()    # the plane's own point
        if body in solids:
            o = np.asarray(solids[body].to_trimesh().bounds[0],
                           float)
        origin = o + float((p - o) @ n) * n          # anchor projected
        model = SketchModel(plane="FACE")
        model.axes = [u.tolist(), v.tolist()]
        model.origin = tuple(float(t) for t in origin)
        model.name = self._face_sketch_name(body)
        model.handle = self._pick_handle(body, p, n)     # M142
        landed = 0
        if tri is not None:
            model.refs = self._host_face_refs(int(tri), model)
            landed = len(model.refs)
        self._begin_sketch(model)
        self.status.showMessage(
            f"Sketching on {model.name} — origin at the body's own "
            "corner; X extrudes outward from the face"
            + (f"; its outline landed with it ({landed} loop"
               f"{'s' if landed != 1 else ''}, dimensionable)"
               if landed else ""), 6000)

    def _pick_handle(self, body, point, normal):
        """M142: at pick the plane under the cursor is matched
        against what the body's features DECLARE — the NEWEST
        publisher wins (a fresh cap shadows the face it grew from,
        which is the face the user saw). A plane nobody publishes
        gets no handle and stays a snapshot: honest, and exactly
        yesterday's behaviour. body=None keeps the old arity's law:
        no attribution invented."""
        if body is None or self.doc is None:
            return None
        best = None
        cos1 = math.cos(math.radians(1.0))
        for f in self.doc.features:
            if (getattr(f, "body", None) or "Body 1") != body:
                continue
            for part, pt, n in self.doc._published_planes(f):
                if (float(n @ normal) > cos1
                        and abs(float((point - np.asarray(pt, float))
                                      @ n)) < 1e-6):
                    best = {"feature": f.name, "part": part}
        return best

    def _host_face_refs(self, tri, m):
        """M141: the host face's loop mapped into the sketch frame.
        The picked triangle's coplanar-ADJACENCY group (M59's _gid:
        disjoint coplanar faces never merge, so the plate-top loop
        is the plate's, not the world's) is validated by face_region
        — outer + holes in the face's own basis — then re-expressed
        in the sketch's (origin, u, v). NOT project(): the slice
        answers "what stands at this height", the loop answers
        "which face am I on" — and a re-include REPLACES (M82 law)."""
        from ..core.presspull import face_region
        tm = self.viewport._tm
        if tm is None:
            return []
        region = face_region(tm, self.viewport._group(tri))
        if region is None:
            return []                      # curved/degenerate group:
        u = np.asarray(m.axes[0], float)   # the loop honestly says
        v = np.asarray(m.axes[1], float)   # nothing
        o = np.asarray(m.origin, float)
        p0 = np.asarray(region["point"], float)
        ru = np.asarray(region["u"], float)
        rv = np.asarray(region["v"], float)
        refs = []
        for pts in [np.asarray(region["outer"], float)] + \
                   [np.asarray(h, float) for h in region["holes"]]:
            w = p0 + pts[:, :1] * ru + pts[:, 1:] * rv
            refs.append({"pts": np.column_stack([(w - o) @ u,
                                                 (w - o) @ v]),
                         "closed": True})
        return refs

    def _face_sketch_name(self, body):
        """Host-named, collision-counted like every other feature."""
        base = f"Sketch on {body}" if body else "Sketch on face"
        used = {f.name for f in self.doc.features}
        name, k = base, 2
        while name in used:
            name, k = f"{base} {k}", k + 1
        return name

    def _contact_op(self, m, outer):
        """M140's contact preset — PROBE, don't guess (the law the
        hole command has kept since M31 and press-pull since M20,
        missing only from the sketch path): sample material on both
        sides of the profile centre along the face normal. Behind
        only -> JOIN outward (the classic top-face boss, the old
        union law intact); BOTH sides -> the face is buried and the
        sketch means a pocket -> CUT; AHEAD only (the normal dove
        into the body) -> JOIN with the frame mirrored so the
        extrude still runs away from material."""
        u, v = plane_uv(m.plane, m.axes)
        n = np.cross(u, v)
        if self.doc.result is None:
            return "union", False       # the doc's first solid: a
        c = np.asarray(outer, float).mean(axis=0)  # FACE-frame sketch
        w = np.asarray(m.origin, float) + c[0] * u + c[1] * v
        tm = self.doc.result.to_trimesh()
        hits = list(tm.contains([w + n * 0.5, w - n * 0.5]))
        front, back = bool(hits[0]), bool(hits[1])
        if front and back:
            return "subtract", False
        if front:
            return "union", True
        return "union", False

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
            thicken_owns = any(isinstance(f, ThickenFeature)
                               and f.sid == sid
                               for f in self.doc.features)
            owns = hole_owns or sweep_owns or loft_owns or thicken_owns
            if owns:
                self._capture()
            if hole_owns:
                self._sync_holes(sid, payload)
            if sweep_owns:
                self._sync_sweeps(sid, payload)
            if loft_owns:
                self._sync_lofts(sid, payload)
            if thicken_owns:
                self._sync_thickens(sid, payload)
            self._update_sketch_features(sid, profiles, payload,
                                         capture=not owns)
            self.sketch.set_model(SketchModel())     # committed: clear editor
            self._end_sketch_view()                  # M191 R2: the marker
            self._show_page(self.viewport)           #   goes home with you
            self.recompute()
            self.status.showMessage(f"Updated {name} — solid recomputed", 5000)
            return
        # M201 R5: the page's Operation answer exists ONLY for the
        # extrude door off a non-FACE plane; every other mouth (the
        # revolve door - its own page is UNPROMISED - and the FACE
        # sketch, where the M140 probe owns operation) writes None
        # here and keeps the rung-era union/probe law untouched.
        eop = None
        if revolve:
            # M191 R5 [SKT-CENTERLINE-GEOMETRY]: a DECLARED centerline
            # IS the axis now - the dry-run measures sides against it,
            # and the u=0 law survives untouched for every sketch that
            # declares none (the vendor's own default).
            _axis, _axerr = self._sketch_revolve_axis(m)
            if _axerr is not None:
                self.status.showMessage("Revolve refused: " + _axerr, 6000)
                return
            for outer, _holes in profiles:
                if self._profile_crosses_axis(outer, _axis):
                    # M189 R5 [LAW-61(a)]: a dry-run profile check BEFORE
                    # any dialog or capture - tier (a) by the ladder's own
                    # logic (the wrapped shape hid from R2's grep: the
                    # whole-set gate caught it, law 18).
                    self.status.showMessage(
                        "Revolve refused: a profile crosses the "
                        + ("declared centerline - Fusion revolves about "
                           "the line the sketch declares, so keep each "
                           "profile on a side of it"
                           if _axis is not None else
                           "sketch's vertical axis (the u=0 line through "
                           "the origin) - Fusion revolves profiles about "
                           "it, so keep each one on a side"), 6000)
                    return
            # M201 R6 [SLD-REF-REVOLVE, verbatim] "Extent Type:
            # Establishes the end point of the revolve. Partial:
            # Revolves the profile around the axis to an angle value
            # that you specify. To Object: Revolves to a body, face,
            # or plane that you select. Full: Revolves the profile 360
            # degrees around the axis." + "Angle: Specifies the angle
            # to revolve around the axis. If the Extent Type is set to
            # Partial, specify the angle value" + "Operation: Select
            # an operation to control how the feature affects the
            # design" (the SAME five voices as the extrude page - and
            # the SAME three are ours to speak: the fold is feature-
            # agnostic, and unlike the extrude the revolve has NEVER
            # had a contact probe, so this row opens everywhere).
            # To Object is PICKING - UNPROMISED (R5's coin: never
            # offer a word the door cannot speak). Direction
            # (One Side/Two Sides/Symmetric) stays UNPROMISED: the
            # page SILENTLY splits no angle across the profile plane
            # and our kernel sweeps one way from it (measured: build()
            # is a single Solid.revolve call) - composing the row
            # would INVENT a pairing rule, and inventing is forbidden.
            # "default" appears ZERO times on the page: every rest
            # here is the HOUSE's - Full (angle 360) is what this door
            # has ALWAYS birthed (getDouble rested at 360.0), Join is
            # what the fold has always folded, and the 1..360 bounds
            # are the door's own spin history (the kernel measures:
            # >360 clamps to 360, <=0 is silently EMPTY - the door
            # speaks neither voice). Page order: Extent, Angle,
            # (Direction skipped), Operation.
            v = cmddialog.ask(self, "Revolve", [
                dict(key="extent", label="extent", kind="combo",
                     choices=("Partial", "Full"), default="Full",
                     group="Extent"),
                dict(key="angle", label="angle (degrees)", kind="double",
                     default=360.0, min=1.0, max=360.0, decimals=1,
                     suffix="°", group="Angle"),
                dict(key="op", label="operation", kind="combo",
                     choices=("Join", "Cut", "Intersect"),
                     default="Join", group="Operation"),
            ], remember_key="revolve")
            if v is None:
                return
            eext = str(v["extent"])
            if eext not in ("Partial", "Full"):
                # The R5 fourth-word law, extent edition: refuse
                # naming the words THIS door speaks - and "To Object"
                # the picker must NOT smuggle itself in as a word.
                self.status.showMessage(
                    "Revolve refused: the extent is 'Partial' or "
                    f"'Full', not {eext!r}", 6000)
                return
            # NUMERIC-ENCODES-EXTENT (R4's law, angular sibling): the
            # page ITSELF defines Full as "360 degrees", the kernel
            # keeps no other word for a closed sweep (measured: 360
            # closes the ring and 361/400/720 clamp to the same
            # solid) - so Full WRITES 360.0 and the typed number goes
            # stored-and-inert (M201 R2's conditional-row law,
            # numeric edition); Partial speaks the number. No new
            # field, no file-mouth change: the number IS the voice.
            angle = 360.0 if eext == "Full" else float(v["angle"])
            eop = str(v["op"])
            if eop not in ("Join", "Cut", "Intersect"):
                self.status.showMessage(
                    "Revolve refused: the operation is 'Join', 'Cut' "
                    f"or 'Intersect', not {eop!r}", 6000)
                return
            if eop == "Cut" and self.doc.result is None:
                self.status.showMessage(
                    "Revolve refused: a cut needs material to cut - "
                    "the first feature cannot be a subtract", 6000)
                return
            # The fold's quirk mirrors R5: a first INTERSECT is NOT
            # refused (with nothing to intersect the feature stands)
            # - so the sentence must stay silent about material that
            # was never there.
            eop_mat = self.doc.result is not None
        else:
            # M201 R3 [SLD-REF-EXTRUDE]: the page IS the EXTRUDE TOOL's
            # dialog - its rows are the CREATION voice, so the door grew
            # Direction and its two conditional siblings next to the one
            # number it always asked (M47 law: ONE dialog, never a
            # prompt chain). Page order: Direction, Measurement, then
            # the distance (the page words it "Distance" under an
            # Extent Type this door cannot honour - To Object and All
            # are picking and visibility - so the row keeps the house's
            # own word, height, never a quoted vendor label). The rows
            # outside the chosen direction are asked, stored and INERT
            # (the modal door cannot open and close rows mid-command -
            # the conditional-row law, same coin as the lever).
            # Resting voices: direction "one" - the door has ONLY ever
            # birthed one-side records; the 5.0 default is the house's
            # own (the page names none: "default" appears zero times).
            fields = [
                # M201 R4 [SLD-REF-EXTRUDE, verbatim]: "Start:
                # Establishes the starting point for the extrusion.
                # Profile Plane: Starts extrusion from the profile
                # plane. Offset: Starts extrusion a specified offset
                # distance from the profile plane. Object: Starts
                # extrusion from a face or plane that you select" +
                # "Offset (Offset or Object start only): Specify
                # distance to offset extrusion from profile plane".
                # THE NUMERIC-ONLY VOICE: Object is PICKING and stays
                # unpromised, so the row ENCODES the two honored
                # starts - 0.0 is the page's own "Profile Plane", what
                # this door has ALWAYS birthed (and the page names no
                # default anywhere: "default" appears zero times). The
                # page words no sign rule - silence is silence - so
                # the house coin rules: a signed number. Page order:
                # the Start rows sit ABOVE the Direction row.
                dict(key="offset", label="offset from the plane",
                     kind="double", default=0.0, min=-1e5, max=1e5,
                     decimals=2, group="Start"),
                dict(key="direction", label="direction", kind="combo",
                     choices=("one", "two", "symmetric"), default="one",
                     group="Direction"),
                dict(key="measurement", label="measurement (symmetric)",
                     kind="combo", choices=("whole", "half"),
                     default="whole", group="Direction"),
                # M201 R9 [SLD-REF-EXTRUDE, verbatim] "Extent Type:
                # Establishes the end point of the extrusion. Distance:
                # Extrudes to a distance that you specify | All:
                # Extrudes through all visible bodies along the
                # extrusion direction." "To Object: Extrudes to a body,
                # face, or plane that you SELECT" is a PICK and stays
                # UNPROMISED (R4's Object-start coin - this door
                # speaks names and numbers it owns). NUMERIC ENCODES
                # EXTENT (R4's law, Extent edition): the row speaks
                # the two voices this tool honours; "distance" is the
                # rest - what this door has ALWAYS birthed (the page
                # names no default: "default" counts ZERO on both
                # pages, so every rest is the house's). Page order:
                # Extent Type sits AFTER Measurement (#9) and BEFORE
                # the Distance numeric (#10) - the number it gates.
                dict(key="extent", label="extent", kind="combo",
                     choices=("distance", "all"), default="distance",
                     group="Distance"),
                dict(key="height", label="height", kind="double",
                     default=5.0, min=0.01, max=1e5, decimals=2,
                     group="Distance"),
                dict(key="height2", label="height 2 (second side)",
                     kind="double", default=0.0, min=0.0, max=1e5,
                     decimals=2, group="Distance"),
                # M201 R9 [SLD-REF-EXTRUDE, verbatim] "Flip (All
                # extent type only): Flips the extrusion over the
                # selected profile plane" + the how-to's verb "Click
                # Flip to reverse the extrusion direction over the
                # profile plane" - RE-AIM is the house coin (measured
                # pair: a start plane 8 up the 10 slab cuts the 2 mm
                # ahead unflipped, 13,400, and the 8 behind flipped,
                # 8,600). THE WIDGET IS THE HOUSE'S: the page never
                # says checkbox or icon (its one "Check to" idiom
                # belongs to Tangent Chain), so the door offers the
                # house checkbox and claims nothing about the vendor's
                # control. Gated "All extent type only" by its OWN
                # qualifier, so at the distance rest the word is
                # asked, stored and INERT (R2's conditional-row coin).
                # Page order: Flip (#14) sits AFTER the distance rows
                # (#10/#11) and BEFORE Wall Thickness (#16).
                dict(key="flip", label="flip (all extent only)",
                     kind="check", default=False, group="Distance"),
                # M201 R8 [SLD-REF-EXTRUDE, verbatim]: "Type: Extrude:
                # Extrudes the entire area within selected closed
                # profiles | Thin Extrude: Extrudes a thin wall along
                # selected open or closed profiles" + "Wall Thickness
                # (Thin Extrude type only): Specify wall thickness for
                # thin extrusion" + "Wall Location (Thin Extrude type
                # only): Determines how the wall thickness is extruded
                # relative to the profile. Side 1: Offsets extrusion
                # to one side of the profile. Side 2: Offsets
                # extrusion to one side of the profile. Center:
                # Centers the extrusion on the profile." THE NUMBER
                # ENCODES THE TYPE ROW (R4's law, Type edition): 0.0
                # IS "Extrude" - the whole area, what this door has
                # ALWAYS birthed (and "default" counts ZERO on both
                # pages, so every rest here is the house's) - and any
                # positive number IS the page's "Thin Extrude" at that
                # Wall Thickness. No Type combo re-asks what the
                # number answers. THE SIDE WORDS ARE THE HOUSE'S: the
                # page describes Side 1 and Side 2 IDENTICALLY and
                # never says which is which (its own asset file is
                # even named "outside" for Side 2) - our coin measures:
                # side 1 stands OUTSIDE the profile line (the 3,960
                # witness), side 2 INSIDE it (3,240), center straddles
                # (3,600). PAGE ORDER: the wall rows sit AFTER the
                # distance rows and BEFORE the Operation row. At rest
                # they are asked, stored and INERT (the modal door
                # cannot open and close rows mid-command - the
                # conditional-row law, R3's coin).
                dict(key="wall", label="wall thickness (0 = the "
                                        "whole area)", kind="double",
                     default=0.0, min=0.0, max=1e5, decimals=2,
                     group="Wall"),
                dict(key="wall_location", label="wall location",
                     kind="combo", choices=("side 1", "side 2", "center"),
                     default="center", group="Wall"),
            ]
            # M201 R5 [SLD-REF-EXTRUDE, verbatim] "Operation: Select
            # an operation to control how the feature affects the
            # design. Join: Combines the new body with an existing
            # body | Cut: Cuts an area out of an existing body |
            # Intersect: Creates a body at the intersection of an
            # existing body and the new body | New Body: ... | New
            # Component ... (Hybrid Design type only)". THE THREE
            # BOOLEAN VOICES: our fold needs NO target-picking - a
            # feature cuts/joins/intersects the accumulator of the
            # body it streams into ("a cut in Body 2 leaves Body 1
            # standing"), so Join|Cut|Intersect speak without the
            # page's "Objects To Cut" (which the page itself restricts
            # to EDIT operations); New Body / New Component stay
            # UNPROMISED (body creation is the mirror door's coin,
            # M200; the vendor restricts the fifth voice to Hybrid
            # Design itself). CONDITIONAL OPENING (M196 R1 law - a row
            # opens only where it rules): on a FACE sketch the M140
            # CONTACT PROBE already owns operation - "PROBE, don't
            # guess" - and a door that never asks never writes (the
            # probe's rung-era mouths stay byte-identical, m140's
            # pins untouched). Rest "Join": the voice this door has
            # ALWAYS birthed off-face (op="union"); the page names no
            # default. Choices ride the mirror door's house coin
            # (capitalised vendor words, "Join"/"New Body", M200).
            # Page order: Operation sits AFTER the distance rows.
            if m.plane != "FACE":
                fields.append(
                    dict(key="op", label="operation", kind="combo",
                         choices=("Join", "Cut", "Intersect"),
                         default="Join", group="Operation"))
            v = cmddialog.ask(self, "Extrude", fields,
                              remember_key="extrude")
            if v is None:
                return
            height = float(v["height"])
            eoffset = float(v["offset"])          # M201 R4: the page's
            #   Offset numeric - 0.0 says "Profile Plane", the start
            #   this door has ALWAYS used; the kernel validates the
            #   number as a number (a spin box cannot speak a wrong
            #   word, so this row grows NO new refusal - the R3 word
            #   refusals stand as they are).
            edirection = str(v["direction"])
            esym = edirection == "symmetric"       # the paper follows
            #                                       the word, always in
            #                                       the door's own coin
            emeas = str(v["measurement"])
            eheight2 = float(v["height2"])
            # M201 R9 [SLD-REF-EXTRUDE]: the extent rows, READ THROUGH
            # .get so every LEGACY scripted answer (m165's shared
            # reply and every remembered dict born before today)
            # speaks THE DISTANCE it always spoke - "distance" is the
            # voice every file holds. Zero rewrites, R5/R7/R8's coin.
            eextent = str(v.get("extent", "distance"))
            eflip = bool(v.get("flip", False))
            # M201 R8 [SLD-REF-EXTRUDE]: the wall rows, READ THROUGH
            # .get so every LEGACY scripted answer (m165's shared
            # reply and every remembered dict born before today)
            # speaks THE WHOLE AREA - 0.0 IS "Extrude", the voice this
            # door has always birthed. Zero rewrites, R5/R7's coin.
            ewall = float(v.get("wall", 0.0))
            eloc = str(v.get("wall_location", "center"))
            # M201 R5: the Operation answer - None on a FACE sketch
            # (the M140 probe owns operation there; the row never
            # opened and this door writes no word it did not ask).
            eop = None if m.plane == "FACE" else str(v["op"])
            if eop is not None and eop not in ("Join", "Cut",
                                               "Intersect"):
                self.status.showMessage(
                    "Extrude refused: the operation is 'Join', 'Cut' "
                    f"or 'Intersect', not {eop!r}", 6000)
                return
            if eop == "Cut" and self.doc.result is None:
                # The M197 precheck law, operation edition: the fold
                # refuses a first-feature subtract by name at recompute
                # (m118 pins that mouth), but a door that lets it in
                # leaves a dead undo step - refuse BEFORE the capture,
                # quoting the fold's own words.
                self.status.showMessage(
                    "Extrude refused: a cut needs material to cut - "
                    "the first feature cannot be a subtract", 6000)
                return
            # INTERSECT is NOT refused on an empty body: the fold's own
            # quirk lets a first intersect stand as the feature itself
            # (nothing to intersect WITH). The door mirrors the fold's
            # refusal SET exactly and invents none - but the sentence
            # must not claim an intersection with material that was
            # never there, so the door NOTES what it found.
            eop_mat = self.doc.result is not None
            # M197 door law, preflight edition: the fold refuses these
            # words (the R2 kernel law), but a door must refuse BEFORE
            # the capture - a refused door leaves no undo step behind.
            # A combo can only offer the page's voices in production;
            # this guards the scripted and future mouths.
            if edirection not in ("one", "two", "symmetric"):
                self.status.showMessage(
                    "Extrude refused: the direction is 'one', 'two' or "
                    f"'symmetric', not {edirection!r}", 6000)
                return
            if edirection == "symmetric" and emeas not in ("whole",
                                                           "half"):
                self.status.showMessage(
                    "Extrude refused: the measurement is 'whole' or "
                    f"'half', not {emeas!r}", 6000)
                return
            if eextent not in ("distance", "all"):
                # M201 R9 preflight (the same law, extent edition): a
                # combo cannot speak a wrong word, a scripted answer
                # can - and the page's THIRD voice, "To Object", is
                # the PICK this tool does not promise, so it must
                # never smuggle itself in as a word. Refuse BEFORE the
                # capture: a refused door leaves no undo step.
                self.status.showMessage(
                    "Extrude refused: the extent is 'distance' or "
                    f"'all', not {eextent!r}", 6000)
                return
            if eextent == "all" and edirection == "symmetric":
                # The page gives All ONE direction - "along THE
                # extrusion direction" - and words NO straddle law
                # for it: symmetric x all is a record whose rows tell
                # different stories. Refused, not guessed (the
                # thin+taper law, extent edition; the kernel speaks
                # the same words - the door only moves them earlier).
                self.status.showMessage(
                    "Extrude refused: the extent 'all' and the "
                    "symmetric straddle tell different stories - All "
                    "rides ONE extrusion direction and the page "
                    "words no straddle", 6000)
                return
            if ewall < 0.0:
                # The precheck law (M197): a spin resting at 0 cannot
                # speak this word, a scripted answer can - and a door
                # that lets it in leaves a dead undo step. Refuse
                # BEFORE the capture, naming the house coin (the page
                # words no bounds - silence is silence).
                self.status.showMessage(
                    "Extrude refused: the wall thickness is 0 (the "
                    f"whole area) or a positive number, not "
                    f"{ewall:g}", 6000)
                return
            if ewall > 0.0 and eloc not in ("side 1", "side 2",
                                            "center"):
                self.status.showMessage(
                    "Extrude refused: the wall location is 'side 1', "
                    f"'side 2' or 'center', not {eloc!r}", 6000)
                return
        self._capture()
        for i, (outer, holes) in enumerate(profiles):
            tag = name if len(profiles) == 1 else f"{name} #{i + 1}"
            face = m.plane == "FACE"
            axes = [list(map(float, a)) for a in m.axes] if face else None
            op = "union"
            if face and not revolve:
                op, flip = self._contact_op(m, outer)
                if flip:
                    axes = [[-t for t in axes[0]], axes[1]]
            elif eop is not None:
                # M201 R5: the door ASKED the page's Operation row -
                # the answer writes, in the kernel's own words (the
                # fold's coin). Join is what this door has always
                # birthed off-face; the mapping is the house menu's
                # (browser ▸ Boolean operation: Join/Cut/Intersect).
                op = {"Join": "union", "Cut": "subtract",
                      "Intersect": "intersect"}[eop]
            placement = tuple(m.origin) if face else (0.0, 0.0, 0.0)
            sketch = dict(payload, regions=len(profiles), region=i)
            common = dict(name=tag, outer=np.asarray(outer),
                          holes=[np.asarray(h) for h in holes],
                          op=op, plane=m.plane, axes=axes,
                          placement=placement, sketch=sketch,
                          sid=m.sid, region=i)
            if not revolve and getattr(m, "handle", None):
                common["handle"] = dict(m.handle)   # M142: extrude
            #                                          only, for now
            if revolve and (_ax := self._sketch_revolve_axis(m)[0]):
                common["axis"] = _ax               # M191 R5: the sketch
            #                                          declared its own
            #                                          axis - the kernel
            #                                          turns on THAT
            self.doc.add(RevolveFeature(angle=angle, **common) if revolve
                         else ExtrudeFeature(height=height,
                                             direction=edirection,
                                             symmetric=esym,
                                             measurement=emeas,
                                             extent=eextent,
                                             height2=eheight2,
                                             flip=eflip,
                                             offset=eoffset,
                                             wall=ewall,
                                             wall_location=eloc,
                                             **common))
        self.sketch.set_model(SketchModel())         # committed: clear editor
        self._show_page(self.viewport)
        self.recompute()
        self.viewport.refresh(fit=True)
        if revolve:
            # M201 R6: the operation tail rides the SAME coin as the
            # extrude's R5 tail (the fold is feature-agnostic). Join
            # is the rest: NO tail - the sentence stays BYTE-IDENTICAL
            # to the rung-era "Revolved N region(s) from X by Y°"
            # (this rung pins that voice: it was never pinned before).
            # An intersect born on an empty body keeps silent too -
            # the fold's quirk stands the feature, but nothing WAS
            # already there to intersect with.
            rtail = _OP_TAILS.get(eop) or ""
            if eop == "Intersect" and not eop_mat:
                rtail = ""
            self.status.showMessage(
                f"Revolved {len(profiles)} region(s) from {name} "
                f"by {angle:g}°{rtail}", 6000)
        else:
            fresh = self.doc.features[-len(profiles):]
            why = (" — cut: material sat on both sides of the face"
                   if m.plane == "FACE" and any(
                       f.op == "subtract" for f in fresh) else "")
            # M201 R3: the sentence tells the record's OWN voice. The
            # one-side sentence stays BYTE-IDENTICAL to the rung-era
            # one (the door's resting voice is the voice it always
            # had); the other two grow tails that say what the page's
            # swapped words MEAN as this tool does them - whole h
            # straddles h/2 each side, half h reaches h EACH side
            # (the vendor's words, obeyed as written, never fixed).
            if eextent == "all":
                # M201 R9 [SLD-REF-EXTRUDE]: at All the typed number
                # is INERT - the page gates its OWN Distance row
                # "(Distance extent type only)" - so the sentence
                # speaks what the fold REACHES, not millimetres it
                # did not use (the wall and start tails still ride:
                # they are live words at all, measured).
                if edirection == "two":
                    voice = "through every body on both sides"
                elif eflip:
                    voice = ("through every body behind the start "
                             "plane")
                else:
                    voice = "through every body ahead"
            elif edirection == "two":
                voice = (f"by {height:g} mm and {eheight2:g} mm "
                         "the other side")
            elif edirection == "symmetric" and emeas == "half":
                voice = f"by {height:g} mm to each side of the plane"
            elif edirection == "symmetric":
                voice = (f"by {height:g} mm straddling the plane "
                         "(half to each side)")
            else:
                voice = f"by {height:g} mm"
            # M201 R4: the Start/Offset tail says WHERE the wall
            # starts when the number moved the plane; at 0.0 the
            # sentence is the R3 one, byte for byte.
            start = (f" starting {eoffset:g} mm off the plane"
                     if eoffset != 0.0 else "")
            # M201 R8: the wall tail says WHERE the wall stands when
            # the number exists - the page's OWN readings: "Center:
            # Centers the extrusion on the profile" and the side
            # words (which the page describes as "Offsets extrusion
            # to one side of the profile"). At 0.0 the sentence is
            # the R5 one, byte for byte.
            wtail = ""
            if ewall > 0.0:
                where = ("centered on the profile" if eloc == "center"
                         else f"offset to one side ({eloc})")
                wtail = f" — with a {ewall:g} mm wall {where}"
            # M201 R5: the operation tail says what the row ASKED the
            # feature does to the material it streams into - the fold
            # reads and writes the feature's OWN body accumulator, so
            # "what was already there" is the honest object. Join is
            # the rest: no tail, the sentence byte-identical. The FACE
            # probe has its own why-sentence (the "why" above); the
            # row never opened there, so the tails never co-write.
            optail = _OP_TAILS.get(eop) or ""
            if eop == "Intersect" and not eop_mat:
                optail = ""            # nothing WAS already there -
            #                          the fold keeps the feature
            #                          itself (its quirk, honest);
            #                          the sentence says nothing it
            #                          did not do
            self.status.showMessage(
                f"Extruded {len(profiles)} region(s) from {name} "
                f"{voice}{start}{wtail}{why}{optail}", 6000)

    def action_hole(self):
        """Fusion Hole: each circle in the current sketch drills one hole —
        simple, counterbore or countersink — into the existing solid."""
        if self.doc is None:
            return
        m = self.sketch.model
        circles = [c for c in m.sketch.circles if not c.construction] \
            if m is not None else []
        if not circles:
            # M189 R4 [LAW-61(a)]: the recipe cure speaks where the eye is.
            self.status.showMessage("Draw circles first — each circle "
                                    "becomes one drilled hole. Sketch on a "
                                    "face (double-click), add the circles, "
                                    "run Hole", 6000)
            return
        if not self.doc.features or self.doc.result is None:
            # M189 R5 [LAW-61(a)]: a precondition that hid in a wrapped
            # call from R3's grep - same law, now same voice.
            self.status.showMessage("Nothing to hole yet — extrude a "
                                    "body first", 5000)
            return
        opts = HoleDialog.ask(self, [2 * c.r for c in circles])
        if opts is None:
            return
        # M201 R7 [SLD-REF-HOLE-DIALOG] "Tip Angle: Specifies the angle
        # of the drill point for the hole" - read through .get so every
        # LEGACY answer dict (m31/m49/m107/m128 scripted a values()
        # without this word) drills FLAT, the voice it was born with:
        # zero rewrites, the same coin R5 paid the extrude router.
        tip = float(opts.get("tip_angle", 0.0))
        if not (0.0 <= tip < 180.0):
            # The precheck law (M197), PAID BY THE GATE THAT CAUGHT
            # THIS CODE BREAKING IT: the first draft refused AFTER the
            # capture, leaving the dead undo step the law forbids -
            # the refusal must sit BEFORE anything is captured. The
            # spin box cannot speak this word (its range is the house
            # coin); a scripted answer can, and the door says no.
            self.status.showMessage(
                "Hole refused: the drill point angle is 0 (flat) or "
                f"between 0 and 180 degrees, not {tip:g}", 6000)
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
        t_size = opts.get("thread_size", thread if tap_pitch else "")
        t_class = opts.get("thread_class", "") if tap_pitch else ""
        t_mode = (opts.get("thread_mode", "modeled") if tap_pitch
                  else "modeled")
        drill = opts.get("drill")          # M107 preset Ø; the circle places only
        payload = model_to_dict(m)
        owned = [f for f in self.doc.features
                 if isinstance(f, HoleFeature) and f.sid == m.sid]
        for i, c in enumerate(circles):
            w = origin + u * float(c.c.x) + v * float(c.c.y)
            rad = (drill / 2 if drill                  # M107 preset → circle places
                   else tap_dia / 2 if tap_pitch       # tapped: tap-drill core
                   else float(c.r))
            L = (diag + 4 * max(rad, cb_r, cs_r)) if through else depth
            tlen = L if tap_pitch else 0.0                   # thread the full depth
            kind = (" counterbore" if cb_r > rad else
                    " countersink" if cs_r > rad else "")
            nm = f"Hole {thread}" if tap_pitch else f"Hole Ø{2 * rad:g}"
            if i < len(owned):                # re-drill: update in place
                f = owned[i]
                f.center, f.radius = tuple(w), rad
                f.depth, f.through, f.cut_length = depth, through, float(L)
                f.tip_angle = tip              # M201 R7: re-drill speaks
                #                                 the fresh answer (the
                #                                 params-replaced-not-
                #                                 merged law, m31)
                f.cb_radius, f.cb_depth = cb_r, float(opts["cb_depth"])
                f.cs_radius, f.cs_angle = cs_r, float(opts["cs_angle"])
                f.thread_pitch, f.thread_len = tap_pitch, tlen
                f.thread_size, f.thread_class = t_size, t_class
                f.thread_mode = t_mode
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
                tip_angle=tip,
                cb_radius=cb_r, cb_depth=float(opts["cb_depth"]),
                cs_radius=cs_r, cs_angle=float(opts["cs_angle"]),
                thread_pitch=tap_pitch, thread_len=tlen,
                thread_size=t_size, thread_class=t_class,
                thread_mode=t_mode,
                sketch=dict(payload), sid=m.sid, cidx=i))
        for f in owned[len(circles):]:        # circles deleted while editing
            self.doc.features.remove(f)
        self.sketch.set_model(SketchModel())
        self._editing_sid = None
        self._end_sketch_view()                  # M191 R2: leave = un-park
        self._show_page(self.viewport)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Drilled {len(circles)} {opts['type']} hole(s)"
            + (" — through all" if through else f" — {depth:g} mm deep")
            # M201 R7: the drill point joins the sentence ONLY when it
            # is not flat - the page's own words ("Drill Point: Select
            # Flat, or Angle"); the flat rest sentence is the rung-era
            # one, byte for byte.
            + (f" — with a {tip:g}° drill point" if tip else "")
            + (f"  ·  {thread}"
               f"[{opts.get('thread_class', '') or '6H'}, "
               f"{opts.get('thread_mode', 'modeled')}]"
               if tap_pitch else ""), 6000)

    def _on_face_selection(self, n: int = 0):
        """Measure-on-pick (Fusion's Inspect>Measure, live): picked faces
        answer in the status bar; no selection shows the body's numbers."""
        if self.doc is None or self.doc.result is None:
            return
        groups = self.viewport.selected_groups()
        # M162 LAW-5.2: whatever owns the picked faces gets its browser
        # ancestry underlined — canvas to tree, one dotted line. (The
        # empty answer clears it: no selection, no lineage lit.)
        self.rail.tree.set_ancestry(self.viewport.selected_body())
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
        # M131 cross-highlight, the other way: light the browser row for
        # the body that owns the picked faces (select_body blocks signals
        # so this never bounces back and re-washes the whole body).
        owner = self.viewport.selected_body()
        if owner:
            self.rail.tree.select_body(owner)

    def action_shell(self):
        """Fusion Shell: hollow the body to thin walls, removing one face
        to open it — enclosures, cases, boxes."""
        if self.doc is None or self.doc.result is None:
            # M189 R3 [LAW-61(a)]: a precondition is INPUT - the same
            # sentence the majority (Draw, Publish, Project...)
            # already murmur in the status bar, lower voice.
            self.status.showMessage("Nothing to shell yet — extrude "
                                    "or import a solid first", 5000)
            return
        if any(isinstance(f, ShellFeature) for f in self.doc.features):
            # M189 R4 [LAW-61(a)]: a state notice is not a modal event.
            self.status.showMessage("This body is already shelled", 4000)
            return
        face = self.viewport.selected_face()
        if face is None:
            # M189 R4 [LAW-61(a)]: the face-pick guidance steps down.
            self.status.showMessage("Click the face to REMOVE first — the "
                                    "body hollows with that face open, "
                                    "exactly like Fusion's Shell", 6000)
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
            # M189 R2 [LAW-61(a)]: a dry-run rejection that touched no
            # history is RECOVERABLE INPUT - the kernel sentence rides
            # the established status family, not a modal.
            self.status.showMessage(f"Shell refused: {e}", 6000)
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
            # M189 R3 [LAW-61(a)]: precondition -> tier (a) voice.
            self.status.showMessage("Nothing to split yet — extrude "
                                    "or import a solid first", 5000)
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
            # M189 R2 [LAW-61(a)]: dry-run rejection, history untouched.
            self.status.showMessage(f"Split refused: {e}", 6000)
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
            # M189 R4 [LAW-61(a)]: a precondition wearing the information
            # verb - R3's law, wrong modal verb.
            self.status.showMessage("Nothing to print yet — model "
                                    "something first", 5000)
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
                dict(key="fit", kind="combo", label="Print fit δ (M124)",
                     choices=self._FIT_DELTAS,
                     default=str(s.value("printfit/delta",
                                         "0.0 — as-modelled"))),
                dict(key="apply", kind="combo", label="Apply δ",
                     choices=("Label only (geometry unchanged)",
                              "Enlarge holes by δ (export only)"),
                     default=str(s.value("printfit/apply",
                                         "Label only (geometry unchanged)"))),
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
        from ..core import printfit
        delta = float(str(v["fit"]).split()[0])
        enlarge = v["apply"].startswith("Enlarge") and delta > 0.0
        s.setValue("printfit/delta", str(v["fit"]))
        s.setValue("printfit/apply", v["apply"])
        if enlarge:
            with printfit.compensated(self.doc, delta) as (pl, _d):
                self._print_export(path, drop=bool(v["drop"]))
                msg = printfit.describe(pl)
            logservice.info("Print fit: " + msg, source="printfit")
            self.status.showMessage(
                f"Print-fit {msg} — document untouched, "
                f"STL only; beware double compensation if your slicer "
                f"also offsets holes", 8000)
        else:
            self._print_export(path, drop=bool(v["drop"]))
            if delta > 0.0:
                self.status.showMessage(
                    "δ set but Label-only: " + "; ".join(
                        printfit.EXPECTED_DEVIATION), 8000)
            else:
                self.status.showMessage(
                    f"Print-ready STL written to {Path(path).name}", 5000)

    def _print_export(self, path, drop: bool = True):
        """Export the current solid as an STL, optionally resting it on
        the build plate — the document itself is never moved."""
        tm = (printcheck.drop_to_bed(self.doc.result) if drop
              else self.doc.result.to_trimesh())
        tm.export(str(path))

    def action_flat_pattern(self):
        """Tools ▸ Flat Pattern (M145, sheet metal SM1): the blank,
        computed by the SHOP LAW — BA = θ(ri + K·t) off the inside
        face — never by unrolling mesh facets (the band tessellation's
        neutral fibre is the mid-surface: K = 0.5 BY CONSTRUCTION,
        +0.188 mm of silent error per bend the moment the shop says
        0.44). SM1 is NUMBERS: per-bend BA/BD + the flat length,
        reported in the dialog and the status line. The flat GEOMETRY
        on paper is SM2; the parametric FlangeFeature that owns band
        geometry outright (and ends the detector fuzz) is SM3."""
        if self.doc is None:
            return
        solid = self.doc.result
        if solid is None:
            return
        st = self.doc.sheet_states()               # SM3: a parametric
        if st and self.doc.active_body in st:      # sheet OWNS its
            fl = st[self.doc.active_body]["flat"]  # numbers — the K
            self.status.showMessage(               # prompt would be
                f"Parametric sheet: flat {fl['flat_length']:.4f} mm "
                "from the FEATURES; the live 'Flat' view (labels from "
                "the inputs) rides every drawing sheet", 8000)
            return
        from ..core import sheetmetal
        from . import cmddialog
        try:
            bands = sheetmetal.detect_bands(solid)
        except Exception:
            bands = []
        if not bands:
            self.status.showMessage(
                "Flat pattern: no bend bands found — this body is "
                "not a sheet (a bend needs an inside radius)", 6000)
            return
        v = cmddialog.ask(self, "Flat Pattern", [
            dict(key="K", kind="double",
                 label=f"K-factor ({len(bands)} bend(s) found; 0.44 "
                       "is shop folklore, not a standard)",
                 default=sheetmetal.K_DEFAULT)])
        if v is None:
            return
        try:
            u = sheetmetal.unfold_flat(solid, K=float(v["K"]))
        except ValueError as e:        # SheetMetalError IS a ValueError
            # M189 R2 [LAW-61(a)]: the preview dry-run refused input -
            # nothing exists yet to lose.
            self.status.showMessage(f"Flat pattern refused: {e}", 6000)
            return
        lines = [f"Bend {i + 1}: theta={b['angle']:.1f}  "
                 f"ri={b['ri']:.2f}  ro={b['ro']:.2f}  "
                 f"BA={b['ba']:.3f}  BD={b['bd']:.3f}"
                 for i, b in enumerate(u["bands"])]
        lines.append("Flanges: " + " + ".join(
            f"{f['extent']:.2f}" for f in u["flanges"]))
        lines.append(f"FLAT: {u['flat_length']:.3f} mm  |  t="
                     f"{u['thickness']:.2f} mm  |  K={u['K']:g}")
        cmddialog.ask(self, "Flat Pattern", [
            dict(key="report", kind="multiline",
                 label="The blank (bend facets never ship — each "
                       "bend contributes BA only)",
                 default="\n".join(lines))])
        # M147 SM2: the report is HALF the command — offer the paper.
        # The active body is the sheet: v1 flattens what the user is
        # holding, not the union of everything visible.
        if QMessageBox.question(
                self, "Flat Pattern",
                "Put the flat on paper?\n\nIt lands as a hidden derived "
                "body '_flat' (no standard view shows it, no 3-D export "
                "carries it) and every drawing sheet gains a 'Flat' "
                "view with one bend centre-line per bend.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) == QMessageBox.Yes:
            body = self.doc.active_body
            self._capture()
            try:
                b, feat = self.doc.add_flat_pattern(body, K=float(v["K"]))
            except (sheetmetal.SheetMetalError, KeyError) as e:
                # M189 R2 [LAW-61(a)]: the sentence drops to tier (a),
                # AND the refused capture unwinds - a refusal may not
                # leave an undo step that undoes nothing (R1's law).
                self._undo.pop()
                self._redo.clear()
                self.status.showMessage(f"Flat pattern refused: {e}", 6000)
                return
            self.recompute()
            self.rail.tree.reload()
            self.status.showMessage(
                f"Flat on paper: {feat.flat_length:.3f} x "
                f"{feat.width:.3f} mm — hidden body '_flat', drawing "
                "view 'Flat'", 6000)
            return
        self.status.showMessage(
            f"Flat: {u['flat_length']:.2f} mm blank · "
            f"{len(u['bands'])} bend(s) · K {u['K']:g}", 5000)

    def action_new_sheet(self):
        """Tools ▸ New Sheet (M149, sheet metal SM3): open a
        PARAMETRIC sheet — the flange features OWN the bends, so the
        flat is FORMULA (== the shop law), not a measurement. SM1's
        detector path stays the import job (a sheet is still any
        detectable body); this is the native edge. t, W and the
        material ride the base flange; Add Flange then folds the free
        end, chain order — the v1 attach limit, said out loud."""
        if self.doc is None:
            return
        from ..core import ksolver, sheetmetal
        from . import cmddialog
        v = cmddialog.ask(self, "New Sheet", [
            dict(key="t", kind="double", label="Thickness t (mm)",
                 default=2.0, min=0.01),
            dict(key="width", kind="double", label="Width W (mm)",
                 default=40.0, min=0.01),
            dict(key="leg", kind="double", label="Base leg (mm)",
                 default=60.0, min=0.01),
            dict(key="material", kind="combo",
                 label="Material (picks the ksheet bins)",
                 choices=ksolver.materials())])
        if v is None:
            return
        self._capture()
        try:
            b, feat = self.doc.add_sheet(
                t=float(v["t"]), width=float(v["width"]),
                leg=float(v["leg"]), material=str(v["material"]))
        except (sheetmetal.SheetMetalError, ValueError) as e:
            # M189 R1 [LAW-61]: an illegal sheet parameter is INPUT -
            # tier (a). The kernel's sentence speaks on the status
            # line; the panel simply gets another honest try.
            self.status.showMessage(f"Sheet not created: {e}", 6000)
            return
        self.recompute()
        self.rail.tree.reload()
        self.status.showMessage(
            f"Parametric sheet '{b['name']}': t {v['t']:g} · W "
            f"{v['width']:g} · leg {v['leg']:g} · {v['material']} — "
            "Add Flange folds the free end of the last leg", 7000)

    def action_add_flange(self):
        """Tools ▸ Add Flange (M149 SM3, M151 SM4): the flange hangs
        on a CHOSEN edge — one combo row per FREE in-family end edge,
        and the HEAD row is SM3's free end of the last leg, because
        the M149 fake answers combos with choices[0] and a new combo
        that moves the old law is our bug, not the test's. Guard-first
        like SM1: a body that is not a parametric sheet — or a sheet
        whose every edge already folds — gets the status line, not a
        dialog. K rides the ksheet table LIVE unless the override is
        pinned; reliefs carry the shop defaults gap = t, depth =
        ri + t, both editable, and the pure law refuses anything that
        would sever the bend."""
        if self.doc is None or self.doc.result is None:
            return
        from ..core import ksolver, sheetmetal
        from ..core.document import FlangeFeature
        from . import cmddialog
        st = self.doc.sheet_states()
        body = self.doc.active_body
        if body not in st:
            self.status.showMessage(
                f"Add Flange: '{body}' is not a parametric sheet — "
                "Tools ▸ New Sheet opens one (flanges hang on a free "
                "edge of a leg)", 6000)
            return
        state = st[body]
        if not state["free"]:
            self.status.showMessage(
                f"Add Flange: every edge of '{body}' already folds — "
                "v1 places ONE fold per edge", 6000)
            return
        prior = [x for x in self.doc.features
                 if isinstance(x, FlangeFeature) and x.body == body]
        legs = [r for r in state["flat"]["runs"] if r["kind"] == "leg"]
        rows = []
        for e in state["free"]:
            i = state["order"].index(e["name"])
            x0 = float(legs[i]["x0"])
            rows.append((e, x0 if e["side"] == "start"
                         else x0 + float(legs[i]["extent"])))
        head = next((j for j, (e, _) in enumerate(rows)
                     if e["name"] == prior[-1].name
                     and e["side"] == "end"), None)
        if head:                                # SM3's law rides the
            rows.insert(0, rows.pop(head))      #   HEAD choice
        labels = [f"{e['name']} \u00b7 {e['side']} edge "
                  f"(station {s:.2f} mm)" for e, s in rows]
        v = cmddialog.ask(self, "Add Flange", [
            dict(key="edge", kind="combo", label="Attach to edge",
                 choices=labels),
            dict(key="leg", kind="double",
                 label="New leg length, tangent-to-end (mm)",
                 default=40.0, min=0.01),
            dict(key="angle", kind="double",
                 label="Fold angle (deg; sign = side)", default=90.0,
                 min=-179.9, max=179.9),
            dict(key="ri", kind="double", label="Inside radius (mm)",
                 default=3.0, min=0.01),
            dict(key="pin", kind="check",
                 label="Pin K-factor (off: the ksheet table rides "
                       "the material live)"),
            dict(key="k", kind="double", label="K-factor override",
                 default=sheetmetal.K_DEFAULT, min=0.001, max=1.0),
            dict(key="rel", kind="check", label="Bend relief — "
                 "square notches at both free edges"),
            dict(key="gap", kind="double", label="Relief gap "
                 "(shop default: t)", default=state["t"], min=0.01),
            dict(key="depth", kind="double",
                 label="Relief depth (shop default: ri + t)",
                 default=state["t"] + 3.0, min=0.01)])
        if v is None:
            return
        pick, station = rows[labels.index(v["edge"])]
        hf = next(x for x in prior if x.uid == pick["uid"])
        self._capture()
        try:
            feat = self.doc.add_flange(
                body, leg=float(v["leg"]), angle=float(v["angle"]),
                ri=float(v["ri"]),
                k_factor=float(v["k"]) if v["pin"] else None,
                relief_gap=float(v["gap"]) if v["rel"] else None,
                relief_depth=float(v["depth"]) if v["rel"] else None,
                host=pick["uid"], side=pick["side"],
                witness=0.0 if pick["side"] == "start"
                else float(hf.leg))
        except (sheetmetal.SheetMetalError, ValueError) as err:
            # M189 R2 [LAW-61(a)]: a refused flange parameter is INPUT;
            # the refusal mutates nothing (guard-first kernel) and the
            # capture unwinds.
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Flange refused: {err}", 6000)
            return
        self.recompute()
        self.rail.tree.reload()
        stn = self.doc.sheet_states()[body]
        # the association says WHERE this flange's fold landed: under
        # a PREPEND it is not last, and bends[-1] would read a stranger
        k_used = stn["bends"][stn["bands"][feat.uid]][2]
        warn = self.doc.sheet_warnings
        src = " (pinned)" if feat.k_factor is not None else " (table)"
        self.status.showMessage(
            f"Flange: {feat.leg:g} mm at {feat.angle:g}\u00b0 \u00b7 K "
            f"{k_used:g}{src} \u00b7 on {pick['name']} {pick['side']} "
            f"edge @ {station:.2f} mm"
            + (f" \u2014 {warn[-1]}" if warn else ""), 7000)

    def action_add_fold(self):
        """Tools ▸ Add Fold (M158, sheet metal SM5 rung 1): the fold
        that lives INSIDE one leg — it adds NO wall, splits the leg,
        and the flat rides THROUGH IT UNCHANGED (contract L1). One
        combo row per leg (a fold never chains: it names its host);
        the witness role picks WHICH line of the band the position
        is (axis centres it — the walk's own convention; btl is
        SM4's back-tangent edge currency; iml/oml are the mold
        lines). Guard-first like the flange: non-sheet bodies get
        the status line, and every kernel refusal arrives as a
        warning with the document untouched."""
        if self.doc is None or self.doc.result is None:
            return
        from ..core import sheetmetal
        from ..core.document import FlangeFeature
        from . import cmddialog
        st = self.doc.sheet_states()
        body = self.doc.active_body
        if body not in st:
            self.status.showMessage(
                f"Add Fold: '{body}' is not a parametric sheet — "
                "Tools ▸ New Sheet opens one (folds live inside a "
                "leg)", 6000)
            return
        state = st[body]
        legs = [x for x in self.doc.features
                if isinstance(x, FlangeFeature) and x.body == body]
        if not legs:
            return
        labels = [f"{x.name} \u00b7 leg {x.leg:g} mm" for x in legs]
        wkinds = [("axis", "band axis (line centred on the pick)"),
                  ("btl", "back tangent line (pick is the band's "
                   "start)"),
                  ("iml", "inner mold line (tangent offset from the "
                   "apex)"),
                  ("oml", "outer mold line (apex to outer tangent)")]
        v = cmddialog.ask(self, "Add Fold", [
            dict(key="leg", kind="combo", label="Fold inside leg",
                 choices=labels),
            dict(key="pos", kind="double",
                 label="Fold-line position along the leg (mm)",
                 default=20.0, min=0.0),
            dict(key="wkind", kind="combo", label="Fold line is the",
                 choices=[lab for _, lab in wkinds]),
            dict(key="angle", kind="double",
                 label="Fold angle (deg; sign = side)", default=90.0,
                 min=-179.9, max=179.9),
            dict(key="ri", kind="double", label="Inside radius (mm)",
                 default=3.0, min=0.01),
            dict(key="pin", kind="check",
                 label="Pin K-factor (off: the ksheet table rides "
                       "the material live)"),
            dict(key="k", kind="double", label="K-factor override",
                 default=sheetmetal.K_DEFAULT, min=0.001, max=1.0)])
        if v is None:
            return
        wk = dict((lab, kind) for kind, lab in wkinds)[v["wkind"]]
        host = legs[labels.index(v["leg"])]
        flat_before = state["flat"]["flat_length"]
        self._capture()
        try:
            feat = self.doc.add_fold(
                body, host=host.uid, position=float(v["pos"]),
                angle=float(v["angle"]), ri=float(v["ri"]),
                k_factor=float(v["k"]) if v["pin"] else None,
                wkind=wk, held=host.uid)
        except (sheetmetal.SheetMetalError, ValueError) as err:
            # M189 R2 [LAW-61(a)]: refused input, guard-first kernel -
            # tier (a) voice, capture unwound.
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Fold refused: {err}", 6000)
            return
        self.recompute()
        self.rail.tree.reload()
        stn = self.doc.sheet_states()[body]
        i = stn["bands"][feat.uid]
        flat_now = stn["flat"]["flat_length"]
        self.status.showMessage(
            f"Fold: {feat.angle:g}\u00b0 {wk} at {feat.position:g} mm "
            f"of {host.name} \u00b7 leg split "
            f"{stn['legs'][i]:.3f} + {stn['legs'][i + 1]:.3f} mm "
            f"\u00b7 flat {flat_now:.4f} mm \u2014 "
            + ("UNCHANGED" if flat_now == flat_before
               else "CHANGED (bug!)"), 7000)

    def action_joint(self):
        """Tools > As-Built Joint (M146 grew the door; M201 R18 dressed
        it in the pages' words [ASM-CREATE-AS-BUILT-JOINT +
        AS-BUILT-JOINT-REFERENCE, verbatim]: "The As-Built Joint
        dialog displays." ... "Select two components to position an
        as-built joint between them." The door is the AS-BUILT tool,
        not the Joint command: "Creates a joint between components
        that are already positioned in relation to" each other -
        pick nothing, MOVE nothing at creation (the vendor's Joint,
        the one that teleports a component to its mate, waits for a
        solver). The Motion section's table prints seven Joint Types;
        only Rigid is offered, because only Rigid's definition the
        kernel bakes - "Locks components together and removes all
        degrees of freedom." (Rotation/Translation: None) - and a
        door never promises what cannot land. THE PAGES GATE THE REST
        AWAY THEMSELVES: "For any Joint Type except Rigid, select a
        Mode" - so the Mode trio {Simple | Between Two Faces | Two
        Edge Intersection} and the "Planes, Edges, and Snap" block
        are NOT shown for Rigid; and the Motion-limits row is
        "available when you have selected a Joint Type that has more
        than one degree of motion" - Rigid has ZERO, so Motion,
        Minimum, Maximum, Rest, Preview and With All Limits stand
        gated off by the vendor's own sentence. The six solved types
        (Revolute, Slider, Cylindrical, Pin-Slot, Planar, Ball) and
        their Rotation and Translation axis pickers need joint-origin
        geometry this door never picks - not offered. ROWS SPEAK
        BODIES: the page selects "two components" on the canvas; the
        kernel binds BODIES (components are a later rung), so the
        combos say body - a door may not name a thing the design has
        not got. The tip "you can select them in any order" rides
        honestly: either body may enter either combo; the RECORD is
        directed (mover follows base) because that is what LAW R
        bakes. The ground checkbox is a HOUSE row - no dialog page
        prints a default (verified across the family), and the
        As-Built exemption "either of the components you select can
        be grounded" licenses grounding the base. VENDOR DEFECT,
        flagged not cloned: the As-Built glosses print the typo
        "in relation to each another" (concept and task pages).
        Joints land in the browser's Joints folder, the page's home
        ("the Joints folder in the Browser")."""
        if self.doc is None:
            return
        names = [b["name"] for b in self.doc.body_list()
                 if not b.get("derived")]     # M147: paper isn't a part
        if len(names) < 2:
            self.status.showMessage(
                "As-Built Joint needs two bodies — New Body first "
                "(right-click the browser)", 6000)
            return
        from . import cmddialog
        prefill = self.doc.active_body if self.doc.active_body in names \
            else names[0]
        others = [n for n in names if n != prefill]
        v = cmddialog.ask(self, "As-Built Joint", [
            dict(key="base", kind="combo", label="Base body",
                 choices=names, default=prefill, group="Components"),
            dict(key="mover", kind="combo", label="Moving body",
                 choices=others, default=others[0] if others else None,
                 group="Components"),
            dict(key="type", kind="combo", label="Joint Type",
                 choices=["Rigid"], default="Rigid", group="Motion"),
            dict(key="ground", kind="check",
                 label="Ground the base (it anchors the tree)",
                 default=True)])
        if v is None:
            return
        if str(v.get("type", "Rigid")) != "Rigid":
            self.status.showMessage(
                "As-Built Joint refused: the only Joint Type the "
                "kernel locks is Rigid", 6000)
            return
        base, mover = v.get("base"), v.get("mover")
        self._capture()
        try:
            self.doc.add_joint(str(base), str(mover))
        except ValueError as e:      # ParamError IS a ValueError
            # M189 R2 [LAW-61(a)]: a refused joint is INPUT - tier (a)
            # voice; and the capture this command took BEFORE the
            # guard-first add_joint unwinds (it used to LEAK a step
            # that undid nothing).
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Joint refused: {e}", 6000)
            return
        if not v.get("ground", True):
            self.doc.ground_body(str(base), False)
        self.recompute()
        self.viewport.refresh()
        self.rail.tree.reload()
        self.status.showMessage(
            f"Joint {mover!r} \u2192 {base!r} — position captured "
            "(rigid, 0 DOF); follows the base's placement and rigid "
            "moves, never its growth", 6000)

    def action_interference(self):
        """Tools ▸ Interference (M122, assembly phase 1): where do my
        bodies hurt?  Every clashing PAIR is reported with its exact
        overlap volume — and each clash can become a BODY of its own,
        live in the timeline.  Fusion's Interference command shows the
        clash then forgets it; ours re-solves on every recompute, so
        move a part and the red map of the new collision follows."""
        if self.doc is None or len(self.doc.body_list()) < 2:
            # M189 R4 [LAW-61(a)]: the pair-needed precondition steps down.
            self.status.showMessage("Two bodies minimum — this audit is "
                                    "about where parts CLASH. Model a pair "
                                    "(Body ▸ New Body) first", 6000)
            return
        from ..core import interference
        hits = interference.audit_doc(self.doc)
        if not hits:
            # M189 R4 [LAW-61(a)]: a clean RESULT is a report line, not
            # a dialog - the clash table below already ends in status.
            self.status.showMessage("Nothing clashes — no two bodies "
                                    "share a volume (touching faces do "
                                    "not count)", 5000)
            return
        lines = [f"{h['a']}  ∩  {h['b']}   —   {h['volume']:,.1f} mm³"
                 for h in hits]
        v = cmddialog.ask(self, "Interference", [
            dict(key="report", kind="multiline", label="Clashing pairs",
                 default="\n".join(lines)),
            dict(key="make", kind="check",
                 label="Create one interference body per clash",
                 default=True),
        ])
        if v is None:
            return
        if not v["make"]:
            self.status.showMessage(
                f"{len(hits)} clashing pair(s) — largest "
                f"{hits[0]['volume']:,.1f} mm³", 5000)
            return
        self._capture()
        made = []
        clash_red = {"name": "Clash", "color": [0.95, 0.10, 0.12],
                     "opacity": 1.0}          # brighter than Anodized red:
        for h in hits:                        # xray dims everything 0.35
            b, _f = self.doc.add_interference(h["a"], h["b"])
            self.doc.set_body_appearance(b["name"], clash_red)
            made.append(b["name"])
        # The lens lives INSIDE the union: X-ray reveals the clash seam
        # through the parents (the red solid itself stays depth-shielded
        # until you hide one in the browser — hence the hint below).
        self._renderer.set_visual_style("xray")   # idempotent
        self.recompute()
        self.viewport.refresh()
        logservice.info("Interference: " + "; ".join(
            f"{h['a']}∩{h['b']} {h['volume']:.2f} mm³" for h in hits),
            source="interference")
        self.status.showMessage(
            f"{len(made)} interference bod{'y' if len(made) == 1 else 'ies'}"
            f" created — hide a parent in the browser to see the red "
            f"clash; move a body and it re-solves", 8000)

    def action_mass_properties(self):
        """Fusion's Inspect ▸ Mass Properties (M71): volume, surface
        area, mass at a material density, and the centre of mass —
        every maker's first question ("how heavy will this print?").
        M163 W1: the report moved out of the results QMessageBox into
        the panel's readout row — the numbers arrive while the combo is
        still in your hand, and no modal ever opens."""
        if self.doc is None or self.doc.result is None:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("Nothing to measure yet — add a "
                                    "feature first", 5000)
            return
        s = QSettings()
        last = str(s.value("materials/density", "PLA (1.24)"))
        fields = [dict(key="material", label="Material density (g/cm³)",
                       kind="combo", choices=self._MATERIAL_DENSITIES,
                       default=last if last in self._MATERIAL_DENSITIES
                       else "PLA (1.24)")]

        def commit(v):
            mat = str(v["material"])
            s.setValue("materials/density", mat)
            text, p = self._mass_report(mat)          # final boundary calc
            panel = getattr(self, "_cmd_panel", None)
            if panel is not None:                     # finalise the row,
                panel.set_readout(text)               #  then run() closes
            if "mass_g" in p:
                self.status.showMessage(f"Mass {p['mass_g']:,.2f} g — "
                                        f"{mat}", 5000)

        cmdpanel.run(self, "mass_properties", "Mass Properties — material",
                     fields, readout=lambda v: self._mass_report(
                         str(v["material"]))[0],
                     commit=commit,
                     abort=self._cmdpanel_abort("Mass Properties"),
                     remember_key=False)   # E2: the material memory is
                                           #  QSettings, never the store

    def _mass_report(self, mat: str) -> tuple[str, dict]:
        """The seven-line report, verbatim from the retired box — minus
        the box.  Silent death is the readout law: a model that vanished
        mid-session yields ("", {}) rather than a traceback."""
        try:
            dens = float(mat.split("(")[1].rstrip(")"))
            p = mass_properties(self.doc.result, dens)
            ext = solid_extents(self.doc.result)
            pr = principal_inertia(self.doc.result, dens)
        except Exception:
            return "", {}
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        ex = ext["size_mm"]
        # kg·cm²: g·mm² ÷ 1e5 (what SolidWorks shows; Fusion has no
        # dialog page at all — this is the beat, not the clone)
        kgcm = [i / 100000.0 for i in pr["moments_g_mm2"]]
        text = (
            f"Volume:          {units.V(p['volume_mm3'], u)}\n"
            f"Surface area:    {units.A(p['area_mm2'], u)}\n"
            f"Material:        {mat}\n"
            f"Mass:            {p['mass_g']:,.2f} g\n"
            f"Centre of mass:  ({units.L(p['com'][0], u)}, "
            f"{units.L(p['com'][1], u)}, {units.L(p['com'][2], u)})\n"
            f"Extents:         {units.L(ex[0], u)} \u00d7 "
            f"{units.L(ex[1], u)} \u00d7 {units.L(ex[2], u)}\n"
            f"Inertia (COG):   {kgcm[0]:.3g} / {kgcm[1]:.3g} / "
            f"{kgcm[2]:.3g} kg\u00b7cm\u00b2")
        return text, p

    def action_show_extents(self):
        """M117 Show Extents: the overall size of the part, in the
        document's units — Fusion has no overall-extents readout at
        all [—V]; SolidWorks does. Beat, not clone."""
        if self.doc is None or self.doc.result is None:
            # M189 R4 [LAW-61(a)]: the empty-model GUARD steps down (the
            # multi-line extents REPORT keeps its dialog - it is data,
            # not a sentence).
            self.status.showMessage("Nothing to measure — add a feature "
                                    "first", 5000)
            return
        ext = solid_extents(self.doc.result)
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        sx, sy, sz = ext["size_mm"]
        lo, hi = ext["min_mm"], ext["max_mm"]
        QMessageBox.information(
            self, "Show Extents",
            f"Bounding box:    {units.L(sx, u)} \u00d7 "
            f"{units.L(sy, u)} \u00d7 {units.L(sz, u)}\n"
            f"Diagonal:        {units.L(ext['diagonal_mm'], u)}\n"
            f"From:            ({units.L(lo[0], u)}, "
            f"{units.L(lo[1], u)}, {units.L(lo[2], u)})\n"
            f"To:              ({units.L(hi[0], u)}, "
            f"{units.L(hi[1], u)}, {units.L(hi[2], u)})")
        self.status.showMessage(
            f"Extents {sx:.1f} \u00d7 {sy:.1f} \u00d7 {sz:.1f} mm", 4000)

    def action_document_measures(self):
        """Fusion Tools ▸ Document Measures (M60): choose the
        vocabulary every readout speaks — the model itself stays pure
        millimetres, the unit rides the file as metadata.  M163 W1: the
        readout row speaks the PENDING unit's numbers before you commit
        — a preview that writes nothing."""
        if self.doc is None:
            return
        names = {"Millimetre (mm)": "mm", "Centimetre (cm)": "cm",
                 "Inch (in)": "inch"}
        inv = {v: k for k, v in names.items()}
        fields = [dict(key="unit", label="Length units", kind="combo",
                       choices=list(names),
                       default=inv.get(self.doc.units, "Millimetre (mm)"),
                       group="Primary units")]     # group: W2 (E5)

        def readout(v):
            u = names[str(v["unit"])]
            if self.doc.result is None:
                return f"Readouts will speak {units.LABEL[u]}"
            x, y, z = solid_extents(self.doc.result)["size_mm"]
            return (f"{units.LABEL[u]} — {units.L(x, u)} \u00d7 "
                    f"{units.L(y, u)} \u00d7 {units.L(z, u)}")

        def commit(v):
            if names[v["unit"]] != self.doc.units:
                self.doc.units = names[v["unit"]]
                self._unsaved = True
            self._apply_units()
            self._update_status()
            self.status.showMessage(
                f"Document measures: {units.LABEL[self.doc.units]}", 4000)

        cmdpanel.run(self, "document_measures", "Document Measures",
                     fields, readout=readout, commit=commit,
                     abort=self._cmdpanel_abort("Document Measures"),
                     remember_key=False)   # the DOCUMENT is the memory

    # ---- marking menu (M56) -----------------------------------------------------
    def _wheel_commands(self):
        """The marking wheel's four wedges (M132), one per quadrant in
        Fusion's geometry: top = history (Undo), right = create
        (Extrude), bottom = sketch, left = modify (Move). Commands are
        the same guarded entry points the ribbon calls, so a wedge can
        never do what its button wouldn't."""
        return [("Undo", self.undo),
                ("Extrude", self.action_extrude_key),
                ("Sketch", self.action_new_sketch),
                ("Move", self.action_move_body)]

    def _marking_menu(self, pos=None):
        """Fusion's right-click quick menu: fit / zoom-to / the four
        views / visual styles / display toggles. M140: over a flat
        face it LEADS with the gesture the double-click hid —
        "Sketch on Face — <body>", the discoverable route the
        sketch probe priced as the highest UX payback per line."""
        m = QMenu(self)
        if pos is not None:
            hit, _why = self.viewport.face_probe(pos)
            if hit is not None:
                b = hit["body"]
                m.addAction("Sketch on Face"
                            + (f" — {b}" if b else ""),
                            lambda checked=False, h=hit:
                            self._start_sketch_on_face(
                                h["point"], h["normal"], h["body"],
                                h.get("tri")))
                m.addSeparator()
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
        menu = self._marking_menu(pos)
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
        self.viewport.glide_fit(np.asarray([lo, hi], float))  # M166 R3
        self.viewport.update()
        self.status.showMessage("Zoom window", 2500)

    def _zoom_to_selection(self):
        bbox = self.viewport.selection_bbox()
        if bbox is None and self.doc is not None and self.doc.result:
            bbox = self.doc.result.bounding_box
        if bbox is not None:
            self.viewport.glide_fit(np.asarray(       # M166 R3: flies
                [list(bbox[0]), list(bbox[1])], float))
            self.viewport.update()
            self.status.showMessage("Zoomed to selection", 2500)

    def action_appearance(self):
        """Fusion's Appearance dialog (M52): paint the body with a shop
        material — steel to brass — and dial its opacity.  M163 W1:
        rides the live panel; every committed boundary re-tints the
        RENDERER (never the document), Abort re-syncs paint from the
        doc's truth."""
        if self.doc is None or self.doc.result is None:
            # M189 R3 [LAW-61(a)]: precondition -> tier (a) voice.
            self.status.showMessage("Nothing to paint yet — extrude "
                                    "or import a solid first", 5000)
            return
        from ..core.appearance import MATERIALS, appearance
        cur = (self.doc.appearance or {}).get("name", "(none)")
        choices = ["(none)", "Custom…", *MATERIALS]
        fields = [
            dict(key="preset", label="Material", kind="combo",
                 choices=choices,
                 default=cur if cur in choices else "(none)",
                 group="Body"),
            dict(key="opacity", label="Opacity", kind="double",
                 default=(self.doc.appearance or {}).get("opacity", 1.0),
                 min=0.05, max=1.0, decimals=2, suffix="",
                 step=0.05, group="Body"),
        ]

        def commit(v):
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
                        if old else QColor.fromRgbF(*DARK["solid_base"])
                    col = QColorDialog.getColor(init, self, "Body colour")
                    if not col.isValid():
                        self._undo.pop()       # colour cancelled: no edit
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

        cmdpanel.run(self, "appearance", "Appearance", fields,
                     preview=self._appearance_preview, commit=commit,
                     abort=self._appearance_abort,
                     remember_key="appearance")

    def _appearance_preview(self, v):
        """Cosmetic-only (the press-pull law): the renderer takes the
        tint, the document NEVER hears about it until Commit."""
        if self.doc is None:
            return
        from ..core.appearance import MATERIALS
        try:
            preset, op = str(v["preset"]), float(v["opacity"])
            if preset == "(none)":
                self._renderer.set_base_color(None)
            elif preset == "Custom…":
                self._renderer.set_base_color(        # the doc's truth
                    (self.doc.appearance or {}).get("color"), op)   # until
            else:                                     # a colour is picked
                self._renderer.set_base_color(MATERIALS[preset], op)
        except Exception:
            return                          # previews die silent
        self.viewport.update()              # paint layer only

    def _appearance_abort(self):
        # NOT _cmdpanel_abort: the thing to restore is PAINT, not a
        # geometry ghost.  The doc is the truth; let the renderer re-sync.
        self._apply_appearance()
        self.viewport.refresh()
        self.status.showMessage("Appearance cancelled", 3000)

    def action_move_body(self):
        """Fusion Move/Copy (M53): the RGB triad appears at the body's
        centre — grab an arrow and drag, the body slides along that
        axis exactly as fast as the mouse, release commits the move as
        a parametric feature.  Esc or an empty click cancels."""
        if self.doc is None or self.doc.result is None:
            # M189 R3 [LAW-61(a)]: precondition -> tier (a) voice.
            self.status.showMessage("Nothing to move yet — extrude "
                                    "or import a solid first", 5000)
            return
        blocker = self._move_blocker_msg()
        if blocker:
            self.status.showMessage(blocker, 6000)
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
        if is_copy:
            # M195 R1 [SLD-USE-MOVE-COPY, verbatim]: Create Copy makes
            # a copy "instead of moving the original" and "the new
            # body is not linked to the original body" - so the twin
            # rides into a NEW browser body as its own snapshot stream.
            # (M53's in-body union stays ONLY for files that already
            # carry a copy MoveFeature - the kernel did not change.)
            b = self.doc.copy_body_moved(off_v)
            self.recompute()
            self.viewport.refresh()
            self.status.showMessage(
                f"Body copied — {b['name']} stands on its own at x "
                + f"{off_v[0]:+g}, y {off_v[1]:+g}, z {off_v[2]:+g} mm",
                5000)
            return
        self.doc.add(MoveFeature(name="Move", vec=off_v))
        self.recompute()
        self.viewport.refresh()
        self.status.showMessage(
            "Body moved — x "
            + f"{off_v[0]:+g}, y {off_v[1]:+g}, z {off_v[2]:+g} mm",
            5000)

    def action_rotate_body(self):
        """Fusion Move/Copy's other half (M55): RGB rings appear around
        the body — drag one and the solid spins about that axis, live;
        release commits a parametric rotate feature."""
        if self.doc is None or self.doc.result is None:
            # M189 R3 [LAW-61(a)]: precondition -> tier (a) voice.
            self.status.showMessage("Nothing to rotate yet — extrude "
                                    "or import a solid first", 5000)
            return
        blocker = self._move_blocker_msg()
        if blocker:
            self.status.showMessage(blocker, 6000)
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
        if is_copy:
            # M195 R3 [GUID-FFD25CD3 + SLD-USE-MOVE-COPY]: Rotate is a
            # Move Type of the SAME Move/Copy dialog, so Create Copy's
            # law rides it verbatim - the twin turns into a NEW browser
            # body, not linked, and the original never moves. (M55's
            # in-body union stays ONLY for files that already carry a
            # copy RotateFeature - the kernel did not change.)
            b = self.doc.copy_body_turned(c, e, deg)
            self.recompute()
            self.viewport.refresh()
            self.status.showMessage(
                f"Body copied — {b['name']} stands turned "
                f"{deg:+.1f}\u00b0 about {'XYZ'[axis_i]}", 5000)
            return
        self.doc.add(RotateFeature(
            name=f"Rotate {'xyz'[axis_i]} {deg:+.1f}\u00b0",
            center=tuple(float(v) for v in c),
            axis=tuple(float(v) for v in e), angle_deg=deg))
        self.recompute()
        self.viewport.refresh()
        self.status.showMessage(
            f"Body rotated {deg:+.1f}\u00b0 about "
            f"{'XYZ'[axis_i]} through its centre", 5000)

    # M201 R17: each tool's placement fact, in one house sentence.
    _PRIM_PLACEMENT = {
        "Box": "placement is the box corner",
        "Cylinder": "placement is the base centre",
        "Sphere": "placement is the centre",
        "Torus": "placement is the ring centre",
        "Cone": "placement is the base centre",   # HOUSE SHAPE (see below)
    }

    def action_box(self):
        """The pages' Box tool [SLD-BOX-SOLID, verbatim]: "On the
        toolbar, click Solid > Create > Box" ... "The Box dialog
        displays." - rows "Length" and "Width" ("specify exact Length
        and Width values") and "Height" ("the Length, Width, and
        Height manipulator handles")."""
        self.action_primitive("Box")

    def action_cylinder(self):
        """The pages' Cylinder tool [SLD-CYLINDER-SOLID, verbatim]:
        "specify an exact Diameter value" ... "Drag the Diameter and
        Height manipulator handles" - the family's size voice is
        DIAMETER (see action_primitive)."""
        self.action_primitive("Cylinder")

    def action_sphere(self):
        """The pages' Sphere tool [SLD-SPHERE-SOLID, verbatim]: "Drag
        the Diameter manipulator handle ... or specify an exact
        value" - Diameter is the ONE size row the page prints."""
        self.action_primitive("Sphere")

    def action_torus(self):
        """The pages' Torus tool [SLD-TORUS-SOLID, verbatim]: "Drag
        the Inner Diameter and Torus Diameter manipulator handles" -
        the door takes the page's TWO handle words. Position {Inside
        | On Center | Outside} is NOT offered: it disambiguates a
        single pick-time diameter this two-diameter door never asks,
        and the page's own Position glosses are self-referential
        (vendor DEFECT, flagged) - nothing is composed from them."""
        self.action_primitive("Torus")

    def action_cone(self):
        """The Cone tool - DECLARED HOUSE SHAPE WHOLESALE: the family
        sweep 404s SLD-CONE-SOLID and the Create panel prints exactly
        {Box | Cylinder | Sphere | Torus | Coil | Pipe}, so NO page
        prints a Cone and every word of this dialog (including its
        diameter rows, borrowed from the family voice) is OURS; the
        kernel has always baked the cone geometry."""
        self.action_primitive("Cone")

    def action_primitive(self, shape: str = "Box"):
        """M65 grew the primitive family; M201 R17 [SLD-*-SOLID,
        verbatim] split the merged "Primitive" dialog into the PAGES'
        separate tools - each dialog is TITLED the tool's word (the
        pages print "The Box dialog displays.", "The Cylinder dialog
        displays.", ...) and shows ONLY its own rows in the pages'
        size voice. That voice is DIAMETER: "radius" counts ZERO hits
        on every task page (the lone Radius lives on the Coil
        reference page, contradicting its own task page - vendor
        DEFECT, flagged, never cloned). LAW AT THE MOUTH: a typed
        Diameter HALVES into the record's radius - the record voice
        (files, lever, rail) moves not an inch; the Torus pair lands
        major=(Torus+Inner)/4, minor=(Torus-Inner)/4 and an Inner not
        smaller than the Torus REFUSES BEFORE the capture (no record,
        no undo step). Cone is the HOUSE shape (its action's docstring
        says so wholesale; the sweep never found a Cone page). The
        pages print ZERO printed defaults (grep "default" across the
        family: 0 hits) and NO placement rows - every rest and the
        "place X/Y/Z" rows are OURS, stamped. Operation rides the
        page's printed order - "Join ... Cut ... Intersect ..." (the
        first three of five; New Body is the separate house tool, New
        Component is "(Hybrid Design type only)" and the kernel does
        not bake it, so the door does not promise it)."""
        if self.doc is None:
            return
        if shape not in self._PRIM_PLACEMENT:
            raise ValueError(f"no primitive tool named {shape!r}")
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        f = units.PER_MM[u]
        lab = units.LABEL[u]

        def num(key, label, mm, dec=2):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=dec, min=0.01)

        def freenum(key, label, mm):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=2)
        size_rows = {
            "Box": (num("length", "Length", 40.0),
                    num("width", "Width", 30.0),
                    num("height", "Height", 15.0)),
            "Cylinder": (num("diameter", "Diameter", 20.0, 3),
                         num("height", "Height", 30.0)),
            "Sphere": (num("diameter", "Diameter", 20.0, 3),),
            "Torus": (num("torus_d", "Torus Diameter", 50.0, 3),
                      num("inner_d", "Inner Diameter", 30.0, 3)),
            "Cone": (num("bottom_d", "Bottom Diameter", 24.0, 3),
                     num("top_d", "Top Diameter", 8.0, 3),
                     num("height", "Height", 30.0)),
        }[shape]
        v = cmddialog.ask(self, shape, [
            *size_rows,
            dict(key="op", label="Operation", kind="combo",
                 choices=["Join", "Cut", "Intersect"], default="Join",
                 group="Boolean"),
            freenum("x", "place X", 0.0),
            freenum("y", "place Y", 0.0),
            freenum("z", "place Z", 0.0),
        ], remember_key=f"primitive_{shape.lower()}")
        if v is None:
            return
        half = 0.5 * f
        kind = shape.lower()
        if shape == "Box":
            dims = {k: float(v[g]) * f
                    for k, g in (("dx", "length"), ("dy", "width"),
                                 ("dz", "height"))}
        elif shape == "Cylinder":
            dims = {"radius": float(v["diameter"]) * half,
                    "height": float(v["height"]) * f}
        elif shape == "Sphere":
            dims = {"radius": float(v["diameter"]) * half}
        elif shape == "Torus":
            td, ind = float(v["torus_d"]) * f, float(v["inner_d"]) * f
            if ind >= td:
                self.status.showMessage(
                    "Torus refused: the Inner Diameter must be smaller "
                    "than the Torus Diameter", 6000)
                return
            dims = {"major": (td + ind) / 4.0, "minor": (td - ind) / 4.0}
        else:                                    # Cone - HOUSE shape
            dims = {"radius_bottom": float(v["bottom_d"]) * half,
                    "radius_top": float(v["top_d"]) * half,
                    "height": float(v["height"]) * f}
        n = sum(1 for g in self.doc.features
                if isinstance(g, PrimitiveFeature) and g.kind == kind) + 1
        self._capture()
        self.doc.add(PrimitiveFeature(
            name=f"{shape} {n}", kind=kind, dims=dims,
            op={"Join": "union", "Cut": "subtract",
                "Intersect": "intersect"}[str(v["op"])],
            placement=tuple(float(v[k]) * f for k in ("x", "y", "z"))))
        self.recompute()
        self.status.showMessage(
            f"Added {kind} — {self._PRIM_PLACEMENT[shape]}", 5000)

    _INTERLOCK_KINDS = {          # dialog labels -> core kinds (M121)
        "Boss — post joining two bodies": "boss",
        "Snap fit — hook + window (press fit)": "snapfit",
        "Rest — flat stepped shelf for a part": "rest",
        "Lip — rim bead riding in a channel": "lip",
    }

    def action_interlock(self):
        """Fusion's Plastic-extension family as ONE free command (M121):
        boss · snap fit · rest · lip.  Two dialogs mirror the family's
        shared grammar — the Side 1 / Side 2 / Flip / offset shape
        first, then the kind's analytic vocabulary.  The tools are
        dry-run validated BEFORE the undo snapshot, so a nonsense
        parameter leaves the timeline untouched."""
        if self.doc is None:
            return
        bodies = [b["name"] for b in self.doc.body_list()]
        if not bodies:
            return
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        f = units.PER_MM[u]
        lab = units.LABEL[u]

        def num(key, label, mm, dec=2, mn=0.0):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=dec, min=mn)
        v = cmddialog.ask(self, "Interlock", [
            dict(key="kind", label="Family member", kind="combo",
                 choices=list(self._INTERLOCK_KINDS), group="Kind"),
            dict(key="carry", label="Body below the interface",
                 kind="combo", choices=bodies, default=bodies[0],
                 group="Bodies"),
            dict(key="mate", label="Body above (unused for Rest)",
                 kind="combo", choices=bodies,
                 default=bodies[1] if len(bodies) > 1 else bodies[0],
                 group="Bodies"),
            dict(key="flip", label="Flip across the interface plane",
                 kind="check", default=False, group="Bodies"),
            num("x", "Interface point X", 0.0, mn=-1e6),
            num("y", "Interface point Y", 0.0, mn=-1e6),
            num("z", "Interface plane height", 0.0, mn=-1e6),
            num("clearance", "Clearance δ (print gap)", 0.2, dec=3),
        ])
        if v is None:
            return
        kind = self._INTERLOCK_KINDS[str(v["kind"])]
        geom = {
            "boss": [num("shaft_d", "Post diameter", 8.0),
                     num("height1", "Anchor below interface", 5.0),
                     num("height2", "Reach above interface", 7.0)],
            "snapfit": [num("length", "Hook length", 10.0),
                        num("width", "Hook width", 6.0),
                        num("height", "Hook height", 2.0),
                        num("lead", "Lead-in chamfer", 1.0),
                        num("depth", "Window depth", 2.2, dec=3)],
            "rest": [num("seat_d", "Seat diameter", 10.0),
                     num("hole_d", "Pilot hole diameter", 6.0),
                     num("depth", "Seat depth", 3.0),
                     num("reach", "Pilot reach", 12.0)],
            "lip": [num("outer_w", "Rim width X", 30.0),
                    num("outer_d", "Rim depth Y", 20.0),
                    num("thickness", "Wall thickness", 2.0),
                    num("height", "Lip height", 4.0),
                    num("depth", "Channel depth", 4.2, dec=3)],
        }[kind]
        g = cmddialog.ask(self, f"Interlock — {kind.title()}", geom)
        if g is None:
            return
        carry, mate = str(v["carry"]), str(v["mate"])
        if kind != "rest" and carry == mate:
            # M189 R2 [LAW-61(a)]: a pick error is INPUT - the cure
            # speaks where the eye is, not from a modal chair.
            self.status.showMessage(
                "Interlock refused: this member mates TWO bodies — "
                "pick different ones (Body ▸ New Body first)", 6000)
            return
        params = {fd["key"]: float(g[fd["key"]]) * f for fd in geom}
        from ..core import interlock
        try:                                # dry-run: refuse before undo
            interlock.tools(kind, clearance=float(v["clearance"]) * f,
                            **params)
        except ValueError as e:
            # M189 R2 [LAW-61(a)]: dry-run rejection, before the undo
            # capture even - tier (a) by the ladder's own logic.
            self.status.showMessage(f"Interlock refused: {e}", 6000)
            return
        self._capture()
        feats = self.doc.add_interlock(
            kind, carry, mate if kind != "rest" else None,
            x=float(v["x"]) * f, y=float(v["y"]) * f,
            z0=float(v["z"]) * f,
            clearance=float(v["clearance"]) * f,
            flip=bool(v["flip"]), **params)
        self.doc.dirty = True
        self.recompute()
        self.viewport.refresh()
        self.status.showMessage(
            f"{kind.title()} ×{len(feats)} at ({float(v['x']):g}, "
            f"{float(v['y']):g}) {lab} — mated pair, δ = "
            f"{float(v['clearance']):g} {lab}", 5000)

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
            # M189 R4 [LAW-61(a)]: empty text is INPUT before history.
            self.status.showMessage("Nothing to draw — type some text "
                                    "first (spaces alone won't do)", 5000)
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
        """Fusion's Combine, grown into the page's OWN door (M201
        R14 [SLD-REF-COMBINE, verbatim]): "Combine joins, cuts, or
        intersects the selected bodies." The page prints a SINGULAR
        Target Body - "the body being acted upon" - so the target
        is ONE combo, never a check-list; the Tool Bodies row is
        the licensed PLURAL ("the bodies that change the model")
        and rides the named-body check-list (R13's bridge). The
        Operation enum is the page's closed three words (Join | Cut
        | Intersect - no Separate, no Merge on the solid tool).
        "Keep Tools: Retains the tool bodies after the combine
        results." - ON is that sentence; the page is machine-
        grepped SILENT on what OFF does, so the drop is OURS and
        says so (never "consumed": that word is the vendor's
        silence). No tool bodies ticked, the door keeps its legacy
        M64 voice: a placed primitive tool (the map calls it a
        valid subset) with the same three Operations. "default"
        counts ZERO on both pages: keep-tools ON and the primitive
        rests are HOUSE FACTS, and every refusal stands BEFORE the
        capture (the window owns the only undo stack)."""
        if self.doc is None or self.doc.result is None:
            # M189 R3 [LAW-61(a)]: precondition -> tier (a) voice.
            self.status.showMessage("Nothing to combine into yet — "
                                    "extrude or import a solid first",
                                    5000)
            return
        lo = np.asarray(self.doc.result.bounding_box[0], float)
        hi = np.asarray(self.doc.result.bounding_box[1], float)
        c = (lo + hi) / 2.0
        u = self.doc.units if self.doc.units in units.LABEL else "mm"
        f = units.PER_MM[u]
        lab = units.LABEL[u]
        names = [b["name"] for b in self.doc.body_list()]

        def num(key, label, mm, dec=2):
            return dict(key=key, label=f"{label} ({lab})", kind="double",
                        default=round(mm / f, 6), decimals=dec)
        v = cmddialog.ask(self, "Combine", [
            dict(key="target", label="Target Body", kind="combo",
                 choices=names,
                 default=self.doc.active_body or names[0],
                 group="Bodies"),
            dict(key="tools", label="Tool Bodies", kind="checks",
                 choices=names, group="Bodies"),
            dict(key="op", label="Operation", kind="combo",
                 choices=["Join", "Cut", "Intersect"], default="Join",
                 group="Bodies"),
            dict(key="keep", label="Keep Tools", kind="check",
                 default=True, group="Bodies"),
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
            num("cx", "centre X", float(c[0])),
            num("cy", "centre Y", float(c[1])),
            num("cz", "centre Z", float(c[2])),
        ], remember_key="combine")
        if v is None:
            return
        opw = str(v["op"])
        if opw not in ("Join", "Cut", "Intersect"):
            self.status.showMessage(
                f"Combine refused: the operation is 'Join', 'Cut' "
                f"or 'Intersect', not {opw!r}", 6000)
            return
        op = {"Join": "union", "Cut": "subtract",
              "Intersect": "intersect"}[opw]
        target = str(v.get("target") or (self.doc.active_body
                                         or names[0]))
        tools = [str(t) for t in (v.get("tools") or [])]
        keep = bool(v.get("keep", True))
        if target not in names:
            self.status.showMessage(
                f"Combine refused: the Target Body is 'the body being "
                f"acted upon' and {target!r} is not a body", 6000)
            return
        for t in tools:
            if t == target:
                self.status.showMessage(
                    f"Combine refused: {t!r} is the body being acted "
                    "upon - it cannot also change the model", 6000)
                return
            if t not in names:
                self.status.showMessage(
                    f"Combine refused: tool body {t!r} is not a "
                    "body", 6000)
                return
        if tools:
            self._capture()
            feat = CombineFeature(name=f"Combine {target}", op=op,
                                  tool_bodies=tuple(tools),
                                  keep_tools=keep, body=target)
            self.doc.add(feat)
            self.recompute()
            ff = getattr(self.doc, "failed_feature", None)
            if ff is not None and ff[1] == feat.name:
                return                      # M118 badge + modal
            self.viewport.refresh(fit=True)
            sol = self.doc.body_solids().get(target)
            vol_mm = sol.volume if sol is not None else 0.0
            self.status.showMessage(
                f"Combined ({opw}) {target} with "
                + " + ".join(tools)
                + ("" if keep else " — the tools are not retained "
                                   "(ours: the page prints no fate)")
                + f" — {vol_mm:,.0f} mm³", 6000)
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
        self._capture()
        self.doc.add(CombineFeature(
            name=f"Combine {tool}", tool=tool, dims=dims, op=op,
            body=target,
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
            # M189 R4 [LAW-61(a)]: the recipe guidance steps down with
            # the same cure words; the R2 kernel refusal rides beside it.
            self.status.showMessage("Sweep runs from a sketch: draw ONE "
                                    "circle (the profile) plus a "
                                    "connected chain of lines and/or arcs "
                                    "(the path)", 6000)
            return
        from ..core.sweep import path_chain
        try:
            pts, closed = path_chain(m)
        except ValueError as e:
            # M189 R2 [LAW-61(a)]: an unbuildable path is INPUT.
            self.status.showMessage(f"Sweep refused: {e}", 6000)
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

    def action_thicken(self):
        """Fusion Patch/Thicken, mesh-honest (M99): the sketch's OPEN
        chains wall into a solid of `thickness` x `depth` — ribs,
        stiffeners, patch plates. Closed profiles are said no, kindly."""
        if self.doc is None:
            return
        m = self.sketch.model
        if m is None:
            # M189 R4 [LAW-61(a)]: recipe guidance - tier (a) voice.
            self.status.showMessage("Thicken runs from a sketch: draw "
                                    "open lines and/or arcs — the path to "
                                    "wall in. Closed profiles are "
                                    "Extrude's job", 6000)
            return
        from ..core.thicken import open_chains
        try:
            chains = open_chains(m)
        except ValueError as e:
            # M189 R2 [LAW-61(a)]: no open profile to thicken is INPUT.
            self.status.showMessage(f"Thicken refused: {e}", 6000)
            return
        from . import cmddialog
        v = cmddialog.ask(self, "Thicken", [
            dict(key="thickness", kind="double",
                 label="Wall thickness (mm)",
                 default=2.0, min=0.01, max=1e4, decimals=3),
            dict(key="depth", kind="double", label="Depth (mm)",
                 default=5.0, min=0.01, max=1e5, decimals=3)])
        if v is None:
            return
        t, dp = float(v["thickness"]), float(v["depth"])
        payload = model_to_dict(m)
        owned = [f for f in self.doc.features
                 if isinstance(f, ThickenFeature) and f.sid == m.sid]
        self._capture()
        paths = [[[float(x), float(y)] for x, y in c] for c in chains]
        if owned:                                   # re-thicken in place
            f = owned[0]
            for extra in owned[1:]:
                self.doc.features.remove(extra)
            f.thickness, f.depth, f.paths = t, dp, paths
            f.name = f"Wall {t:g}"
            f.sketch = dict(payload)
        else:
            self.doc.add(ThickenFeature(
                name=f"Wall {t:g}", thickness=t, depth=dp, paths=paths,
                plane=m.plane, placement=tuple(map(float, m.origin)),
                axes=m.axes, sketch=dict(payload), sid=m.sid))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Thickened {len(chains)} open chain(s) to a {t:g} mm wall, "
            f"{dp:g} mm deep", 5000)

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

    def _sync_thickens(self, sid, payload):
        """Sketch re-edit committed: re-extract the open chains for
        walls born from this sketch; drop them if nothing open is left
        (M99 — the wall follows the path it was thickened from)."""
        walls = [f for f in self.doc.features
                 if isinstance(f, ThickenFeature) and f.sid == sid]
        if not walls:
            return False
        from ..core.thicken import open_chains
        m = model_from_dict(payload)
        try:
            chains = open_chains(m)
        except ValueError:
            for f in walls:                        # nothing open anymore
                self.doc.features.remove(f)
            return True
        keep = walls[0]
        for extra in walls[1:]:
            self.doc.features.remove(extra)
        keep.paths = [[[float(x), float(y)] for x, y in c] for c in chains]
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
            # M189 R4 [LAW-61(a)]: a pick error is INPUT - tier (a).
            self.status.showMessage("Loft refused: blend two or more "
                                    "DIFFERENT sketches", 5000)
            return
        by_sid = {s: sec for s, _label, sec in cands}
        secs = [dict(by_sid[s]) for s in sids]
        names = [next(l for s, l, _ in cands if s == sid) for sid in sids]
        try:                            # validate before touching history
            LoftFeature(name="loft", sections=secs, closed=closed).build()
        except ValueError as e:
            # M189 R2 [LAW-61(a)]: validate before touching history -
            # the refusal (kernel words + the offset cure) drops to a.
            self.status.showMessage(
                f"Loft refused: {e} — the two profiles must sit on "
                "different planes (sketch-on-face gives the second "
                "one an offset)", 6000)
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
        # M191 R5: a re-edit may DECLARE or MOVE the centerline - the
        # revolve re-reads the axis from the fresh payload (the SAME
        # mouth the first commit spoke), and a crowd of declarations
        # refuses the commit exactly as the fresh door does.
        _ax_err = None
        if any(isinstance(f, RevolveFeature) for f in group):
            _ax_upd, _ax_err = self._axis_from_payload(payload)
        if _ax_err is not None:
            self.status.showMessage("Update refused: " + _ax_err, 6000)
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
                if isinstance(f, RevolveFeature):
                    f.axis = _ax_upd
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
                    # M191 R5: a region born in THIS re-edit reads the
                    # axis from the same fresh payload — the declaration
                    # the maker just made applies to every half of it.
                    extra["axis"] = _ax_upd
                    self.doc.add(RevolveFeature(angle=src.angle, **extra))
                else:
                    if getattr(src, "handle", None):
                        extra["handle"] = dict(src.handle)  # M142:
                        #   added regions inherit the attachment
                    # M201 R3: and the DIRECTION VOICE - the door
                    # asked it ONCE for this sketch, so a region born
                    # into the group speaks the same answer (a
                    # two-sided sketch must not grow a one-sided
                    # sibling). Word and paper travel together, as
                    # they were born agreeing.
                    # M201 R4: and so does the START - the door asked
                    # the offset ONCE too; a sibling must not start at
                    # the plane when its family starts off it.
                    # M201 R5: and the OPERATION - the door asked it
                    # ONCE (off-face; on a FACE sketch the probe
                    # decided per profile and the family already
                    # speaks what it measured - a grown sibling
                    # inherits THAT same answer rather than silently
                    # switching to union mid-family).
                    extra.update(direction=src.direction,
                                 symmetric=src.symmetric,
                                 measurement=src.measurement,
                                 height2=src.height2,
                                 offset=src.offset,
                                 op=src.op)
                    self.doc.add(ExtrudeFeature(height=src.height,
                                                **extra))
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
        # M185 R2 [LAW-45]: the PICKBOX meets the hand - the selection
        # target radius lives right beside the grid toggle. The spin is
        # a WINDOW onto the canvas mouth: it never writes QSettings -
        # set_pick_radius (R1) is the ONE door that persists.
        self._pick_spin = QSpinBox()
        self._pick_spin.setRange(0, 20)
        self._pick_spin.setPrefix("Target ")
        self._pick_spin.setSuffix(" px")
        # LAYOUT PARITY LAW (learned in CI-red): the sketch bar's
        # natural size sets the offscreen window, and the window sets
        # the canvas - the drag fixtures round w2s() to screen pixels,
        # so BOTH canvas halves must stay integers. The spin's stock
        # sizeHint entered the bar with an ODD footprint (99px) and
        # slid every x by 0.125 world. A handle must sit in its row at
        # its row's PARITY: even width, height no taller than siblings.
        self._pick_spin.setFixedHeight(self._snap_btn.sizeHint().height())
        self._pick_spin.setFixedWidth(106)      # "Target 20 px" + arrows
        self._pick_spin.setToolTip(
            "Selection target radius in pixels (the PICKBOX). Clicks\n"
            "and the hover preview share this ONE number; 0 turns the\n"
            "live selection previews off - targets still click-select.")
        bl.addWidget(self._pick_spin)
        # Fusion's constraint voice on the toolbar (M73): fully / dof
        self._sketch_state = ClickableLabel("")    # M164 R2: the chip acts
        self._sketch_state.setStyleSheet(
            f"color:{DARK['accent_soft']}; padding:0 8px;")
        bl.addWidget(self._sketch_state)
        self._sketch_state.clicked.connect(self._on_sketch_state_click)
        bl.addStretch(1)
        back = QPushButton("← Back")
        back.setProperty("tb", True)
        back.setToolTip("Return to the 3D model without extruding")
        back.clicked.connect(self._leave_sketch_page)   # M191 R2: the
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
        thk = QPushButton("Thicken…")           # M99: Patch/Thicken twin
        thk.setProperty("tb", True)
        thk.setToolTip("Wall this sketch's open chains into solid stock — "
                       "ribs, stiffeners, patch plates")
        thk.clicked.connect(self.action_thicken)
        bl.addWidget(thk)
        self.sketch = SketchCanvas()
        self.sketch.profiles_ready.connect(self._on_profiles)
        self.sketch.state_changed.connect(self._on_sketch_state)
        self.sketch.dim_edited.connect(           # M165 R3 record site 4:
            lambda _c: self._note_cmd(            #  a chip commit; payload
                "sketch:chip", "sketch", "chip", None))  #  stays None - the
                #  ring holds NO stale object, the doors re-resolve via the
                #  live canvas._last_dim (plan risk 3 self-heal)
        self._wire_sketch_params(self.sketch)      # M89 fx sees the sheet
        self._snap_btn.setChecked(self.sketch._snap_grid)
        self._pick_spin.setValue(self.sketch.pick_radius)   # M185 R2:
        self._pick_spin.valueChanged.connect(               #  two doors,
            self.sketch.set_pick_radius)                    #  one mouth -
        self.sketch.pick_radius_changed.connect(            #  it converges
            self._pick_spin.setValue)                       #  by design
        lay.addWidget(bar)
        # M192 R1 [GUID-4183A4B7]: the Sketch Palette is born - a fixed
        # side column beside the canvas (the vendor's panel is docked
        # furniture too). The canvas keeps the whole stretch; the
        # palette's 196 px never steal grow-room from the drawing
        # (M185's integer-halves law: the SPLITTER pages keep their
        # halves - this is a panel, not a split view).
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._sketch_palette = SketchPalette(self.sketch)
        row.addWidget(self.sketch, 1)
        row.addWidget(self._sketch_palette)
        lay.addLayout(row, 1)
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
        # M164 R3: the finder sentence rides ONLY where the solve blames
        # something - clean states keep M73/M87's words byte-exact (the
        # chain above was NOT touched). String-cheap law holds: booleans
        # off the cached result only, no scan - the scan runs at CLICK.
        fixable = res is not None and not empty and bool(
            getattr(res, "conflicting", [])
            or getattr(res, "redundant", []))
        if fixable:
            self._sketch_state.setText(self._sketch_state.text()
                                       + " \u2304 remove one to fix")
        free = res is not None and not empty and not fixable \
            and res.dof > 0
        self._sketch_state.setEnabled(fixable or free)
        self._sketch_state.setCursor(Qt.PointingHandCursor
                                     if fixable or free else Qt.ArrowCursor)
        self._sketch_state.setToolTip(
            "Click to choose one to remove" if fixable else
            "Click to select every free point" if free else "")

    def _on_sketch_state_click(self):
        """M164 R3: the chip FIXES before it selects.  A blamed solve
        opens the live sketch_fix panel (anti-modal; the drop-one scan
        runs THERE, at click time - never in this handler).  When the
        finder declines (nothing singly removable) the click falls back
        to rung 2's selection voice: never a dead click."""
        res = getattr(self.sketch, "_last_result", None)
        if res is None:
            return
        if getattr(res, "conflicting", []) or getattr(res, "redundant", []):
            if self.sketch.open_finder_panel(self) is not None:
                return
        if getattr(res, "conflicting", []):
            self.sketch.select_blamed()
        elif res.dof > 0:
            self.sketch.select_underconstrained()

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
        # M162: set_document reset the folder eye — the LAYER follows it
        # here, or a second document would open behind the first one's
        # hidden-Bodies folder (the renderer outlives the doc).
        self.viewport.set_solid_visible(self.rail.tree.folder_vis)
        self.timeline.set_document(self.doc)
        self.viewport.set_document(self.doc)
        self.viewport.refresh(fit=False)
        if self._drawing_page is not None:            # M96: sheets too
            idx = self.drawing.sheet_idx              # keep the same sheet
            self.drawing.set_document(self.doc,
                                      idx=None if idx < 0 else idx)
            self._sync_bom_btn()                      # M110: paper state
            self._sync_hole_btn()                     # M129: notes state
        self._update_status()
        self._apply_appearance()
        self._apply_units()

    def _mark_dirty(self):
        self._unsaved = True             # M155: "Set Current View as
        #   Home" is a DOCUMENT edit — the title dot must say so

    def new_document(self, doc: Document | None = None):
        self.doc = doc or Document("Untitled")
        self.file_path = None
        self._saved_mtime = None          # M111: on-disk conflict guard
        self._editing_sid = None
        self._edit_park = None            # M191 R2: a new doc un-parks
        self._edit_park_on = False
        self._unsaved = False
        self._undo.clear()
        self._redo.clear()
        self.rail.tree.set_document(self.doc)
        # M162: set_document reset the folder eye — the LAYER follows it
        # here, or a second document would open behind the first one's
        # hidden-Bodies folder (the renderer outlives the doc).
        self.viewport.set_solid_visible(self.rail.tree.folder_vis)
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
        """The NEWEST autosave for this document (M111 rolling set).
        With none on disk, hands back a well-formed but absent path,
        so callers can keep asking ``.exists()`` (M67's contract)."""
        stem = self.file_path.stem if self.file_path else "untitled"
        files = sorted(self._recovery_dir().glob(f"{stem}.*.autosave.tracer"))
        return files[-1] if files else (
            self._recovery_dir() / f"{stem}.none.autosave.tracer")

    def _autosave(self):
        """Every successful recompute mirrors the document to disk, so a
        crash loses at most the last unsaved edit.  M111: the mirrors are
        timestamped, keep the last five, and reach disk atomically — the
        safety net cannot itself be caught half-written."""
        if self.doc is None:
            return
        try:
            from datetime import datetime
            stem = self.file_path.stem if self.file_path else "untitled"
            t = time.time()
            stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(t)) \
                + f"-{int(t * 1000) % 1000:03d}"
            f = self._recovery_dir() / f"{stem}.{stamp}.autosave.tracer"
            fio.write_json_atomic(dict(
                path=str(self.file_path) if self.file_path else None,
                saved=datetime.now().isoformat(timespec="seconds"),
                doc=self.doc.to_dict()), f)
            for old in sorted(self._recovery_dir()
                              .glob(f"{stem}.*.autosave.tracer"))[:-5]:
                old.unlink(missing_ok=True)
        except Exception:                 # the safety net never bites
            pass

    def _clear_autosave(self):
        """Save/open/new: drop this document's autosaves — and the
        pre-save ``untitled.*`` mirrors of it, which the old single-file
        scheme missed entirely, haunting the next launch with a recovery
        prompt for work that was already saved."""
        try:
            stem = self.file_path.stem if self.file_path else "untitled"
            for p in self._recovery_dir().glob("*.autosave.tracer"):
                if p.name.startswith(stem + ".") or (
                        self.file_path is not None
                        and p.name.startswith("untitled.")):
                    p.unlink(missing_ok=True)
        except Exception:
            pass

    # ---- versions (M111) ---------------------------------------------------
    def _record_version(self):
        """A Save IS a version (the cloud semantic, adopted offline): an
        auto point beside the file, rolling at 25 — undo is RAM, this is
        disk.  Version trouble must never make a save look doubtful, so
        it passes quietly; the written document is already safe."""
        if self.doc is None or self.file_path is None:
            return
        try:
            from ..core import versions
            versions.append(self.file_path, self.doc.to_dict())
        except Exception:
            pass

    def _changed_on_disk_prompt(self) -> str:
        """'go', 'cancel' or 'new': if the file moved under our hands
        since the last save (a second copy of Tracer, a sync tool, a
        git checkout), a plain save would silently eat those changes —
        ask instead.  Half a second of tolerance; never silent."""
        if self._saved_mtime is None or self.file_path is None \
                or not self.file_path.exists():
            return "go"
        try:
            mt = self.file_path.stat().st_mtime
        except OSError:
            return "go"
        if mt <= self._saved_mtime + 0.5:
            return "go"
        box = QMessageBox(QMessageBox.Warning, "File changed on disk",
                          f"{self.file_path.name} was modified outside "
                          "Tracer since your last save.\nOverwrite it "
                          "anyway, or keep both?",
                          QMessageBox.NoButton, self)
        over = box.addButton("Overwrite", QMessageBox.AcceptRole)
        keep = box.addButton("Save to a new file…", QMessageBox.ActionRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec_()
        hit = box.clickedButton()
        if hit is over:
            return "go"
        if hit is keep:
            return "new"
        return "cancel"

    def action_revert_saved(self):
        """The File-menu verb cloud products never needed and local
        first does: throw the in-memory changes away and re-read the
        file (the dialog-free inverse of dirty)."""
        if self.doc is None or self.file_path is None \
                or not self.file_path.exists():
            self.status.showMessage("Nothing saved to revert to", 4000)
            return
        if QMessageBox.question(
                self, "Revert to Saved",
                "Discard the changes in memory and reopen "
                f"{self.file_path.name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            return
        self._open_path(self.file_path)
        self.status.showMessage("Reverted to the saved file", 5000)

    def action_versions(self):
        if self.doc is None or self.file_path is None:
            self.status.showMessage("Save the document first — versions "
                                    "live beside the file", 5000)
            return
        from .versionsdlg import VersionsDialog
        VersionsDialog(self.file_path, parent=self,
                       on_restore=self._load_version).exec_()

    def _load_version(self, data: dict, detach: bool = False) -> bool:
        """Restore is NON-destructive: the snapshot becomes unsaved
        working state — the file and the version chain wait, untouched,
        for the user's next Save.  ``detach`` (Open as Copy) drops the
        file link so the next Save necessarily starts a new document."""
        path = None if detach else self.file_path
        try:
            doc = Document.from_dict(data)
            doc.recompute()
        except Exception as e:
            QMessageBox.warning(self, "Version unreadable", str(e))
            return False
        self.new_document(doc)
        self.file_path = path
        if path is not None:
            self.doc.title = path.stem
            self._saved_mtime = float(path.stat().st_mtime)
        self._unsaved = True
        self._update_title()
        self.status.showMessage("Version loaded — review it; saving "
                                "makes it the newest", 6000)
        return True

    def maybe_recover(self) -> bool:
        """Startup offer: an autosave from a previous crash can be
        restored, or thrown away. Called by tracer.app.main(), not by
        the constructor, so headless tests never see the prompt.
        M111's gate, earned from FreeCAD's proven recovery: an autosave
        older than the file it mirrors is not a rescue — it is a
        ghost, and ghosts are eaten silently."""
        cand: Path | None = None
        payload: dict | None = None
        for p in sorted(self._recovery_dir().glob("*.autosave.tracer"),
                        key=lambda q: q.stat().st_mtime, reverse=True):
            try:
                data = fio.load_json(p)
            except Exception:
                p.unlink(missing_ok=True)
                continue
            sp = data.get("path")
            if sp:
                f = Path(sp)
                try:
                    if f.exists() and p.stat().st_mtime <= f.stat().st_mtime:
                        p.unlink(missing_ok=True)      # file already has it
                        continue
                except OSError:
                    pass
            cand, payload = p, data
            break
        if cand is None or payload is None:
            return False
        p = cand
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
        else:
            ans = self._changed_on_disk_prompt()        # M111, never silent
            if ans == "cancel":
                return
            if ans == "new":
                return self.action_save(as_new=True)
        try:
            fio.save_document(self.doc, self.file_path)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return                                      # dirty flag stays: honest
        self.status.showMessage(f"Saved {self.file_path}", 5000)
        self.doc.dirty = False
        self._unsaved = False
        self._saved_mtime = float(self.file_path.stat().st_mtime)
        self._update_title()
        self._note_recent(self.file_path)
        self._clear_autosave()
        self._record_version()                          # M111: save = version

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
            return self._offer_autosave_for(path)      # M111: broken file
        self.new_document(doc)                         # is not the end of
        self.file_path = Path(path)
        self._saved_mtime = float(self.file_path.stat().st_mtime)
        self._note_recent(path)
        self._clear_autosave()
        self._update_title()
        self.status.showMessage(f"Opened {Path(path).name}", 5000)
        return True

    def _offer_autosave_for(self, path) -> bool:
        """A corrupted document should still not be the end of the work:
        if an autosave of it exists, offer to open THAT (the recovery
        pattern FreeCAD ships, mirrored).  Deliberately not consumed —
        the autosave survives until a real Save clears it."""
        stem = Path(path).stem
        files = sorted(self._recovery_dir().glob(f"{stem}.*.autosave.tracer"),
                       key=lambda q: q.stat().st_mtime, reverse=True)
        if not files:
            return False
        p = files[0]
        try:
            payload = fio.load_json(p)
            doc = Document.from_dict(payload["doc"])
            doc.recompute()
        except Exception:
            return False
        if QMessageBox.question(
                self, "Open autosave instead?",
                f"{Path(path).name} could not be read. Open its autosave "
                f"from {payload.get('saved', 'earlier')}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes) \
                != QMessageBox.StandardButton.Yes:
            return False
        self.new_document(doc)
        self.file_path = Path(path)
        self._unsaved = True
        self._update_title()
        self.status.showMessage("Opened autosave — save it somewhere "
                                "safe right away", 8000)
        return True

    def action_open(self):
        start = str(self.file_path.parent if self.file_path else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open document", start,
            "Tracer Studio document (*.tracer);;Legacy Forma document (*.forma)")
        if not path:
            return
        self._open_path(path)

    def recompute(self):
        if self.continue_on_error:
            # M188 R4 [LAW-65]: "SOLIDWORKS can either continue
            # rebuilding (ignoring the error) or stop so you can
            # repair." Stop-and-repair is R1-R3's law and the DEFAULT;
            # the gear's toggle chooses the other half.
            self._recompute_continue()
            return
        was_bad = getattr(self.doc, "failed_feature", None) is not None
        try:
            self.doc.recompute()
        except Exception as e:  # kernel error must not kill the app
            # M118: stamp the guilty feature (red badge on its chip),
            # say it in the log WITH its name, then the modal — Fusion
            # order, deep-linked. Views must follow the doc even when
            # the build failed — an opened-broken file still badges.
            where = self.doc.record_failure(str(e))
            logservice.error(str(e), source="kernel",
                             feature=where[1] if where else None,
                             pos=where[0] if where else None)
            if self.timeline.bar.doc is not self.doc:
                self.timeline.set_document(self.doc)
            self.timeline.bar.update()
            if where is not None and self.doc.rollback_to != where[0]:
                # M188 R1 [LAW-64 documented]: "when repairing a model
                # with errors, the rollback bar SHIFTS TO THE FEATURE
                # WITH THE FIRST ERROR." The marker lands right BEFORE
                # the fault and the rebuild re-runs as the repair pass:
                # what the maker sees is now the last honest state, the
                # fault waiting past the marker in its red badge (a
                # skip never heals a scar). View state - never saved.
                self.doc.rollback_to = where[0]
                self.recompute()              # the fault is skipped now
                self.status.showMessage(
                    f"Rollback shifted to {where[1]} — the marker waits "
                    "before it; roll forward to test the fix", 6000)
            QMessageBox.warning(self, "Recompute failed", str(e))
            return
        self._after_clean_pass(was_bad)

    def _after_clean_pass(self, was_bad):
        """M188 R4 extraction (behavior-preserving): the refresh tail
        a SUCCESSFUL pass runs — views follow the doc, badges follow
        the scars, recovery is news only when every scar healed. The
        continue driver shares this exact tail: same honesty, no
        second copy to drift."""
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
        # rung D (M152): the states that used to be SILENT — a frozen
        # face handle, a mute letter, a stale host — reach the maker:
        # every line through the log's warn channel, the first also on
        # the status line. LAST word on purpose: _on_face_selection
        # rewrites the status with the body stats; a warning outlasts
        # a stat line. Never a modal: the model lives with these.
        aw = getattr(self.doc, "attachment_warnings", [])
        for line in aw:
            logservice.warn(line, source="kernel")
        if aw:
            self.status.showMessage(aw[0], 6000)
        if was_bad:                     # M118: recovery is news too -
            # M188 R1: but ONLY when every scar actually healed. A pass
            # that SKIPPED the fault under the marker must not shout
            # "clean again" over a badge still wearing red.
            if getattr(self.doc, "failed_feature", None) is None:
                logservice.info("recompute clean again", source="kernel")
            self.timeline.bar.update()  # badges follow the pass either way

    def _recompute_continue(self):
        """M188 R4 [LAW-65] "Continue (Ignore Error)": the rebuild
        driver RETRIES PAST EACH CAUGHT FAULT — every fault stamps its
        scar (via record_failure, whose wipes now also spare the
        skipped: a skip is not a heal, and a catch is not either),
        takes its slot out of the band, and the pass rebuilds what it
        can. Outcome: best-effort body, EVERY fault scarred, errors
        still a QUEUE (the pointer aims at the FIRST scar, not the
        last catch). No modal ambush — LAW-61(b)'s tier speaks: a
        non-modal COUNT in the log and on the status line. The bar is
        NOT parked: this pass ran everything it could."""
        was_bad = getattr(self.doc, "failed_feature", None) is not None
        self.doc._skip = set()
        while True:
            try:
                self.doc.recompute()
                break
            except Exception as e:
                where = self.doc.record_failure(str(e))
                logservice.error(str(e), source="kernel",
                                 feature=where[1] if where else None,
                                 pos=where[0] if where else None)
                if where is None or where[0] in self.doc._skip:
                    break               # pathological: same catch twice
                self.doc._skip.add(where[0])
        n = len(self.doc._skip)
        self.doc._skip = set()
        self.doc.failed_feature = next(
            ((i, f.name) for i, f in enumerate(self.doc.features)
             if getattr(f, "error", None)), None)
        self._after_clean_pass(was_bad)
        if n:
            logservice.warn(
                f"rebuild continued past {n} failed feature"
                + ("" if n == 1 else "s"), source="kernel")
            self.status.showMessage(
                f"Rebuild continued past {n} failed feature"
                + ("" if n == 1 else "s")
                + " — the gear asks What's Wrong?", 6000)

    def _toggle_message_log(self):
        self._log_menu.toggle()       # menu check IS the truth

    def _update_log_chip(self):
        err, warn = logservice.counts()
        self._log_chip.setText(f"\u26d4 {err}  \u26a0 {warn}")
        self._log_chip.setStyleSheet(
            "border: none; color: " + (
                DARK["danger"] if err else
                DARK["warn"] if warn else DARK["fg_faint"]))

    def _reveal_fault_list(self):
        """M190 R4 [LAW-63]: "Click a part name to reveal a list of
        errors and warnings. Clicking any entity in that list ADVANCES
        YOU DIRECTLY to that feature in the tree." The rollup dot is
        that part-name click: it reveals the Message Log AND lands on
        the queue head - list, door and walk in one gesture. Emits only
        while a fault is home (the tree's own gate)."""
        if not self._log_menu.isChecked():
            self._log_menu.toggle()
        ff = self.doc.failed_feature if self.doc is not None else None
        if ff is not None:
            self._goto_logged_feature(ff[0])
        else:
            self.status.showMessage(
                "Message Log open — the amber warnings are listed "
                "there", 4000)

    def _goto_logged_feature(self, pos: int):
        """M118 BEAT: the log row Fusion could never click."""
        if self.doc is None or not 0 <= pos < len(self.doc.features):
            return
        f = self.doc.features[pos]
        # M190 R3 [LAW-63]: THE LIST is the log, and the class law ends
        # "...ADVANCES YOU DIRECTLY TO THAT FEATURE IN THE TREE" - the
        # chip select (M118) was half the door; the row lands too.
        self.rail.tree.reveal_feature(f)
        self.timeline.bar.select_feature(f)
        msg = f"{f.name}"
        if getattr(f, "error", None):
            msg += f" \u2014 {f.error}"
        self.status.showMessage(msg, 6000)

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

    # ---- M113: command search + the model-context key layer -------------------
    def _make_command_search(self):
        self._palette = CommandPalette(self)
        self._palette.picked.connect(lambda: self.viewport.setFocus())
        # Fusion's two voices for the toolbox — S anywhere, / as command
        # line.  Text fields claim these first (Qt shortcut override),
        # matching Fusion's "keys sleep while you type" rule.
        for key in ("S", "/"):
            self.addAction(QAction("Command search", self, shortcut=key,
                                   triggered=self.open_command_search))

    def open_command_search(self):
        self._palette.set_commands(collect_commands(self))
        vp = self.viewport
        self._palette.open_near(QRect(vp.mapToGlobal(QPoint(0, 0)),
                                      vp.size()),
                                QCursor.pos())

    def keyPressEvent(self, ev):
        if self._dispatch_key(ev.key(), ev.modifiers()):
            return
        super().keyPressEvent(ev)

    @staticmethod
    def _key_str(key: int, mods) -> str:
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.AltModifier:
            parts.append("Alt")
        if mods & Qt.ShiftModifier:
            parts.append("Shift")
        base = QKeySequence(key).toString()
        return "+".join([*parts, base]) if parts else base

    def _dispatch_key(self, key: int, mods) -> bool:
        """Model-layer single keys — the one table (commands.MODEL_KEYS).
        The sketch widget claims its own letters before we ever see
        them; what bubbles up here is the model's to answer."""
        if mods & Qt.MetaModifier or self._palette.isVisible() \
                or getattr(self.sketch, "_dim_edit", None) is not None:
            return False                      # M165: an inline chip edit
                                              #   swallows the model layer
        hit = MODEL_KEYS.get(self._key_str(key, mods))
        return self._run_command(hit[1]) if hit else False

    def _run_command(self, target: str) -> bool:
        kind, sep, arg = target.partition(":")
        if sep and kind == "view":
            self.action_view(arg)
            return True
        if sep and kind == "style":
            self.action_visual_style(arg)
            return True
        if sep and kind == "viewport":
            m = getattr(self.viewport, arg, None)
            if m is None:
                return False
            m()
            return True
        if sep and kind == "layout":
            return self._layout_toggle(arg)
        obj = getattr(self, target, None)
        if obj is None:
            return False
        if isinstance(obj, QAction):
            if not obj.isEnabled():
                return False
            obj.trigger()                      # M165 R3: the recorder
            return True                        #  slots note the ring
        if target in REPEATABLE_TARGETS:       # M165 R3: a METHOD door
            self._note_cmd(target, "doc", "target",   #  (Hole's key path:
                         target)               #   never a QAction) - the
        obj()                                  #  two branches are
        return True                            #  exclusive, so no double
                                               #  record (risk 1, dead)

    def _layout_toggle(self, what: str) -> bool:
        if what == "browser":
            self.rail.setVisible(not self.rail.isVisible())
            return True
        if what in ("cube", "nav", "datums"):
            attr = "show_" + what
            setattr(self.viewport, attr, not getattr(self.viewport, attr))
            self.viewport.update()
            return True
        if what == "reset":
            self.rail.setVisible(True)
            self.viewport.show_cube = True
            self.viewport.show_nav = True
            self.action_view("fit")
            return True
        return False

    def action_extrude_key(self):
        """E — Fusion extrudes from anywhere: it finishes the active
        sketch profile, and asks for one when there is none."""
        if (self.stack.currentWidget() is self._sketch_page
                and self.sketch.model is not None):
            self.sketch.finish()
        else:
            self.status.showMessage(
                "Extrude wants a profile — press N, draw a closed "
                "sketch, then E")

    def action_toggle_active_visible(self):
        if self.doc is None or not self.doc.active_body:
            return
        self._toggle_body_visible(self.doc.active_body)

    def action_recompute(self):
        """Ctrl+B — Fusion's Compute All: rebuild every feature now."""
        if self.doc is not None:
            self.doc.recompute()
            self.viewport.refresh()
            self.status.showMessage("Computed all", 2000)

    def action_view(self, kind: str):
        if kind == "fit":
            if self.viewport._bbox is not None:
                # M166 R3: Fit FLIES — the menu/palette fit rides the
                # viewport's own fit door (orientation held, framing
                # tweened), the SAME one transition law as the views.
                self.viewport.glide_fit(self.viewport._bbox)
        else:
            # M166 R1: the menu no longer teleports into cam privates -
            # it rides the viewport's glide door (one transition law).
            self.viewport.snap_view(kind)
        self.viewport.update()

    def action_toggle_grid(self):
        self._renderer.show_grid = not self._renderer.show_grid
        self.viewport.update()

    def action_toggle_edges(self):
        self._renderer.show_edges = not self._renderer.show_edges
        self.viewport.update()

    def action_pick_radius(self):
        """M160 (FD8-45): the pickbox. ONE knob for click tolerance AND
        hover preview, DIPs 0..20, default 3 — AutoCAD's own numbers;
        0 disables hover PREVIEWING (their PICKBOX=0 law), exact clicks
        keep working. App-persisted like every viewport manner.
        M163 W1: commit-only — a per-boundary preview would WRITE
        QSettings (preview renders, never persists); the honest feedback
        is the status voice at the green button."""
        prior = self.viewport.pick_radius
        fields = [dict(key="r", kind="double",
                       label="Pick radius (0 = no hover preview)",
                       default=prior, min=0.0, max=20.0, decimals=1,
                       suffix=" DIP", step=1.0)]   # PICKBOX is integers

        def commit(v):
            r = self.viewport.set_pick_radius(v["r"])
            self.status.showMessage(
                f"Pick radius {r:g} DIP — "
                + ("hover preview is OFF (PICKBOX = 0)" if r <= 0
                   else "clicks and hover share this one box"), 5000)

        def abort():
            self.viewport.set_pick_radius(prior)   # defensive restore:
            self.status.showMessage(               #  proves the contract
                "Pick radius cancelled", 3000)     #  for commit-only

        cmdpanel.run(self, "pick_radius", "Pick radius", fields,
                     commit=commit, abort=abort,
                     remember_key=False)   # the memory is pick/radius
                                           #  QSettings inside the setter

    def action_readout_toggle(self):
        """M160 (FD8-34): 'show detail measure' — the bottom-right spec
        line is a preference, remembered, effective this instant."""
        self.viewport.set_readout_visible(self.act_readout.isChecked())

    def action_export(self, ext: str = ".stl"):
        if self.doc is None or self.doc.result is None:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("Nothing to export — add a feature "
                                    "first", 5000)
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
            from .. import __version__
            meta = {"title": self.doc.title or name,
                    "application": f"Tracer Studio {__version__}"}
            for g in reversed(self.doc.drawings or []):
                author = (g.get("block") or {}).get("author")
                if author:                       # the title block knows
                    meta["designer"] = author
                    break                        # who drew this
            out = fio.export_solids(self.doc.export_solids(), path,
                                    meta=meta,
                                    appearances=self.doc.export_appearances())
            self.status.showMessage(f"Exported {out}", 6000)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def action_save_as_mesh(self, body_name: str):
        """M201 R16 [MESH-SAVE-AS-MESH / MESH-EXPORT-TOOLS, verbatim]:
        Save As Mesh - the page's dialog carries EXACTLY three rows
        in steps order: Format {3MF | STL (Binary) | STL (ASCII) |
        OBJ}, Unit Type {Centimeter | Millimeter | Meter | Inch |
        Foot} (the page glosses Centimeter ONLY - "One unit from the
        design equals one centimeter." - and the kernel CONVERTS per
        that one printed sentence: a 60 mm boss saved as Centimeter
        leaves as SIX, the same boss), and Structure {One File | One
        Body Per File}. "default" counts ZERO on the page: all three
        rests are OURS, stamped - STL (Binary) (the house's legacy
        export voice), Millimeter (the units rung's stamped mm house)
        and One File. The page's DEFECT - "The Save STL dialog
        displays." after OK whatever the format - is not cloned stale:
        the file dialog wears the CHOSEN format's name. The closing
        sentence is ours (the page prints no status), mirroring the
        page's own close: the body IS saved as a 3MF, OBJ, or STL
        file in the location the user specified. No component door
        yet (the page's component half waits for the components
        rung); from a body row the door saves THAT body, so the two
        Structure branches honestly collapse to one file - the
        per-body naming rides the kernel, proven at kernel level."""
        if self.doc is None or self.doc.result is None:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("Nothing to save — add a feature "
                                    "first", 5000)
            return
        parts = [(n, s) for (n, s) in self.doc.export_solids()
                 if n == body_name]
        if not parts:
            self.status.showMessage(f"Save As Mesh refused: {body_name!r} "
                                    "has no solid to save", 6000)
            return
        v = cmddialog.ask(self, "Save As Mesh", [
            dict(key="fmt", label="Format", kind="combo",
                 choices=["3MF", "STL (Binary)", "STL (ASCII)", "OBJ"],
                 default="STL (Binary)"),
            dict(key="unit", label="Unit Type", kind="combo",
                 choices=["Centimeter", "Millimeter", "Meter", "Inch",
                          "Foot"], default="Millimeter"),
            dict(key="struct", label="Structure", kind="combo",
                 choices=["One File", "One Body Per File"],
                 default="One File"),
        ], remember_key="save_as_mesh")
        if v is None:
            return
        suffix = fio.MESH_AS_FORMATS[v["fmt"]]
        name = (self.doc.title or "model").replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(
            self, f"Save {v['fmt']} file",
            str(Path.home() / f"{name}{suffix}"),
            f"{v['fmt']} (*{suffix})")
        if not path:
            return
        try:
            from .. import __version__
            meta = {"title": self.doc.title or name,
                    "application": f"Tracer Studio {__version__}"}
            paths = fio.save_mesh_as(parts, path, v["fmt"], unit=v["unit"],
                                     structure=v["struct"], meta=meta,
                                     appearances=self.doc.export_appearances())
        except ValueError as e:
            self.status.showMessage(f"Save As Mesh refused: {e}", 6000)
            return
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        self.status.showMessage(
            f"Saved {body_name} as {v['fmt']} to {paths[0]}", 6000)

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
                                      GeometricPatternFeature,
                                      ScaleFeature,
                                      PathPatternFeature,
                                      BodyFilletFeature))
                and not f.suppressed]

    def action_path_pattern(self):
        """Fusion Pattern-on-Path (M50): the open line/arc chain of the
        current sketch is the walk — N equally spaced copies of the
        chosen feature ride it, translation first (v1).
        M200 R3 [SLD-REF-PATTERN, verbatim] grew the page's
        Orientation row - "Identical: Orients all pattern instances
        to match the source object" (the v1 voice, the default) |
        "Path Direction: Orients each pattern instance relative to
        its position along the path" (each copy turns by the angle
        the path has turned since the source).  Start Point and the
        Distance/Distribution row are the page's other path mouths
        and stay UNOFFERED until a rung cuts them."""
        if self.doc is None or self.doc.result is None:
            return
        m = self.sketch.model
        if m is None:
            # M189 R4 [LAW-61(a)]: recipe guidance steps down.
            self.status.showMessage("Pattern on Path runs from a sketch: "
                                    "draw a connected OPEN chain of "
                                    "lines/arcs, starting it at the "
                                    "feature you want to repeat", 6000)
            return
        cands = self._pattern_candidates()
        if not cands:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("Nothing to pattern — create a "
                                    "feature first", 5000)
            return
        from ..core.sweep import path_chain
        try:
            pts, closed = path_chain(m, need_circle=False)
        except ValueError as e:
            # M189 R5 [LAW-61(a)]: a dry-run path rejection is INPUT -
            # the R2 family voice, kernel words intact.
            self.status.showMessage(f"Pattern on Path refused: {e}",
                                    6000)
            return
        if closed or len(pts) < 2:
            # M189 R5 [LAW-61(a)]: ditto the open-chain shape rule (the
            # v1 law rides the sentence, not the window).
            self.status.showMessage(
                "Pattern on Path refused: the path must be an OPEN "
                "chain of lines/arcs - v1 does not loop", 6000)
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Pattern on Path", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="count", label="Occurrences along the path",
                 kind="int", default=4, min=2, max=200, group="Pattern"),
            dict(key="orient", label="Orientation", kind="combo",
                 choices=["Identical", "Path Direction"],
                 default="Identical", group="Pattern"),
        ], remember_key="path_pattern")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        orient = "path" if str(v["orient"]) == "Path Direction" \
            else "identical"
        self._capture()
        self.doc.add(PathPatternFeature(
            name=f"Path of {src.name}", op=src.op, source_uid=src.uid,
            path=[list(map(float, p)) for p in pts],
            count=int(v["count"]), plane=m.plane,
            placement=tuple(map(float, m.origin)), axes=m.axes,
            orientation=orient))
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Patterned {src.name} \u00d7{v['count']} along the path"
            + (", each turned to its place along it"
               if orient == "path" else ""), 6000)

    def action_circular_pattern(self):
        """M200 R2 [SLD-REF-PATTERN, verbatim] grew the ONE dialog
        with the page's circular Distribution row - "Full: Distributes
        pattern instances 360 degrees around the axis" | "Partial:
        ...in one direction from the source object around the axis to
        an angle value that you specify" | "Symmetric: ...
        symmetrically in two directions from the source object around
        the axis to an angle value that you specify".  The page's
        FULL words NO angle, so a Full pick NOTICES the typed Angle
        row and NEVER WRITES it (the draft door's two-voice law - one
        record one voice); Partial and Symmetric write it as the rung
        era always did.  Suppression and Compute Type stay UNOFFERED
        (canvas checkboxes / feature-face BRep)."""
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            # M189 R4 [LAW-61(a)]: precondition in information clothing
            # (three twins in this file + the scale/mirror/no-body kin).
            self.status.showMessage("Nothing to pattern — create a "
                                    "feature first", 5000)
            return
        names = [f.name for f in cands]
        axes = ["+Z (through center)"] + ["X (origin)", "Y (origin)",
                                          "Z (origin)"] \
            + [a["name"] for a in self.doc.axes]
        # M201 R15 [SLD-REF-PATTERN]: the page's circular dialog
        # carries EXACTLY the Axis and Distribution rows - an angle
        # row belongs ONLY to the two words that say "to an angle
        # value that you specify" (Partial, Symmetric).  A modal door
        # cannot gate rows (the lever can, and does - R2), so the
        # Angle row rides the house's conditional-row law: under
        # FULL it is NOTICED and NEVER WRITTEN (the record carries
        # the page's own 360: "Distributes pattern instances 360
        # degrees around the axis"), and the sentence and the rail
        # speak the page's Full words, never the row's value.  One
        # dialog, as always.
        v = cmddialog.ask(self, "Circular Pattern", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="axis", label="Axis", kind="combo", choices=axes,
                 group="Axis"),
            dict(key="cx", label="Center X", kind="double", default=0.0,
                 min=-1e5, max=1e5, group="Axis"),
            dict(key="cy", label="Center Y", kind="double", default=0.0,
                 min=-1e5, max=1e5, group="Axis"),
            dict(key="dist", label="Distribution", kind="combo",
                 choices=["Full", "Partial", "Symmetric"], default="Full",
                 group="Pattern"),
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
        dist = str(v["dist"]).lower()         # the page's own voice
        ang = 360.0 if dist == "full" else float(v["ang"])
        # Full takes NO angle (page words none): the typed row is
        # noticed, never written - the record carries the default.
        count = v["count"]
        axsel = v["axis"]
        axis = "" if axsel.startswith("+Z") else \
            axsel[0] if "(origin)" in axsel else axsel
        self._capture()
        feat = self.doc.add_circular_pattern(f"Circle of {src.name}", src,
                                             (cx, cy), ang, count,
                                             axis=axis, distribution=dist)
        try:
            self.doc.recompute()       # the row lands on success
        except Exception as e:
            # M200 R1 door law kept whole: a refusal leaves NOTHING -
            # no record, no undo step that undoes nothing, the
            # kernel's cure verbatim ("an odd count has one, an even
            # one does not").
            self.doc.features.remove(feat)
            self.doc.dirty = True
            self.recompute()
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Pattern refused: {e}", 6000)
            return
        self.recompute()
        self.viewport.refresh(fit=True)
        pivot = f"axis {axis!r}" if axis else f"({cx:g}, {cy:g})"
        # M201 R15 [SLD-REF-PATTERN]: a Full pick speaks the page's
        # OWN number - "Full: Distributes pattern instances 360
        # degrees around the axis" - never the Angle row's value,
        # which was never asked of it (the row rides noticed-and-
        # unwritten, the conditional-row law).  Partial and Symmetric
        # are the page's two angle-speakers and keep "over Ng".
        spoke = ("over 360 degrees" if dist == "full"
                 else f"over {ang:g}\u00b0")
        self.status.showMessage(
            f"Patterned {src.name}: {count}x {spoke} about "
            f"{pivot}"
            + (", symmetrically from the source" if dist == "symmetric"
               else ""), 6000)

    def action_linear_pattern(self):
        """M200 [SLD-REF-PATTERN, verbatim] grew the ONE dialog with
        the page's two typed rows: Distribution - "Spacing: ...spaced
        at the distance value" | "Extent: Distributes pattern
        instances evenly along the FULL EXTENT of the distance value
        that you specify" - and Direction - "One direction: ...in one
        direction from the source" | "Symmetric: ...symmetrically in
        two directions from the source object".  The X/Y/Z rows are
        the page's Distance row in the house's plain-speech voice;
        their meaning FLIPS with Distribution, so they now say
        "distance", the page's own word ("the meaning flips with the
        Distribution row").  Suppression (canvas checkboxes) and
        Compute Type (feature-face BRep) are NOT offered: doors do
        not promise what cannot bake.

        M201 R15 [SLD-REF-PATTERN, the naming pass]: the door and the
        Create menu now wear the PAGE's name - "Rectangular Pattern" -
        the word "linear" lives only in the CAM book, and the ribbon
        tooltip already spoke "Rectangular pattern" while the menu
        said Linear: the house's OWN mouth-conflict, healed.  The two
        count rows are labeled "Occurrences"/"Occurrences 2" - OURS:
        the page's row is "Quantity" ("Specify the number of pattern
        instances to create along or around an axis or path"), kept
        under the rung-era label on purpose.  The Direction row's
        words follow the REFERENCE page's casing, "One direction"."""
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            # M189 R4 [LAW-61(a)]: precondition in information clothing
            # (three twins in this file + the scale/mirror/no-body kin).
            self.status.showMessage("Nothing to pattern — create a "
                                    "feature first", 5000)
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Rectangular Pattern", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="dx", label="X distance", kind="double", default=10.0,
                 min=-1e5, max=1e5, decimals=3, group="Direction"),
            dict(key="dy", label="Y distance", kind="double", default=0.0,
                 min=-1e5, max=1e5, decimals=3, group="Direction"),
            dict(key="dz", label="Z distance", kind="double", default=0.0,
                 min=-1e5, max=1e5, decimals=3, group="Direction"),
            dict(key="count", label="Occurrences", kind="int", default=3,
                 min=2, max=500, group="Pattern"),
            dict(key="dist", label="Distribution", kind="combo",
                 choices=["Spacing", "Extent"], default="Spacing",
                 group="Pattern"),
            dict(key="dir", label="Direction", kind="combo",
                 choices=["One direction", "Symmetric"],
                 default="One direction", group="Pattern"),
            # M201 [SLD-REF-PATTERN + rectangular how-to, verbatim]:
            # the vendor's ONE tool carries a second direction - the
            # Quantity row reads "Specify the number of pattern
            # instances to create along or around an axis or path" for
            # EACH axis, and the how-to words the single-direction case
            # as "To create a Rectangular Pattern in only one direction,
            # set the Quantity value for Axis 2 to 1".  So Occurrences 2
            # DEFAULTS TO 1: nothing second is asked, the sentence keeps
            # its rung-era shape, and the door's own default is the
            # page's own one-direction case.
            dict(key="count2", label="Occurrences 2", kind="int",
                 default=1, min=1, max=500, group="Second direction"),
            dict(key="dx2", label="X distance 2", kind="double",
                 default=0.0, min=-1e5, max=1e5, decimals=3,
                 group="Second direction"),
            dict(key="dy2", label="Y distance 2", kind="double",
                 default=0.0, min=-1e5, max=1e5, decimals=3,
                 group="Second direction"),
            dict(key="dz2", label="Z distance 2", kind="double",
                 default=0.0, min=-1e5, max=1e5, decimals=3,
                 group="Second direction"),
            dict(key="dist2", label="Distribution 2", kind="combo",
                 choices=["Spacing", "Extent"], default="Spacing",
                 group="Second direction"),
            dict(key="dir2", label="Direction 2", kind="combo",
                 choices=["One direction", "Symmetric"],
                 default="One direction", group="Second direction"),
        ], remember_key="linear_pattern")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        dx, dy, dz = v["dx"], v["dy"], v["dz"]
        count = v["count"]
        dist = "extent" if str(v["dist"]) == "Extent" else "spacing"
        dirn = "symmetric" if str(v["dir"]) == "Symmetric" else "one"
        count2 = int(v["count2"])
        dx2, dy2, dz2 = v["dx2"], v["dy2"], v["dz2"]
        dist2 = "extent" if str(v["dist2"]) == "Extent" else "spacing"
        dirn2 = ("symmetric" if str(v["dir2"]) == "Symmetric" else "one")
        self._capture()
        feat = self.doc.add_linear_pattern(
            f"Pattern of {src.name}", src, (dx, dy, dz), count,
            distribution=dist, direction=dirn,
            vector2=(dx2, dy2, dz2), count2=count2,
            distribution2=dist2, direction2=dirn2)
        try:
            self.doc.recompute()       # the row lands on success
        except Exception as e:
            # M197 door law: a refusal leaves NOTHING - no record, no
            # undo step that undoes nothing, the kernel's cure words
            # verbatim ("an odd count has one, an even one does not").
            self.doc.features.remove(feat)
            self.doc.dirty = True
            self.recompute()
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Pattern refused: {e}", 6000)
            return
        self.recompute()
        self.viewport.refresh(fit=True)
        at = (" over the full extent" if dist == "extent" else " at")
        tail = (", symmetrically from the source" if dirn == "symmetric"
                else "")
        base = (f"Patterned {src.name}: {count}x{at} ({dx:g}, {dy:g}, "
                f"{dz:g}) mm{tail}")
        if count2 == 1:
            # the page's own one-direction case: the rung-era sentence,
            # byte for byte, whatever the second rows were typed as.
            self.status.showMessage(base, 6000)
            return
        at2 = (" over the full extent" if dist2 == "extent" else " at")
        tail2 = (", symmetrically from the source" if dirn2 == "symmetric"
                 else "")
        self.status.showMessage(
            f"{base} by {count2}x{at2} ({dx2:g}, {dy2:g}, {dz2:g}) "
            f"mm{tail2}", 6000)

    def _mirror_feature(self, src, plane=None, off=None, operation="join"):
        """Symmetric twin of ``src`` across a datum plane — an origin
        plane or any M125 construction plane. Mirroring the part's
        mid-plane reproduces Fusion's most common mirror (e.g. a
        one-sided lug on a bracket).  Whatever the caller already knows
        (plane from a menu, values from the ribbon panel) skips the
        prompt — what's missing lands in ONE live panel (M163).
        `operation` is the page's Operation row (M201): "join" (the
        legacy voice, the twin lands in the source's body) or "new"
        (a body of the twin's own).  The panel this method opens asks
        the PLANE and the OFFSET — never the operation — so a caller
        that did not ask cannot write it: the browser menu's mirror
        stays the join it always was."""
        known = plane is not None
        is_origin = plane in MirrorFeature.NORMALS
        if off is None:
            fields = [] if known else [
                dict(key="plane", label="Mirror plane", kind="combo",
                     choices=["YZ", "XZ", "XY"] +
                     [p["name"] for p in self.doc.planes], group="Plane")]
            default_off = 0.0
            if known and is_origin and self.doc.result is not None:
                # default to the model's own mid-plane along that normal
                n0 = np.array(MirrorFeature.NORMALS[plane], float)
                bb = self.doc.result.bounding_box
                default_off = float((bb.mean(0) * n0).sum())
            fields.append(dict(key="off", label="Plane offset",
                               kind="double", default=default_off,
                               min=-1e6, max=1e6, group="Plane"))

            def preview(v):
                self._mirror_preview(
                    src, plane if known else v["plane"], v["off"])

            def commit(v):
                self._mirror_feature(src, plane if known else v["plane"],
                                     v["off"])

            cmdpanel.run(self, "mirror", "Mirror", fields,
                         preview=preview, commit=commit,
                         abort=self._cmdpanel_abort("Mirror"),
                         remember_key="mirror")
            return
        self._capture()
        knew = {b["name"] for b in self.doc.bodies}
        feat = self.doc.add_mirror(f"Mirror of {src.name}", src, plane, off,
                                   operation=operation)
        try:
            self.doc.recompute()       # the row lands on success
        except Exception as e:
            # M197 door law, M201 edition: a refusal leaves NOTHING -
            # not the record, not the body a "new" mirror had to open,
            # not the undo step that would undo nothing.
            self.doc.features.remove(feat)
            self.doc.bodies = [b for b in self.doc.bodies
                               if b["name"] in knew]
            if self.doc.active_body not in knew:
                self.doc.active_body = (self.doc.bodies[0]["name"]
                                        if self.doc.bodies else None)
            self.doc.dirty = True
            self.recompute()
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Mirror refused: {e}", 6000)
            return
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Mirrored {src.name} across {plane} @ {off:g} mm"
            + (f" as a new body ({feat.body})" if operation == "new"
               else ""), 6000)

    def action_geometric_pattern(self):
        """Fusion's Geometric Pattern (M126): a T·R·S lattice — two step
        transforms, each translate + rotate about a named axis + scale
        about a base point, raised to grid indices. Directions and the
        pivot are NAMES when the datum store should drive them (M125);
        count 2 = 1 keeps it a single-direction spiral.

        M201 R15 [audit stamp]: this door is DECLARED HOUSE-NAMED
        WHOLESALE.  The vendor's Geometric Pattern lives behind the
        Plastic extension (Create > Geometric Pattern) and the only
        page the family sweep ever found is a HOW-TO - no reference
        page prints its row words - so EVERY word this door speaks
        (rows, choices, statuses) is OURS by declaration, not a
        clone: "Direction 1/2", "Rotate about", "Scale about",
        "Grid", and the T·R·S law in the kernel.  Nothing here
        claims a page; if a reference page surfaces later, the door
        answers to it rung by rung."""
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            # M189 R4 [LAW-61(a)]: precondition in information clothing
            # (three twins in this file + the scale/mirror/no-body kin).
            self.status.showMessage("Nothing to pattern — create a "
                                    "feature first", 5000)
            return
        names = [f.name for f in cands]
        dirs = ["X", "Y", "Z"] + [a["name"] for a in self.doc.axes]
        v = cmddialog.ask(self, "Geometric Pattern", [
            dict(key="src", label="Feature to pattern", kind="combo",
                 choices=names, group="Object"),
            dict(key="axis", label="Rotate / scale about", kind="combo",
                 choices=dirs, default="Z", group="Pivot"),
            dict(key="base", label="Base point", kind="text",
                 default="0,0,0", group="Pivot"),
            dict(key="d1", label="Direction 1", kind="combo",
                 choices=dirs, default="X", group="First step"),
            dict(key="n1", label="Count", kind="int", default=4, min=1,
                 max=64, group="First step"),
            dict(key="t1", label="Translate per step", kind="double",
                 default=8.0, min=-1e5, max=1e5, group="First step"),
            dict(key="r1", label="Rotate per step", kind="double",
                 default=0.0, min=-359.9, max=359.9, suffix="°",
                 group="First step"),
            dict(key="k1", label="Scale per step", kind="double",
                 default=1.0, min=0.01, max=100.0, group="First step"),
            dict(key="d2", label="Direction 2", kind="combo",
                 choices=dirs, default="Y", group="Second step"),
            dict(key="n2", label="Count", kind="int", default=1, min=1,
                 max=64, group="Second step"),
            dict(key="t2", label="Translate per step", kind="double",
                 default=0.0, min=-1e5, max=1e5, group="Second step"),
            dict(key="r2", label="Rotate per step", kind="double",
                 default=0.0, min=-359.9, max=359.9, suffix="°",
                 group="Second step"),
            dict(key="k2", label="Scale per step", kind="double",
                 default=1.0, min=0.01, max=100.0, group="Second step"),
        ], remember_key="geometric_pattern")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        try:
            base = self._pt(v["base"])
        except params.ParamError as exc:
            self.status.showMessage(f"Lattice refused: {exc}", 6000)
            return
        self._capture()
        self.doc.add_geometric_pattern(
            f"Lattice of {src.name}", src, axis=v["axis"], base=base,
            d1=v["d1"], n1=v["n1"], t1=v["t1"], r1=v["r1"], k1=v["k1"],
            d2=v["d2"], n2=v["n2"], t2=v["t2"], r2=v["r2"], k2=v["k2"])
        self.recompute()
        self.viewport.refresh(fit=True)
        span = (f"{v['n1']}x{v['n2']} along {v['d1']} x {v['d2']}"
                if v["n2"] > 1 else f"{v['n1']} along {v['d1']}")
        twist = "" if not (v["r1"] or v["k1"] != 1) else \
            " (spiral: rotated/shrinking per step)"
        self.status.showMessage(
            f"Patterned {src.name}: lattice of {span}{twist} about "
            f"{v['axis']}", 6000)

    def action_scale(self):
        """Fusion's Scale (M126): resize one feature's solid about a
        base point — uniform or per axis; a negative factor mirrors
        that axis (left-hand parts from right-hand models).

        M201 R11 [GUID-D3F6F79B... verbatim]: the door now wears the
        page's OWN row names - "Scale Type" ("Uniform: Scales the
        selected bodies uniformly on all axes. For example, enter
        -0.5 to halve the size or 2 to double it." / "Non Uniform:
        Scale along the X, Y, and Z axes separately." - the page
        spells "Non Uniform" WITHOUT a hyphen), "Scale Factor:
        Specify the proportional value to scale the bodies." and the
        three per-axis rows the page names "X Distance" / "Y
        Distance" / "Z Distance" ("Specifies the value to scale in
        the X direction." - a VALUE, no units anywhere on the page,
        so each label says what it is: a scale value). The page's
        -0.5 example HALVES; on our kernel a negative also MIRRORS
        (m126's pinned law) - so the factor label carries the house
        fact the page is silent about. "default" counts ZERO on the
        page: every rest here is the house's, and the house rests on
        the identity (factor 1, Non-Uniform rests at 1,1,1). The
        anchor is the page's "pick a fixed anchor point" spoken
        plainly as XYZ numbers - origin is NOT documented as the
        vendor's default, the (0,0,0) rest is ours."""
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("Nothing to scale — create a feature "
                                    "first", 5000)
            return
        names = [f.name for f in cands]
        v = cmddialog.ask(self, "Scale", [
            dict(key="src", label="Feature to scale", kind="combo",
                 choices=names, group="Object"),
            dict(key="base", label="Base point", kind="text",
                 default="0,0,0", group="Frame"),
            dict(key="mode", label="Scale Type", kind="combo",
                 choices=("Uniform", "Non Uniform"), group="Size"),
            # THE UNIT-SUFFIX LAW (R11, film-caught): ask() defaults
            # every double to " mm"; a scale VALUE is dimensionless -
            # the page prints no units - so the suffix is cleared BY
            # HAND here (the lever's plain=True clears it at its own
            # source). A ratio may not wear millimetres any more than
            # an angle may (R1b's lesson, generalised).
            dict(key="k", label="Scale Factor (negative mirrors too)",
                 kind="double", suffix="",
                 default=1.5, min=-1000.0, max=1000.0, group="Size"),
            dict(key="kx", label="X Distance (a scale value)",
                 kind="double", suffix="", default=1.0,
                 min=-1000.0, max=1000.0, group="Size"),
            dict(key="ky", label="Y Distance (a scale value)",
                 kind="double", suffix="", default=1.0,
                 min=-1000.0, max=1000.0, group="Size"),
            dict(key="kz", label="Z Distance (a scale value)",
                 kind="double", suffix="", default=1.0,
                 min=-1000.0, max=1000.0, group="Size"),
        ], remember_key="scale")
        if v is None:
            return
        src = cands[names.index(v["src"])]
        try:
            base = self._pt(v["base"])
        except params.ParamError as exc:
            self.status.showMessage(f"Scale refused: {exc}", 6000)
            return
        if v["mode"].startswith("Uniform"):
            factors = (v["k"],) * 3
        else:
            factors = (v["kx"], v["ky"], v["kz"])
        if not all(factors):
            self.status.showMessage(
                "Scale refused: a factor of 0 collapses the solid", 6000)
            return
        self._capture()
        self.doc.add_scale(f"Scaled {src.name}", src, base=base,
                           factors=factors)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Scaled {src.name} by "
            f"{'x'.join(f'{f:g}' for f in factors)} about ({v['base']})",
            6000)

    def action_coil(self):
        """Fusion's Coil (M127 v1), on-center and honest: a circular or
        square section riding a helix about a NAMED axis; height is
        turns x pitch (the classic two-of-three forward). Springs and
        boss threads; internal cut-threads deliberately aren't offered
        — decoration serves them better on any kernel."""
        if self.doc is None:
            return
        dirs = ["X", "Y", "Z"] + [a["name"] for a in self.doc.axes]
        v = cmddialog.ask(self, "Coil", [
            # M201 R12 [SLD-REF-COIL, verbatim]: "Type: Select the
            # type of coil to create. | Revolution And Height: Creates
            # a coil with a specific number of revolutions and a
            # specific height. | Revolution And Pitch: ... | Height
            # And Pitch: ..." - the page's TWO-OF-THREE contract:
            # every mode takes exactly two of {Revolutions, Height,
            # Pitch} and the third stands derived. Ours stores the
            # classic pair (turns, pitch) and derives height, so the
            # modes are SOLVER words: Revolution And Height divides
            # height by revolutions, Height And Pitch divides height
            # by pitch - arithmetic only, the kernel never moves.
            # THREE of the page's four words are offered: SPIRAL (the
            # page's fourth, a coil whose radius winds outward) is NOT
            # what coil_solid sweeps - a door may not promise what
            # cannot bake - and a scripted Spiral is refused before
            # the capture, by name (R10's coin). REST "Revolution And
            # Pitch" is NAMED AS A HOUSE FACT: "default" counts ZERO
            # on both pages (R10's quoted-default bounty drew blanks
            # here); the house rests on the mode whose pair the record
            # already keeps unwounded. The REF page prints capital
            # "And" (the how-to's lowercase "and" is the minority
            # voice) - the door copies REF. Page order: Type is row
            # ONE; the page's Radius-vs-Diameter naming split (REF
            # "Radius ... to the center of the profile", the how-to
            # says Diameter) is answered honestly by NAMING the
            # convention we copy: our number is the how-to's DIAMETER
            # of the center circle the REF's Radius measures.
            dict(key="type", label="Type", kind="combo",
                 choices=("Revolution And Height",
                          "Revolution And Pitch", "Height And Pitch"),
                 default="Revolution And Pitch", group="Helix"),
            dict(key="axis", label="Helix axis", kind="combo",
                 choices=dirs, default="Z", group="Axis"),
            dict(key="base", label="Start point", kind="text",
                 default="0,0,0", group="Axis"),
            dict(key="diam",
                 label="Centre diameter (of the profile's center "
                       "circle)", kind="double",
                 default=8.0, min=0.001, max=1e5, group="Helix"),
            dict(key="turns", label="Revolutions", kind="double",
                 default=6.0, min=0.5, max=2000.0, decimals=1,
                 suffix="", group="Helix"),      # a COUNT, unit-free
            dict(key="height", label="Height", kind="double",
                 default=9.0, min=0.01, max=1e5, group="Helix"),
            dict(key="pitch", label="Pitch", kind="double",
                 default=1.5, min=0.01, max=1e4, group="Helix"),
            dict(key="hand", label="Hand", kind="combo",
                 choices=("Right", "Left"), group="Helix"),
            dict(key="section", label="Section", kind="combo",
                 choices=("Circular", "Square"), group="Section"),
            dict(key="size", label="Section size", kind="double",
                 default=1.2, min=0.01, max=1e4, group="Section"),
        ], remember_key="coil")
        if v is None:
            return
        ctype = str(v.get("type", "Revolution And Pitch"))
        if ctype not in ("Revolution And Height", "Revolution And Pitch",
                         "Height And Pitch"):
            self.status.showMessage(
                f"Coil refused: the type is 'Revolution And Height', "
                f"'Revolution And Pitch' or 'Height And Pitch', not "
                f"{ctype!r}", 6000)
            return
        try:
            base = self._pt(v["base"])
        except params.ParamError as exc:
            self.status.showMessage(f"Coil refused: {exc}", 6000)
            return
        turns = float(v.get("turns", 6.0))
        pitch = float(v.get("pitch", 1.5))
        # the .get law (R5's coin): a remembered dict born before this
        # rung has no height row - it speaks the classic pair, under
        # which height is DERIVED, so its absence is the rest, not a
        # crash. Under a height mode a missing height divides to zero
        # and the refusal below names it.
        height = float(v.get("height", 0.0))
        # THE SOLVER (arithmetic only - the record keeps the classic
        # pair and the fold's own coil_solid refuses what it cannot
        # sweep; the door's preflight catches the DIVISIONS before
        # the capture, naming what would not stand).
        if ctype == "Revolution And Height":
            if not turns > 0.0 or not height > 0.0:
                self.status.showMessage(
                    "Coil refused: Revolution And Height needs "
                    "positive revolutions and height to divide", 6000)
                return
            pitch = height / turns
        elif ctype == "Height And Pitch":
            if not pitch > 0.0 or not height > 0.0:
                self.status.showMessage(
                    "Coil refused: Height And Pitch needs positive "
                    "height and pitch to divide", 6000)
                return
            turns = height / pitch
        self._capture()
        f = self.doc.add_coil(
            f"Coil {turns:g}x{pitch:g}", axis=v["axis"],
            base=base, diameter=v["diam"], pitch=pitch,
            turns=turns, hand=v["hand"].lower(),
            section=v["section"].lower(), size=v["size"],
            coil_type=ctype)
        self.recompute()
        ff = getattr(self.doc, "failed_feature", None)
        if ff is not None and ff[1] == f.name:
            return                          # M118 badge + modal already
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"{f.name} — {f.turns:g} turns x {f.pitch:g} mm pitch "
            f"= {f.height:g} mm tall, {v['section'].lower()} section "
            f"{v['size']:g} mm, {v['hand'].lower()}-handed on {v['axis']}",
            6000)

    def action_fluid_volume(self):
        """M201 R13 [SLD fluid volume page, verbatim]: "Fluid Volume
        creates a body that envelopes or fills the interior of the
        selected tool bodies." - the EXTERNAL half, honestly: the
        body is the envelope MINUS the tools. The page's Volume row
        offers External | Internal, but INTERNAL is a gate this
        kernel cannot pass ("You will not be permitted to complete
        the fluid body creation until the program detects a
        completely isolated interior volume" - and capping needs
        surface bodies we have none of), so the combo carries the
        ONE word that composes and a scripted other word is refused
        by name before the capture (R12's Spiral coin). The page's
        tool selection is a canvas PICK - our bridge is the check-
        list of NAMED bodies (names compose; geometry follows).
        Shape words are the page's, in page order: Box | Cylinder |
        Hemisphere, gated direction ("This option is available when
        the Shape Type is Cylinder or Hemisphere", words "X-Axis
        Y-Axis Z-Axis"), "Flip Direction to invert the hemisphere",
        and one distance: Offset, "the distance between the outer
        faces of the tool bodies and the outer faces of the fluid
        volume" - a DISTANCE, so it wears mm on both mouths (UNIT-
        SUFFIX LAW). Rests (External/Box/Z-Axis/flip off/offset 0)
        are HOUSE FACTS: "default" counts ZERO on the page."""
        if self.doc is None:
            return
        names = [b["name"] for b in self.doc.body_list()]
        v = cmddialog.ask(self, "Fluid Volume", [
            dict(key="volume", label="Volume", kind="combo",
                 choices=("External",), default="External",
                 group="Fluid"),
            dict(key="tools", label="Tool bodies", kind="checks",
                 choices=names, group="Fluid"),
            dict(key="shape", label="Shape Type", kind="combo",
                 choices=("Box", "Cylinder", "Hemisphere"),
                 default="Box", group="Shape"),
            dict(key="direction", label="Shape Direction",
                 kind="combo",
                 choices=("X-Axis", "Y-Axis", "Z-Axis"),
                 default="Z-Axis", group="Shape"),
            dict(key="flip", label="Flip Direction", kind="check",
                 default=False, group="Shape"),
            dict(key="offset", label="Offset", kind="double",
                 default=0.0, min=0.0, max=1e5, group="Shape"),
        ], remember_key="fluid")
        if v is None:
            return
        vol = str(v.get("volume", "External"))
        if vol != "External":
            # refused by name, quoting the page's own precondition
            self.status.showMessage(
                f"Fluid Volume refused: the volume is 'External', "
                f"not {vol!r} - the page: \"You will not be "
                "permitted to complete the fluid body creation "
                "until the program detects a completely isolated "
                "interior volume\"", 9000)
            return
        tools = [str(t) for t in (v.get("tools") or [])]
        if not tools:
            self.status.showMessage(
                "Fluid Volume refused: the page envelopes the "
                "selected tool bodies - select at least one", 6000)
            return
        from ..core import fluid                    # coil precedent
        shape = str(v["shape"])
        if shape not in fluid.SHAPES:
            self.status.showMessage(
                "Fluid Volume refused: the shape type is 'Box', "
                f"'Cylinder' or 'Hemisphere', not {shape!r}", 6000)
            return
        direction = str(v["direction"])
        if direction not in fluid.DIRECTIONS:
            self.status.showMessage(
                "Fluid Volume refused: the shape direction is "
                f"'X-Axis', 'Y-Axis' or 'Z-Axis', not {direction!r}",
                6000)
            return
        offset = float(v["offset"])
        if offset < 0.0:
            self.status.showMessage(
                "Fluid Volume refused: the offset is the distance "
                "between outer faces - it cannot be negative", 6000)
            return
        self._capture()
        b, f = self.doc.add_fluid_volume(
            tools, shape, volume=vol,
            direction=direction, flip=bool(v["flip"]), offset=offset)
        self.recompute()
        ff = getattr(self.doc, "failed_feature", None)
        if ff is not None and ff[1] == f.name:
            return                          # M118 badge + modal already
        self.viewport.refresh(fit=True)
        solid = self.doc.body_solids().get(f.name)
        vol_mm = solid.volume if solid is not None else 0.0
        self.status.showMessage(
            f"{f.name} — {shape} envelope around "
            + " + ".join(tools)
            + f", offset {offset:g} mm — {vol_mm:,.0f} mm³ of fluid",
            6000)

    def action_mirror(self):
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("Nothing to mirror — create a feature "
                                    "first", 5000)
            return
        names = [f.name for f in cands]
        planes = ["YZ", "XZ", "XY"] + [p["name"] for p in self.doc.planes]
        fields = [
            dict(key="src", label="Feature to mirror", kind="combo",
                 choices=names, group="Object"),
            dict(key="plane", label="Mirror plane", kind="combo",
                 choices=planes, group="Plane"),
            dict(key="off", label="Plane offset", kind="double",
                 default=0.0, min=-1e6, max=1e6, group="Plane"),
            # M201 [SLD-REF-MIRROR-DIALOG, verbatim]: "Operation:
            # Select whether to create a new body or join the mirrored
            # body with the original body." - "Join: Joins the mirrored
            # body with the original body, if they intersect. Solid
            # bodies are combined." (what this tool has ALWAYS done, so
            # it is the door's resting voice and old files replay it) |
            # "New Body: Creates a new body mirrored across the mirror
            # plane." The page states no initial value anywhere - the
            # word "default" does not appear on it - so Join is chosen
            # because it is the legacy voice, not because the vendor
            # named a default.
            dict(key="op", label="Operation", kind="combo",
                 choices=["Join", "New Body"], default="Join",
                 group="Boolean"),
        ]

        def src_of(v):
            return cands[names.index(v["src"]) if v.get("src") in names
                         else 0]

        # M163: the panel IS the command - live ghost while scrubbing,
        # the feature exists only at the green button.
        cmdpanel.run(self, "mirror", "Mirror", fields,
                     preview=lambda v: self._mirror_preview(
                         src_of(v), v["plane"], v.get("off", 0.0)),
                     commit=lambda v: self._mirror_feature(
                         src_of(v), v["plane"], v["off"],
                         "new" if str(v["op"]) == "New Body" else "join"),
                     abort=self._cmdpanel_abort("Mirror"),
                     remember_key="mirror")

    def _cmdpanel_abort(self, title: str):
        def _abort():
            self.viewport.preview_mesh(None)
            self.status.showMessage(f"{title} cancelled", 3000)
        return _abort

    def _mirror_preview(self, src, plane, off):
        """Ghost the mirrored twin onto the viewport WITHOUT touching
        the document — press-pull's cosmetic loop, one commit boundary
        at a time.  The build is feature-local (src.build(), pre-
        boolean); mirroring is a mesh transform, so the ghost stays in
        single-digit ms on maker parts.  Preview dies silently; only the
        Commit path reports."""
        if self.doc is None or self.doc.result is None:
            return
        try:
            n = MirrorFeature.NORMALS.get(plane)
            p0 = (0.0, 0.0, 0.0)
            if n is None:                       # M125 custom datum plane
                p0, _, _, nf = self.doc.plane_frame(plane)
                n = tuple(float(x) for x in nf)
            ghost = src.build()
            shift = tuple(p0[i] + n[i] * float(off) for i in range(3))
            ghost = (ghost.translated((-shift[0], -shift[1], -shift[2]))
                     .mirror(n).translated(shift))
            base = self.doc.result
            prev = (base.subtract(ghost) if src.op == "subtract"
                    else base.union(ghost))
        except Exception:
            return
        self.viewport.preview_mesh(prev)

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
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage(f"No body to {kind.lower()} — create "
                                    "a feature first", 5000)
            return
        angle = None
        dist2 = None
        if chamfer:
            # M196 R2 [SLD-REF-CHAMFER, verbatim]: "Type Select the
            # type of chamfer to create for the highlighted selection
            # set." with the rows "Distance" and "Angle (Distance And
            # Angle chamfer type only)".  The door now speaks the
            # vendor's rows through the house dialog; the angle WRITES
            # only under its own type (the page's parenthetical).
            # M196 R3: TWO DISTANCE landed in the kernel, so the list
            # grew exactly as the R2 comment promised it would - all
            # THREE page types now stand, in the page's own order, and
            # the second distance row writes only under its type (the
            # Equal choice NOTES both extra values and writes neither;
            # each other type notes what is not its business).  Page,
            # verbatim: "For the Two Distance chamfer type, you can
            # specify two different distance values. The first
            # distance value you specify applies to both sides."
            v = cmddialog.ask(self, "Chamfer body edges", [
                dict(key="type", label="Chamfer Type", kind="combo",
                     choices=["Equal Distance", "Two Distance",
                              "Distance And Angle"],
                     default="Equal Distance"),
                dict(key="distance", label="Distance", kind="double",
                     default=2.0, min=0.05, max=1e4),
                dict(key="dist2", label="Second distance",
                     kind="double", default=2.0, min=0.05, max=1e4),
                dict(key="angle", label="Angle", kind="double",
                     default=45.0, min=0.1, max=89.9, decimals=1,
                     suffix="\u00b0"),
            ], remember_key="chamfer_body_edges")
            if v is None:
                return
            size = float(v["distance"])
            if v["type"] == "Two Distance":
                dist2 = float(v["dist2"])
            elif v["type"] == "Distance And Angle":
                angle = float(v["angle"])
        else:
            size, ok = Shell.getDouble(
                self, "Fillet body edges", "Radius (mm):",
                2.0, 0.05, 1e4, 2)
            if not ok:
                return
        self._capture()
        n = sum(isinstance(f, BodyFilletFeature)
                for f in self.doc.features) + 1
        f = BodyFilletFeature(name=f"{kind}{n}", radius=size,
                              chamfer=chamfer, angle_deg=angle,
                              dist2=dist2)
        self.doc.features.append(f)
        self.doc.dirty = True
        try:
            self.doc.recompute()           # bakes the result on success
        except Exception as e:
            self.doc.features.remove(f)
            self.doc.dirty = True
            self.recompute()
            # M189 R5 [LAW-61(a)+R2 capture law]: a too-big radius is
            # fixable INPUT and the rollback already restored the doc -
            # so the refusal unwinds its undo step too (a refusal may
            # not leave a step that undoes nothing), and the kernel's
            # cure ("try a smaller size") rides the status line.
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(
                f"{kind} refused: {e} — try a smaller size; each fillet "
                "must fit between the faces around its edge", 6000)
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
            f"{kind}ed body edges at {size:g} mm"
            + (f" x {angle:g}\u00b0" if angle is not None
               else f" x {dist2:g} mm" if dist2 is not None else "")
            + f" · {how} · volume "
            f"{self.doc.result.volume:,.1f} mm³", 6000)

    def _body_draft(self):
        """M197 R2 [SLD-REF-DRAFT, verbatim]: "Fixed Plane Select a
        fixed plane to draft from" + "Angle Specify the draft angle".
        Rung three grows the page's own first row into the door -
        "Type Select the draft type." with the page's two types
        ("Fixed Plane", "Parting Line") - and the Parting Tool row
        spoken plainly as a height above the body's own bottom (the
        same plain-speech rung two gave the fixed plane).  The rows
        stand in the PAGE'S ORDER; one record one voice (M196 law):
        under a Fixed Plane the parting row is noticed and never
        written, under a Parting Line the fixed-plane row is.  Rung
        five grows the page's DRAFT SIDES: "Two Side: Create a draft
        on both sides of the parting line. Specify a different angle
        for each side" - a Draft sides combo with the page's two
        bakes (Symmetric = "a single angle for both sides", rung
        three's exact behavior; Two Side = the note's Angle 1 below
        the parting line and Angle 2 above), and the Angle 2 row it
        displays.  "One Side" is NOT offered: which side IS the Faces
        pick - a door may not promise what cannot bake.  Rung TEN
        grows the page's Angle Mode row - the FIRST quoted vendor
        default on this bench, resting on the page's own word
        "Relative" and measured inert on this kernel's straight
        walls (the door comment and the rail speak the law).  The
        face list and Tangent Chain are still NOT offered."""
        if self.doc is None or self.doc.result is None:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("No body to draft — create a "
                                    "feature first", 5000)
            return
        v = cmddialog.ask(self, "Draft body walls", [
            dict(key="type", label="Type", kind="combo",
                 choices=["Fixed Plane", "Parting Line"],
                 default="Fixed Plane"),
            dict(key="fixed", label="Fixed plane", kind="combo",
                 choices=["bottom", "top"], default="bottom"),
            # M201 R10 [SLD-REF-DRAFT, verbatim]: "Angle Mode (Fixed
            # Plane draft type only): Select how the draft angle is
            # measured. | Relative: Apply the draft angle relative to
            # the angle of the selected faces. This is the default. |
            # Absolute: Apply the draft angle from the Pull Direction,
            # regardless of any existing draft on the selected faces."
            # THE FIRST QUOTED VENDOR DEFAULT ON THIS BENCH ("default"
            # counts 1 on the reference page, 0 on the how-to - it
            # belongs to RELATIVE), so the door rests on the PAGE'S
            # own word, not the house's. PAGE ORDER: the row stands
            # where the page prints it (#3): after the Fixed Plane
            # choice and before the Parting Tool (#4). The page
            # GATES it "Fixed Plane draft type only" - the modal door
            # cannot open and close rows mid-command (R2's
            # conditional-row law), so under a Parting Line the word
            # is asked, stored and INERT, and the rail keeps silent
            # about it. THE AGREEMENT NOTE (honesty law): this kernel
            # leans straight vertical walls only, and a vertical
            # face's own angle is zero - the two readings NAME THE
            # SAME NUMBER here (measured), so the row promises no
            # difference and the rail speaks the agreement.
            dict(key="angle_mode",
                 label="Angle Mode (Fixed Plane only)",
                 kind="combo", choices=["Relative", "Absolute"],
                 default="Relative"),
            dict(key="parting", label="Parting line above the bottom",
                 kind="double", default=15.0, min=0.05),
            dict(key="angle_deg", label="Draft angle", kind="double",
                 default=10.0, min=-89.9, max=89.9, decimals=1,
                 suffix="\u00b0"),
            dict(key="sides", label="Draft sides", kind="combo",
                 choices=["Symmetric", "Two Side"],
                 default="Symmetric"),
            dict(key="angle2", label="Angle 2 above the parting line",
                 kind="double", default=10.0, min=-89.9, max=89.9,
                 decimals=1, suffix="\u00b0"),
        ], remember_key="draft_body_walls")
        if v is None:
            return
        # M201 R10 preflight (M197's law, angle-mode edition): a combo
        # cannot speak a third word, a scripted answer can - refuse
        # BEFORE the capture, naming the page's list (the door's words
        # and the kernel's guard speak the same sentence).
        amode = str(v.get("angle_mode", "Relative"))
        if amode not in ("Relative", "Absolute"):
            self.status.showMessage(
                f"Draft refused: the angle mode is 'Relative' or "
                f"'Absolute', not {amode!r}", 6000)
            return
        self._capture()
        n = sum(isinstance(f, DraftFeature)
                for f in self.doc.features) + 1
        parting = (float(v["parting"]) if str(v["type"]) == "Parting Line"
                   else None)               # noticed, never written
        two = str(v["sides"]) == "Two Side"  # read ALWAYS (the door
        a2 = float(v["angle2"])              # asked these rows)
        f = DraftFeature(name=f"Draft{n}",
                         angle_deg=float(v["angle_deg"]),
                         fixed=str(v["fixed"]),
                         angle_mode=amode,
                         parting=parting,
                         angle2=(a2 if two and parting is not None
                                 else None))  # fixed voice: noticed
        self.doc.features.append(f)
        self.doc.dirty = True
        try:
            self.doc.recompute()           # the lean lands on success
        except Exception as e:
            self.doc.features.remove(f)
            self.doc.dirty = True
            self.recompute()
            # M189 R5 law, M196 door law: a refusal may not leave an
            # undo step that undoes nothing, and the kernel's own cure
            # ("a cylinder on its axis or a box...", "must still reach
            # the parting line", "at an end it is the fixed plane")
            # rides the status line verbatim.
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Draft refused: {e}", 6000)
            return
        self.viewport.refresh(fit=True)
        self.rail.tree.reload()
        self.timeline.bar.update()
        lean = (f"at {f.angle_deg:g}\u00b0 below and {f.angle2:g}\u00b0 "
                f"above the parting line at {f.parting:g} mm"
                if f.angle2 is not None else
                f"at {f.angle_deg:g}\u00b0 from the "
                + (f"parting line at {f.parting:g} mm"
                   if f.parting is not None else f"{f.fixed}"))
        self.status.showMessage(
            f"Drafted body walls {lean}"
            f" · {f.n_walls} wall(s) leaned · volume "
            f"{self.doc.result.volume:,.1f} mm³", 6000)

    def _body_offset(self):
        """M198 R2 [SLD-OFFSET-FACES, verbatim]: "Select a single
        face ... and specify the Offset distance".  Rung three grows
        the door to the page's OWN plural - "a single face or
        MULTIPLE FACES and specify THE Offset DISTANCE": a Faces
        checks row (the plain names) and THE one distance, wearing
        millimetres and signed.  A new record speaks with faces;
        the `face` field is noticed and never written (one record
        one voice, the M196 law).  The manipulator and curved
        bodies beyond the rod's one wall are NOT offered: a door
        may not promise what cannot bake (the M196 law)."""
        if self.doc is None or self.doc.result is None:
            # M189 R4 [LAW-61(a)]: precondition in information clothing.
            self.status.showMessage("No body to offset — create a "
                                    "feature first", 5000)
            return
        v = cmddialog.ask(self, "Offset a face", [
            dict(key="faces", label="Faces", kind="checks",
                 choices=["bottom", "top", "wall", "+x", "-x", "+y",
                          "-y"],
                 checked=["top"]),
            dict(key="dist", label="Offset distance", kind="double",
                 default=5.0, min=-1000.0, max=1000.0, decimals=3,
                 suffix=" mm"),
        ], remember_key="offset_face")
        if v is None:
            return
        if not list(v["faces"]):
            # ZERO ticks is not a request - and under THIS door's
            # voice a faces-EMPTY record is the LEGACY single-face
            # route, so writing one would slide a face nobody
            # named (the R3 probe caught exactly that lie).  Refuse
            # before the capture: no record, no undo step that
            # undoes nothing, the kernel's own words verbatim.
            self.status.showMessage("Offset refused: name at least "
                                    "one face to offset", 6000)
            return
        self._capture()
        n = sum(isinstance(f, OffsetFaceFeature)
                for f in self.doc.features) + 1
        f = OffsetFaceFeature(name=f"Offset{n}",
                              faces=tuple(str(x) for x in v["faces"]),
                              dist=float(v["dist"]))
        self.doc.features.append(f)
        self.doc.dirty = True
        try:
            self.doc.recompute()           # the slide lands on success
        except Exception as e:
            self.doc.features.remove(f)
            self.doc.dirty = True
            self.recompute()
            # M189 R5 law, the door law: a refusal may not leave an
            # undo step that undoes nothing, and the kernel's own cure
            # ("this cylinder's faces are ...", "must still leave
            # material") rides the status line verbatim.
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(f"Offset refused: {e}", 6000)
            return
        self.viewport.refresh(fit=True)
        self.rail.tree.reload()
        self.timeline.bar.update()
        word = "face" if len(f.faces) == 1 else "faces"
        names = ", ".join(repr(x) for x in f.faces)
        self.status.showMessage(
            f"Offset {word} {names} by {f.dist:+g} mm · volume "
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
            # M189 R5 [LAW-61(a)+R2 capture law]: the ADJUST twin of the
            # refused resize - rollback restores the doc, so the undo
            # step unwinds too and the kernel cure speaks inline.
            self._undo.pop()
            self._redo.clear()
            self.status.showMessage(
                f"{kind} refused: {e} — kept {kind.lower()} at {old:g} "
                "mm; try a smaller size", 6000)
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
        # the GPU goes home with the window: a moderngl standalone
        # context is a process-lifetime allocation, and leaving it
        # alive behind a closed window is what OOM-killed the CI
        # suite tail (renderer.close law, cited M152)
        self._renderer.close()
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
            # M189 R4 [LAW-61(a)]: ditto the STEP twin.
            self.status.showMessage("Nothing to export — add a feature "
                                    "first", 5000)
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


class _AttachmentsDialog(QDialog):
    """M153: rung D's "Manage Lost Attachments". One row per lost
    attachment; verbs per species (§3 of the M153 contract): Re-Link
    is offered exactly the candidate sets the kernel can RESOLVE today
    (dead names drop — same predicate the warning uses; follow drops
    self and downstream, the L4c silent-death door), and the breaking
    verb speaks Detach / Stop Following / Retire Letter per species —
    datum has no break, a letter without a ref is the silence rung D
    ended. Refusals are the kernel's own named sentences, never a
    paraphrase. Every act recomputes through win.recompute() — the
    bridge keeps the badge, tree and status as the last word."""

    BREAK_LABELS = {"host": "Detach", "follow": "Stop Following",
                    "datum": "Retire Letter"}

    def __init__(self, win):
        super().__init__(win)
        from PySide6.QtWidgets import (QComboBox, QDialogButtonBox,
                                       QFormLayout)
        self._win = win
        self.setWindowTitle("Manage Lost Attachments")
        self._issue = QComboBox()
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._cands = QComboBox()
        self._relink_btn = QPushButton("Re-Link")
        self._break_btn = QPushButton("Detach")
        form = QFormLayout(self)
        form.addRow("Lost attachment:", self._issue)
        form.addRow("", self._detail)
        form.addRow("New host:", self._cands)
        bb = QDialogButtonBox(Qt.Horizontal)
        bb.addButton(self._relink_btn, QDialogButtonBox.ButtonRole.ActionRole)
        bb.addButton(self._break_btn, QDialogButtonBox.ButtonRole.ActionRole)
        bb.addButton(QDialogButtonBox.StandardButton.Close)
        form.addRow(bb)
        bb.rejected.connect(self.reject)
        self._issue.currentIndexChanged.connect(self._on_issue)
        self._relink_btn.clicked.connect(self._relink)
        self._break_btn.clicked.connect(self._break)
        self._reload()

    # ---- model ----------------------------------------------------------
    def _issues(self):
        return self._win.doc.attachment_issues

    def _current(self):
        issues = self._issues()
        idx = self._issue.currentIndex()
        return issues[idx] if 0 <= idx < len(issues) else None

    def _datum_kind(self, letter):
        dt = next((x for x in self._win.doc.datums
                   if x["letter"] == letter), None)
        return dt["kind"] if dt else "plane"

    def _candidates(self, i):
        """(DISPLAY, BIND) pairs — names bind names, hole-axes display
        names but bind uids (M146: ids are identity, names are paint)."""
        d = self._win.doc
        if i["species"] == "host":
            return [(n, n) for n in d.plane_candidates()]
        if i["species"] == "follow":
            return [(n, n) for n in d.follow_candidates(i["owner"])]
        kind = self._datum_kind(i["owner"])
        if kind == "plane":
            return [(n, n) for n in d.plane_candidates()]
        if kind == "axis":
            return [(n, n) for n in d.axis_candidates()]
        return [(nm, uid) for nm, uid in d.hole_axis_candidates()]

    # ---- view -----------------------------------------------------------
    def _reload(self):
        issues = self._issues()
        self._issue.blockSignals(True)
        self._issue.clear()
        for i in issues:
            self._issue.addItem(f"{i['species']}: {i['owner']} \u2014 "
                                f"lost {i['dead']!r}")
        self._issue.blockSignals(False)
        empty = not issues
        self._relink_btn.setEnabled(not empty)
        self._break_btn.setEnabled(not empty)
        self._cands.setEnabled(not empty)
        if empty:
            self._detail.setText("Nothing is lost any more — every "
                                 "attachment is home.")
            self._cands.clear()
        else:
            self._on_issue()

    def _on_issue(self):
        i = self._current()
        if i is None:
            return
        if i["species"] == "datum":
            self._detail.setText(
                f"Datum {i['owner']} (kind {self._datum_kind(i['owner'])})"
                f" lost {i['dead']!r}. Re-link re-binds it atomically; "
                "retiring takes the letter out of service.")
        else:
            self._detail.setText(
                f"{i['owner']} lost {i['dead']!r}. Re-linking does not "
                "move geometry — the frame stays frozen until an edit "
                "rides the new host.")
        self._cands.clear()
        for label, val in self._candidates(i):
            self._cands.addItem(label, val)
        self._break_btn.setText(self.BREAK_LABELS[i["species"]])

    # ---- verbs (kernel state layer; the bridge owns the recompute) ------
    def _act(self, fn, *a):
        try:
            fn(*a)
        except params.ParamError as e:
            # M189 R5 [LAW-61(a)]: the guard-first attach verbs raise
            # BEFORE touching the doc - a refused relink/break is
            # INPUT, and the kernel's own sentence drops to the
            # window's status line (the dock has no mouth of its own).
            self._win.status.showMessage(f"Change refused: {e}", 6000)
            return
        self._win.recompute()
        self._reload()

    def _relink(self):
        i = self._current()
        ref = self._cands.currentData()
        if i is None or ref is None:
            return
        d = self._win.doc
        if i["species"] == "host":
            self._act(d.relink_sketch, i["owner"], ref)
        elif i["species"] == "follow":
            self._act(d.relink_follow, i["owner"], ref)
        else:
            self._act(d.relink_datum, i["owner"],
                      self._datum_kind(i["owner"]), ref)

    def _break(self):
        i = self._current()
        if i is None:
            return
        d = self._win.doc
        if i["species"] == "host":
            self._act(d.break_sketch, i["owner"])
        elif i["species"] == "follow":
            self._act(d.break_follow, i["owner"])
        else:
            self._act(d.datum_remove, i["owner"])


class ClickableLabel(QLabel):
    """M164 R2: the DoF chip is a BUTTON without a button's chrome -
    anti-modal: a click selects, nothing else opens."""

    clicked = Signal()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and \
                self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(ev)
