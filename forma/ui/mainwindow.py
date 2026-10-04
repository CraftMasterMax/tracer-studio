"""Application shell: menus, status bar, document <-> viewport wiring."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout,
                               QInputDialog, QMainWindow, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core import io as fio
from ..core.document import Document, ExtrudeFeature
from ..core.sketch.model import SketchModel
from . import theme
from .renderer import SceneRenderer
from .panels import LeftRail
from .sketcheditor import SketchCanvas
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
        self.setWindowTitle("Forma")
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
        self.setCentralWidget(split)

        self._make_actions()
        self.status = self.statusBar()
        self.status.showMessage("Ready — F fit · G grid · E edges · 0/1/2/3 views")
        self.new_document(demo_document())

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
        self.act_import = QAction("&Import mesh…", self, triggered=self.action_import)
        m_export = m_file.addMenu("&Export mesh")
        for ext in (".stl", ".3mf", ".obj", ".ply"):
            m_export.addAction(QAction(
                ext.upper().lstrip("."), self,
                triggered=lambda checked=False, e=ext: self.action_export(e)))
        m_file.addActions([self.act_new, self.act_open, self.act_save,
                           self.act_save_as, self.act_import])
        m_file.addSeparator()
        m_file.addAction(QAction("E&xit", self, shortcut=QKeySequence.Quit,
                                 triggered=self.close))

        m_sk = self.menuBar().addMenu("S&ketch")
        m_sk.addAction(QAction("&New sketch", self, shortcut="N",
                               triggered=self.action_new_sketch))
        m_sk.addAction(QAction("&Extrude profile…", self, shortcut="X",
                               triggered=lambda: self.sketch.finish()))

        m_edit = self.menuBar().addMenu("&Edit")
        m_edit.addAction(QAction("&Undo", self, shortcut=QKeySequence.Undo,
                                 triggered=self.undo))
        m_edit.addAction(QAction("&Redo", self, shortcut="Ctrl+Shift+Z",
                                 triggered=self.redo))

        m_view = self.menuBar().addMenu("&View")
        for label, key, view in (("Front", "1", "front"), ("Top", "2", "top"),
                                 ("Right", "3", "right"), ("Isometric", "0", "iso"),
                                 ("Fit view", "F", "fit")):
            m_view.addAction(QAction(
                label, self, shortcut=key,
                triggered=lambda checked=False, v=view: self.action_view(v)))
        m_view.addSeparator()
        m_view.addAction(QAction("Toggle grid", self, shortcut="G",
                                 triggered=self.action_toggle_grid))
        m_view.addAction(QAction("Toggle edges", self, shortcut="E",
                                 triggered=self.action_toggle_edges))

    # ---- sketching -----------------------------------------------------------
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
                            ("rect", "Rect"), ("circle", "Circle")):
            b = QPushButton(label, checkable=True,
                            clicked=lambda checked, t=tool: self._pick_tool(t))
            bl.addWidget(b)
            self._tool_btns[tool] = b
        bl.addStretch(1)
        done = QPushButton("Extrude profile…  (X)")
        done.clicked.connect(lambda: self.sketch.finish())
        bl.addWidget(done)
        self.sketch = SketchCanvas()
        self.sketch.profiles_ready.connect(self._on_profiles)
        lay.addWidget(bar)
        lay.addWidget(self.sketch, 1)
        return page

    def _pick_tool(self, tool: str):
        self.sketch.set_tool(tool)
        for t, b in self._tool_btns.items():
            b.setChecked(t == tool)

    def action_new_sketch(self):
        if self.doc is None:
            return
        if self.stack.currentWidget() is self._sketch_page and self.sketch.model \
                and (self.sketch.model.sketch.lines or self.sketch.model.sketch.circles):
            ans = QMessageBox.question(
                self, "Discard current sketch?",
                "You are sketching. Start a new sketch and discard?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans != QMessageBox.Yes:
                return
        model = SketchModel()
        model.name = f"Sketch{len(self.doc.features) + 1}"
        self.sketch.set_model(model)
        self.stack.setCurrentWidget(self._sketch_page)
        self._pick_tool("rect")     # most sketches start with a rectangle
        self.status.showMessage("Sketching: R rect · L line · C circle · H/V/F/D "
                                "constraints · X extrude · Esc select")

    def _on_profiles(self, profiles, name):
        height, ok = QInputDialog.getDouble(
            self, "Extrude", "Height (mm):", 5.0, 0.01, 1e5, 2)
        if not ok:
            return
        self._capture()
        for i, (outer, holes) in enumerate(profiles):
            tag = name if len(profiles) == 1 else f"{name} #{i + 1}"
            self.doc.add(ExtrudeFeature(name=tag, outer=np.asarray(outer),
                                        holes=[np.asarray(h) for h in holes],
                                        height=height, op="union"))
        self.stack.setCurrentWidget(self.viewport)
        self.recompute()
        self.viewport.refresh(fit=True)
        self.status.showMessage(
            f"Extruded {len(profiles)} region(s) from {name} by {height:g} mm", 6000)

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

    def undo(self):
        import json
        if not self._undo or self.doc is None:
            self.status.showMessage("Nothing to undo", 2500)
            return
        self._redo.append(json.dumps(self.doc.to_dict()))
        self.doc = Document.from_dict(json.loads(self._undo.pop()))
        self._adopt_doc()

    def redo(self):
        import json
        if not self._redo or self.doc is None:
            self.status.showMessage("Nothing to redo", 2500)
            return
        self._undo.append(json.dumps(self.doc.to_dict()))
        self.doc = Document.from_dict(json.loads(self._redo.pop()))
        self._adopt_doc()

    def _adopt_doc(self):
        self.rail.tree.set_document(self.doc)
        self.viewport.set_document(self.doc)
        self.viewport.refresh(fit=False)
        self._update_status()
    def new_document(self, doc: Document | None = None):
        self.doc = doc or Document("Untitled")
        self.file_path = None
        self._undo.clear()
        self._redo.clear()
        self.rail.tree.set_document(self.doc)
        self.viewport.set_document(self.doc)
        self._update_status()

    def _update_title(self):
        name = self.file_path.name if self.file_path else (
            (self.doc.title if self.doc else "Untitled") + ("" if not self.doc or not self.doc.dirty else " •"))
        self.setWindowTitle(f"{name} — Forma")

    def action_save(self, as_new: bool = False):
        if self.doc is None:
            return
        if self.file_path is None or as_new:
            start = str(self.file_path or (Path.home() / f"{self.doc.title}.forma"))
            path, _ = QFileDialog.getSaveFileName(
                self, "Save document", start, "Forma document (*.forma)")
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
        self._update_title()

    def action_open(self):
        start = str(self.file_path.parent if self.file_path else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open document", start, "Forma document (*.forma)")
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
        self.viewport.refresh()
        self.rail.tree.reload()
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

    def action_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import mesh", str(Path.home()),
            "Meshes (*.stl *.obj *.ply *.3mf *.glb *.gltf)")
        if not path:
            return
        try:
            solid = fio.import_mesh(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        self.viewport._r.clear_mesh()
        v, n, f = solid.to_render_arrays()
        self.viewport._r.set_mesh(v, n, f)
        self.viewport._bbox = solid.bounding_box
        self.viewport._r._grid_auto(solid.bounding_box)
        self.viewport._cam.fit(solid.bounding_box)
        self.viewport.update()
        self.status.showMessage(f"Imported {Path(path).name} (display only — "
                                "mesh becomes an editable feature in M3)", 8000)
