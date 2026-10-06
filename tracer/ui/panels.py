"""Left rail: feature tree + properties stub. M2 grows the properties
panel into a live editor; keeping it a label now is honest, not lazy.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QLabel, QVBoxLayout,
                               QTabWidget, QWidget, QFrame)

from ..core.document import (BodyFilletFeature, CircularPatternFeature,
                             Document, ExtrudeFeature, HoleFeature,
                             ImportedFeature, LinearPatternFeature,
                             PathPatternFeature,
                             MirrorFeature, PrimitiveFeature, RevolveFeature,
                             ShellFeature, SweepFeature, LoftFeature,
                             ThreadFeature)
from .theme import DARK

_OP_GLYPH = {"union": "+", "subtract": "−", "intersect": "∩"}


class FeatureTree(QTreeWidget):
    feature_menu = Signal(object, object)   # Feature, global QPoint
    cplane_menu = Signal(str, object)       # plane name, global QPoint
    body_menu = Signal(object)              # global QPoint

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
        elif role and role[0] == "cplane":
            self.cplane_menu.emit(role[1], self.viewport().mapToGlobal(pos))
        elif role and role[0] == "body":
            self.body_menu.emit(self.viewport().mapToGlobal(pos))

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

        # ---- Origin: point + axes + planes, like Fusion's folder ----------
        origin = QTreeWidgetItem(["Origin"])
        origin.setData(0, Qt.UserRole, ("folder", "origin"))
        root.addChild(origin)
        op = QTreeWidgetItem(["\u2316 Origin"])            # ⌖ origin point
        op.setData(0, Qt.UserRole, ("originpt", None))
        origin.addChild(op)
        for lab, key in (("X Axis", "axis_x"), ("Y Axis", "axis_y"),
                         ("Z Axis", "axis_z")):
            it = QTreeWidgetItem(["\u2014 " + lab])        # — axis
            it.setForeground(0, QColor.fromRgbF(*DARK[key]))
            it.setData(0, Qt.UserRole, ("axis", lab[0]))
            origin.addChild(it)
        for pl in ("XY-Plane", "XZ-Plane", "YZ-Plane"):
            it = QTreeWidgetItem(["\u25ad " + pl])         # ▭
            it.setData(0, Qt.UserRole, ("plane", pl[:2]))
            origin.addChild(it)
        origin.setExpanded(False)

        # ---- Bodies (1) ▸ Body 1 ▸ features (+ nested sketches) -----------
        feats = list(self._doc.features)
        bodies = QTreeWidgetItem([f"Bodies ({1 if feats else 0})"])
        bodies.setData(0, Qt.UserRole, ("folder", "bodies"))
        root.addChild(bodies)
        parent = bodies
        if feats:
            body_item = QTreeWidgetItem(["\u25a3 Body 1"])  # ▣
            body_item.setData(0, Qt.UserRole, ("body", None))
            bodies.addChild(body_item)
            bodies.setExpanded(True)
            body_item.setExpanded(True)
            parent = body_item
        for i, f in enumerate(feats):
            fillet = isinstance(f, BodyFilletFeature)
            glyph = ("\u25cb" if f.suppressed else            # suppressed wins
                     "\u25d0" if fillet else                  # body op, no boolean
                     _OP_GLYPH.get(f.op, f.op))
            kind = ("\u21bb" if isinstance(f, RevolveFeature)
                    else "\u2300" if isinstance(f, HoleFeature)
                    else "\u25a4" if isinstance(f, ShellFeature)
                    else "\u223f" if isinstance(f, SweepFeature)
                    else "\u25b3" if isinstance(f, LoftFeature)
                    else "\u25c8" if isinstance(f, ImportedFeature)
                    else "\u25e7" if isinstance(f, MirrorFeature)
                    else "\u2240" if isinstance(f, ThreadFeature)  # ≀ screw
                    else "\u2312" if fillet                    # arc = fillet/chamfer
                    else "\u29c9" if isinstance(f, (LinearPatternFeature,
                                                    CircularPatternFeature))
                    else "\u2935" if isinstance(f, PathPatternFeature)
                    else "\u25a1")
            label = (f"{glyph} {f.name}" if fillet
                     else f"{glyph} {kind} {f.name}")
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, ("feature", i))
            if f.suppressed:
                item.setForeground(0, QColor("#767e8a"))
            parent.addChild(item)
            if (isinstance(f, (ExtrudeFeature, RevolveFeature, HoleFeature))
                    and f.sketch):
                sk = QTreeWidgetItem([f"\u270e {f.sketch.get('name', 'Sketch')}"])
                sk.setData(0, Qt.UserRole, ("sketch", i))
                item.addChild(sk)
                item.setExpanded(True)

        # ---- Sketches (n): the same sketches listed like in Fusion --------
        sketchers = [i for i, f in enumerate(feats)
                     if isinstance(f, (ExtrudeFeature, RevolveFeature,
                                       HoleFeature)) and f.sketch]
        sketches = QTreeWidgetItem([f"Sketches ({len(sketchers)})"])
        sketches.setData(0, Qt.UserRole, ("folder", "sketches"))
        root.addChild(sketches)
        for i in sketchers:
            it = QTreeWidgetItem([f"\u270e {feats[i].sketch.get('name', 'Sketch')}"])
            it.setData(0, Qt.UserRole, ("sketch", i))
            sketches.addChild(it)

        # ---- Construction (n): Fusion parks construction planes here ------
        planes = getattr(self._doc, "planes", [])
        constr = QTreeWidgetItem([f"Construction ({len(planes)})"])
        constr.setData(0, Qt.UserRole, ("folder", "construction"))
        root.addChild(constr)
        for pl in planes:
            it = QTreeWidgetItem(["\u25ad " + pl["name"]])
            it.setData(0, Qt.UserRole, ("cplane", pl["name"]))
            constr.addChild(it)
        constr.setExpanded(bool(planes))
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

    def show_stats(self, volume: float, area: float):
        """Whole-body numbers, Fusion-inspector style (no selection)."""
        self._body.setText(
            f"<b>Body</b><br>volume: {volume:,.1f} mm³<br>"
            f"surface area: {area:,.1f} mm²<br>"
            "<span style='color:#767e8a'>click a face to measure it; "
            "click two to measure between</span>")

    def show_feature(self, feature):
        if feature is None:
            self._body.setText("Select a feature to inspect it.")
            return
        if isinstance(feature, BodyFilletFeature):
            lines = [f"<b>{feature.name}</b>",
                     "operation: fillet body edges (OpenCascade)"]
        else:
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
        elif isinstance(feature, HoleFeature):
            kind = ("counterbore" if feature.cb_radius > feature.radius else
                    "countersink" if feature.cs_radius > feature.radius
                    else "simple")
            lines.append(f"diameter: Ø{2 * feature.radius:g} mm ({kind})")
            lines.append("depth: through all" if feature.through
                         else f"depth: {feature.depth:g} mm")
            if feature.thread_pitch > 0:
                lines.append(f"threaded: pitch {feature.thread_pitch:g} mm, "
                             f"{feature.thread_len:g} mm long")
            if feature.cb_radius > feature.radius:
                lines.append(f"counterbore: Ø{2 * feature.cb_radius:g} × "
                             f"{feature.cb_depth:g} mm deep")
            if feature.cs_radius > feature.radius:
                lines.append(f"countersink: Ø{2 * feature.cs_radius:g} at "
                             f"{feature.cs_angle:g}°")
        elif isinstance(feature, ThreadFeature):
            minor = 2 * (feature.radius - feature.pitch / 2)
            lines.append(f"external thread — pitch {feature.pitch:g} mm")
            lines.append(f"major: Ø{2 * feature.radius:g} mm, "
                         f"minor: Ø{minor:g} mm")
            lines.append(f"length: {feature.length:g} mm "
                         f"(~{int(feature.length / feature.pitch)} turns)")
        elif isinstance(feature, LoftFeature):
            lines.append(f"loft through {len(feature.sections)} profile(s)")
            for i, sec in enumerate(feature.sections):
                pts = sec["outer"]
                a = 0.5 * sum(
                    pts[k][0] * pts[(k + 1) % len(pts)][1]
                    - pts[(k + 1) % len(pts)][0] * pts[k][1]
                    for k in range(len(pts)))
                lines.append(f"profile {i + 1}: {len(pts)} pts, "
                             f"area {abs(a):,.0f} mm\u00b2")
            if feature.closed:
                lines.append("ring loft (closed loop)")
        elif isinstance(feature, SweepFeature):
            import math as _m
            pts = feature.path
            length = sum(_m.dist(pts[i], pts[i + 1])
                         for i in range(len(pts) - 1)) if len(pts) > 1 else 0.0
            lines.append(f"profile: Ø{2 * feature.radius:g} circle")
            lines.append(f"path: {length:.1f} mm "
                         + ("closed ring" if feature.closed else "open"))
        elif isinstance(feature, ShellFeature):
            lines.append(f"wall thickness: {feature.thickness:g} mm")
            lines.append(f"faces removed: {len(feature.openings)}")
        elif isinstance(feature, PrimitiveFeature):
            lines.append(f"kind: {feature.kind}")
            for k, v in feature.dims.items():
                lines.append(f"{k}: {v:g} mm")
        elif isinstance(feature, ImportedFeature):
            lines.append(f"imported mesh: {len(feature.faces)} triangles")
        elif isinstance(feature, MirrorFeature):
            lines.append(f"mirror across {feature.plane}"
                         f" @ {feature.offset:g} mm")
        elif isinstance(feature, BodyFilletFeature):
            kind = "chamfer" if feature.chamfer else "fillet"
            lines.append(f"{kind}: {feature.radius:g} mm on all sharp edges")
            if feature.n_rims:
                lines.append(f"circular rims rounded: {feature.n_rims}")
            baked = len(feature.res_faces)
            lines.append(f"baked triangles: {baked}" if baked
                         else "not yet computed")
        elif isinstance(feature, LinearPatternFeature):
            lines.append(f"pattern: {feature.count}x at "
                         f"({feature.vector[0]:g}, {feature.vector[1]:g}, "
                         f"{feature.vector[2]:g}) mm")
        elif isinstance(feature, CircularPatternFeature):
            lines.append(f"pattern: {feature.count}x over {feature.angle:g}° "
                         f"about ({feature.center[0]:g}, {feature.center[1]:g})")
        elif isinstance(feature, PathPatternFeature):
            import numpy as _np
            from ..core.sweep import sample_polyline
            pts = sample_polyline(feature.path, feature.count)
            span = _np.asarray(pts)
            length = sum(float(_np.linalg.norm(span[i + 1] - span[i]))
                         for i in range(len(span) - 1))
            lines.append(f"pattern: {feature.count} copies walking a "
                         f"{length:g} mm path")
        placement = getattr(feature, "placement", None)
        if placement is not None:                    # patterns have none
            px, py, pz = placement
            lines.append(f"placed at ({px:g}, {py:g}, {pz:g})")
        self._body.setText("<br>".join(lines))


class LeftRail(QTabWidget):
    """Fusion-style left dock: tabbed Browser / Shortcuts panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)          # values like "6,899.6 mm³"
        self.setMaximumWidth(480)          # must not wrap word-per-line
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
