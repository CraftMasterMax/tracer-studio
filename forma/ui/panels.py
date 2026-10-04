"""Left rail: feature tree + properties stub. M2 grows the properties
panel into a live editor; keeping it a label now is honest, not lazy.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QLabel, QVBoxLayout,
                               QTabWidget, QWidget, QFrame)

from ..core.document import (Document, ExtrudeFeature, ImportedFeature,
                             PrimitiveFeature, RevolveFeature)

_OP_GLYPH = {"union": "+", "subtract": "−", "intersect": "∩"}


class FeatureTree(QTreeWidget):
    feature_menu = Signal(object, object)   # Feature, global QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setUniformRowHeights(True)
        self.setIndentation(14)
        self._doc: Document | None = None
        self.feature_selected = None  # callback(feature|None)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def _show_menu(self, pos):
        it = self.itemAt(pos)
        role = it.data(0, Qt.UserRole) if it else None
        if role and role[0] in ("feature", "sketch") and self._doc:
            idx = role[1]
            if idx < len(self._doc.features):
                self.feature_menu.emit(self._doc.features[idx],
                                       self.viewport().mapToGlobal(pos))

    def set_document(self, doc: Document):
        self._doc = doc
        self.reload()

    def reload(self):
        self.clear()
        if not self._doc:
            return
        root = QTreeWidgetItem([self._doc.title])
        root.setFlags(root.flags() & ~Qt.ItemIsSelectable)
        self.addTopLevelItem(root)
        origin = QTreeWidgetItem(["Origin"])
        origin.setData(0, Qt.UserRole, ("origin", None))
        root.addChild(origin)
        for pl in ("XY-Plane", "XZ-Plane", "YZ-Plane"):
            it = QTreeWidgetItem([pl])
            it.setData(0, Qt.UserRole, ("plane", pl[:2]))
            origin.addChild(it)
        origin.setExpanded(False)
        for i, f in enumerate(self._doc.features):
            glyph = "\u25cb" if f.suppressed else _OP_GLYPH.get(f.op, f.op)
            kind = ("\u21bb" if isinstance(f, RevolveFeature)
                    else "\u25c8" if isinstance(f, ImportedFeature)
                    else "\u25a1")
            item = QTreeWidgetItem([f"{glyph} {kind} {f.name}"])
            item.setData(0, Qt.UserRole, ("feature", i))
            if f.suppressed:
                item.setForeground(0, QColor("#5f6672"))
            root.addChild(item)
            if (isinstance(f, (ExtrudeFeature, RevolveFeature))
                    and f.sketch):
                sk = QTreeWidgetItem([f"\u270e {f.sketch.get('name', 'Sketch')}"])
                sk.setData(0, Qt.UserRole, ("sketch", i))
                item.addChild(sk)
                item.setExpanded(True)
        root.setExpanded(True)
        self.setCurrentItem(None)

    def current_feature(self):
        it = self.currentItem()
        if not it:
            return None
        role = it.data(0, Qt.UserRole)
        if role and role[0] in ("feature", "sketch") and self._doc:
            idx = role[1]
            if idx < len(self._doc.features):
                return self._doc.features[idx]
        return None


class PropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self._title = QLabel("Properties")
        self._title.setObjectName("docTitle")
        self._body = QLabel("Select a feature to inspect it.")
        self._body.setObjectName("dim")
        self._body.setWordWrap(True)
        lay.addWidget(self._title)
        lay.addWidget(self._body)
        lay.addStretch(1)

    def show_feature(self, feature):
        if feature is None:
            self._body.setText("Select a feature to inspect it.")
            return
        lines = [f"<b>{feature.name}</b>", f"operation: {feature.op}"]
        if isinstance(feature, ExtrudeFeature):
            lines.append(f"height: {feature.height:g} mm")
            if feature.fillet > 0:
                lines.append(f"vertical fillet: {feature.fillet:g} mm")
            if feature.chamfer > 0:
                lines.append(f"vertical chamfer: {feature.chamfer:g} mm")
            lines.append(f"outer vertices: {len(np.asarray(feature.outer))}")
            lines.append(f"holes: {len(feature.holes)}")
        elif isinstance(feature, RevolveFeature):
            lines.append(f"angle: {feature.angle:g}°")
            lines.append(f"outer vertices: {len(np.asarray(feature.outer))}")
            lines.append(f"holes: {len(feature.holes)}")
        elif isinstance(feature, PrimitiveFeature):
            lines.append(f"kind: {feature.kind}")
            for k, v in feature.dims.items():
                lines.append(f"{k}: {v:g} mm")
        elif isinstance(feature, ImportedFeature):
            lines.append(f"imported mesh: {len(feature.faces)} triangles")
        px, py, pz = feature.placement
        lines.append(f"placed at ({px:g}, {py:g}, {pz:g})")
        self._body.setText("<br>".join(lines))


class LeftRail(QTabWidget):
    """Fusion-style left dock: tabbed Browser / Shortcuts panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .shortcuts import ShortcutsPage
        model = QWidget()
        lay = QVBoxLayout(model)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self.tree = FeatureTree()
        self.props = PropertiesPanel()
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: palette(mid);")
        lay.addWidget(self.tree, 3)
        lay.addWidget(line)
        lay.addWidget(self.props, 1)
        self.addTab(model, "Browser")
        self._keys = ShortcutsPage()
        self.addTab(self._keys, "Shortcuts")
        self.setObjectName("leftRail")

    def show_shortcuts(self):
        self.setCurrentIndex(1)

    def show_browser(self):
        self.setCurrentIndex(0)
