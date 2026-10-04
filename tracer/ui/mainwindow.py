"""Application shell: menus, status bar, document <-> viewport wiring."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PySide6.QtCore import QSize, Qt, QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)

from ..core import io as fio
from ..core import step
from ..core.document import (BodyFilletFeature, CircularPatternFeature,
                             Document, ExtrudeFeature, ImportedFeature,
                             LinearPatternFeature, MirrorFeature,
                             PrimitiveFeature, RevolveFeature)
from ..core.sketch.model import (SketchModel, face_basis, model_from_dict,
                                 model_to_dict)
from . import icons
from .renderer import SceneRenderer
from .panels import LeftRail
from .shortcuts import TourDialog
from .sketcheditor import SketchCanvas
from .theme import DARK
from .timeline import TimelineHost
from .viewport import Viewport


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

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.rail)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.viewport)
        self._sketch_page = self._make_sketch_page()
        self.stack.addWidget(self._sketch_page)
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
        self.timeline.bar.feature_delete.connect(self._delete_feature)
        self.timeline.bar.home_clicked.connect(self.viewport.home)
        self.viewport.face_picked.connect(self._start_sketch_on_face)
        self.viewport.coords.connect(self._show_coords)
        self.viewport.press_pull.connect(self._press_pull)
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
        tb = QToolBar("Tools", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(22, 22))
        t = DARK
        tb.setStyleSheet(
            f"QToolBar {{ background: {t['bg0']}; padding: 2px 6px;"
            f" border-bottom: 1px solid {t['line']}; spacing: 3px; }}"
            f" QToolButton {{ border: none; border-radius: 5px;"
            f" padding: 3px; background: transparent; }}"
            f" QToolButton:hover {{ background: {t['bg2']}; }}"
            f" QToolButton:pressed {{ background: {t['line']}; }}"
            f" QToolButton::menu-indicator {{ subcontrol-position: right;"
            f" right: 2px; }}"
            f" QToolBar::separator {{ width: 8px; background: transparent; }}"
            f" QMenu {{ background: {t['bg1']}; border: 1px solid {t['line']};"
            f" border-radius: 8px; padding: 4px; }}"
            f" QMenu::item:selected {{ background: {t['bg2']}; color:"
            f" {t['accent']}; }}")
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, tb)

        def btn(name, tip, slot=None, menu=None):
            b = QToolButton(tb)
            b.setIcon(icons.icon(name))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            if menu is not None:
                b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                b.setMenu(menu)
            elif slot is not None:
                b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        def sep():
            tb.addSeparator()

        btn("sketch", "New sketch (N)",
            lambda checked=False: self.action_new_sketch())
        sep()
        m_create = QMenu(tb)
        m_create.addAction("E&xtrude profile… (X)", self._tb_extrude)
        m_create.addAction("&Revolve profile… (⇧R)", self._tb_revolve)
        btn("extrude", "Extrude — sweep a sketch profile into a solid",
            menu=m_create)
        m_pat = QMenu(tb)
        m_pat.addAction(self.act_linpat)
        m_pat.addAction(self.act_cirpat)
        m_pat.addAction(self.act_mirror)
        btn("pattern", "Pattern & mirror — replicate features", menu=m_pat)
        btn("cpattern", "Circular pattern…",
            lambda checked=False: self.action_circular_pattern())
        sep()
        m_mod = QMenu(tb)
        m_mod.addAction(self.act_fillet)
        m_mod.addAction(self.act_chamfer)
        btn("fillet", "Fillet — round every sharp edge of the body",
            menu=m_mod)

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
        m_file.addActions([self.act_new, self.act_open, self.act_save,
                           self.act_save_as])
        m_file.addSeparator()
        m_file.addAction(self.act_import)
        m_export = m_file.addMenu("&Export mesh")
        for ext in (".stl", ".3mf", ".obj", ".ply"):
            m_export.addAction(QAction(
                ext.upper().lstrip("."), self,
                triggered=lambda checked=False, e=ext: self.action_export(e)))
        m_file.addAction(QAction("Export &STEP (.step)…", self,
                                 triggered=self.action_export_step))
        m_file.addSeparator()
        m_file.addAction(QAction("Export &render (PNG)…", self,
                                 triggered=lambda checked=False: self.action_export_render()))
        m_file.addSeparator()
        m_file.addAction(QAction("E&xit", self, shortcut=QKeySequence.Quit,
                                 triggered=self.close))

        m_sk = self.menuBar().addMenu("S&ketch")
        self.act_new_sketch = QAction("&New sketch", self, shortcut="N",
                                      triggered=lambda checked=False: self.action_new_sketch())
        self.act_extrude = QAction("&Extrude profile…", self, shortcut="X",
                                   triggered=lambda: self.sketch.finish())
        self.act_revolve = QAction("&Revolve profile…", self, shortcut="Shift+R",
                                   triggered=lambda: self.sketch.finish(revolve=True))
        m_sk.addActions([self.act_new_sketch, self.act_extrude,
                         self.act_revolve])

        m_cr = self.menuBar().addMenu("C&reate")
        self.act_linpat = QAction("&Linear pattern…", self,
                                  triggered=lambda checked=False: self.action_linear_pattern())
        self.act_cirpat = QAction("C&ircular pattern…", self,
                                  triggered=lambda checked=False: self.action_circular_pattern())
        self.act_mirror = QAction("&Mirror…", self,
                                  triggered=lambda checked=False: self.action_mirror())
        m_cr.addActions([self.act_linpat, self.act_cirpat, self.act_mirror])

        m_mo = self.menuBar().addMenu("Mo&dify")
        self.act_fillet = QAction("&Fillet body edges…", self,
                                  triggered=lambda checked=False: self._body_fillet(False))
        self.act_chamfer = QAction("C&hamfer body edges…", self,
                                   triggered=lambda checked=False: self._body_fillet(True))
        m_mo.addActions([self.act_fillet, self.act_chamfer])

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
        elif kind == "sketch":
            self._feature_activated(self.doc.features[arg])

    def _feature_activated(self, feature):
        if (isinstance(feature, (ExtrudeFeature, RevolveFeature))
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
        sketchy = (isinstance(feature, (ExtrudeFeature, RevolveFeature))
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
        menu.addAction("Rename…", lambda: self._rename_feature(feature))
        menu.addSeparator()
        menu.addAction("Unsuppress" if feature.suppressed else "Suppress",
                       lambda: self._toggle_suppress(feature))
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

    def _toggle_suppress(self, feature):
        self._capture()
        feature.suppressed = not feature.suppressed
        self.doc.dirty = True
        self.recompute()
        verb = "Suppressed" if feature.suppressed else "Unsuppressed"
        self.status.showMessage(f"{verb} {feature.name}", 4000)

    def _set_distance(self, feature):
        val, ok = QInputDialog.getDouble(self, "Extrude distance",
                                         "Height (mm):", feature.height,
                                         0.01, 1e5, 3)
        if not ok or abs(val - feature.height) < 1e-12:
            return
        self._capture()
        feature.height = float(val)
        self.doc.dirty = True
        self.recompute()
        self.status.showMessage(f"{feature.name}: height {val:g} mm", 4000)

    def _set_corner(self, feature, kind: str):
        """Round (fillet) or cut (chamfer) the extrusion's vertical edges.
        The two are mutually exclusive; 0 clears."""
        cur = getattr(feature, kind)
        title = "Fillet vertical edges" if kind == "fillet" \
            else "Chamfer vertical edges"
        val, ok = QInputDialog.getDouble(self, title, "Size (mm, 0 = none):",
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
        val, ok = QInputDialog.getDouble(self, "Revolve angle",
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
        name, ok = QInputDialog.getText(self, "Rename feature", "Name:",
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

    def action_new_sketch(self, plane: str = "XY"):
        if self.doc is None or not self._discard_guard():
            return
        model = SketchModel(plane=plane)
        model.name = self._next_sketch_name()
        self._begin_sketch(model)
        self.status.showMessage(f"Sketching on {plane} — R rect · L line · C circle · "
                                "O slot · A arc · H/V/F/D/P/Q/T/I constraints · "
                                "K construction · X extrude · Esc select")

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
            self._update_sketch_features(sid, profiles, payload)
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
            angle, ok = QInputDialog.getDouble(
                self, "Revolve", "Angle (degrees):", 360.0, 1.0, 360.0, 1)
            if not ok:
                return
        else:
            height, ok = QInputDialog.getDouble(
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

    def _update_sketch_features(self, sid, profiles, payload):
        """Re-edit: swap profiles in the features born from this sketch,
        keeping each one's height/angle; add/remove features to match."""
        group = [f for f in self.doc.features
                 if isinstance(f, (ExtrudeFeature, RevolveFeature))
                 and f.sid == sid]
        if not group:
            return
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
                            ("slot", "Slot"), ("arc", "Arc")):
            b = QPushButton(label, checkable=True,
                            clicked=lambda checked, t=tool: self._pick_tool(t))
            b.setProperty("tb", True)
            bl.addWidget(b)
            self._tool_btns[tool] = b
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
        self.sketch = SketchCanvas()
        self.sketch.profiles_ready.connect(self._on_profiles)
        lay.addWidget(bar)
        lay.addWidget(self.sketch, 1)
        return page

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
        self._update_status()
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

    def _update_title(self):
        name = self.file_path.name if self.file_path else (
            (self.doc.title if self.doc else "Untitled") + ("" if not self.doc or not self.doc.dirty else " •"))
        self.setWindowTitle(f"{name} — Tracer Studio")

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

    def action_open(self):
        start = str(self.file_path.parent if self.file_path else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open document", start,
            "Tracer Studio document (*.tracer);;Legacy Forma document (*.forma)")
        if not path:
            return
        try:
            doc = fio.load_document(path)
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self.new_document(doc)
        self.file_path = Path(path)
        self._update_title()
        self.status.showMessage(f"Opened {Path(path).name}", 5000)

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
        self._update_status()

    def _update_status(self):
        n = len(self.doc.features) if self.doc else 0
        vol = ""
        if self.doc and self.doc.result is not None:
            vol = f" · volume {self.doc.result.volume:,.1f} mm³"
        self.status.showMessage(f"{self.doc.title if self.doc else ''}"
                                f" — {n} feature{'s' if n != 1 else ''}{vol} · units mm")
        self._update_title()

    # ---- slots ---------------------------------------------------------------
    def action_new(self):
        self.new_document()

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
                                      BodyFilletFeature))
                and not f.suppressed]

    def action_circular_pattern(self):
        if self.doc is None:
            return
        cands = self._pattern_candidates()
        if not cands:
            QMessageBox.information(self, "Nothing to pattern",
                                    "Create a feature first.")
            return
        names = [f.name for f in cands]
        name, ok = QInputDialog.getItem(self, "Circular pattern",
                                        "Feature to pattern:", names, 0, False)
        if not ok:
            return
        src = cands[names.index(name)]
        cx, ok = QInputDialog.getDouble(self, "Circular pattern",
                                        "Center X (mm):", 0.0, -1e5, 1e5, 2)
        if not ok:
            return
        cy, ok = QInputDialog.getDouble(self, "Circular pattern",
                                        "Center Y (mm):", 0.0, -1e5, 1e5, 2)
        if not ok:
            return
        ang, ok = QInputDialog.getDouble(self, "Circular pattern",
                                         "Angle (deg):", 360.0, -360.0, 360.0, 1)
        if not ok:
            return
        count, ok = QInputDialog.getInt(self, "Circular pattern",
                                        "Occurrences:", 6, 2, 500, 1)
        if not ok:
            return
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
        name, ok = QInputDialog.getItem(self, "Linear pattern",
                                        "Feature to pattern:", names, 0, False)
        if not ok:
            return
        src = cands[names.index(name)]
        dx, ok = QInputDialog.getDouble(self, "Linear pattern",
                                        "X spacing (mm):", 10.0, -1e5, 1e5, 3)
        if not ok:
            return
        dy, ok = QInputDialog.getDouble(self, "Linear pattern",
                                        "Y spacing (mm):", 0.0, -1e5, 1e5, 3)
        if not ok:
            return
        dz, ok = QInputDialog.getDouble(self, "Linear pattern",
                                        "Z spacing (mm):", 0.0, -1e5, 1e5, 3)
        if not ok:
            return
        count, ok = QInputDialog.getInt(self, "Linear pattern",
                                        "Occurrences:", 3, 2, 500, 1)
        if not ok:
            return
        self._capture()
        self.doc.add_linear_pattern(f"Pattern of {src.name}", src,
                                    (dx, dy, dz), count)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Patterned {src.name}: {count}x at ({dx:g}, {dy:g}, {dz:g}) mm", 6000)

    def _mirror_feature(self, src, plane=None):
        """Symmetric twin of ``src`` across a datum plane offset from the
        origin. Mirroring the part's mid-plane reproduces Fusion's most
        common mirror (e.g. a one-sided lug on a bracket)."""
        if plane is None:
            plane, ok = QInputDialog.getItem(
                self, "Mirror", "Mirror plane:", ["YZ", "XZ", "XY"], 0, False)
            if not ok:
                return
        else:
            plane = plane[:2]
        n = np.array(MirrorFeature.NORMALS[plane], float)
        # default the offset to the model's own mid-plane along the normal
        off = 0.0
        if self.doc.result is not None:
            bb = self.doc.result.bounding_box
            off = float((bb.mean(0) * n).sum())
        off, ok = QInputDialog.getDouble(self, "Mirror",
                                         "Plane offset (mm):", off,
                                         -1e6, 1e6, 2)
        if not ok:
            return
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
        name, ok = QInputDialog.getItem(self, "Mirror", "Feature to mirror:",
                                        names, 0, False)
        if not ok:
            return
        self._mirror_feature(cands[names.index(name)])

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
        size, ok = QInputDialog.getDouble(
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
        val, ok = QInputDialog.getDouble(self, kind, "Size (mm):",
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
        ev.accept()

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
