"""Left rail: feature tree + properties stub. M2 grows the properties
panel into a live editor; keeping it a label now is honest, not lazy.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QLabel, QVBoxLayout,
                               QTabWidget, QWidget, QFrame)

from ..core import units
from ..core.document import (BodyFilletFeature, CircularPatternFeature,
                             CombineFeature,
                             Document, ExtrudeFeature, GeometricPatternFeature,
                             HoleFeature,
                             ImportedFeature, LinearPatternFeature,
                             MoveFeature, ScaleFeature,
                             PathPatternFeature, RotateFeature, SplitFeature,
                             MirrorFeature, PrimitiveFeature, RevolveFeature,
                             ShellFeature, SweepFeature, LoftFeature,
                             ThickenFeature,
                             ThreadFeature)
from .theme import DARK

_OP_GLYPH = {"union": "+", "subtract": "−", "intersect": "∩"}


def _sketch_label(sk: dict) -> str:
    """'✎ Sketch1 (fully constrained)' — Fusion appends the constraint
    state to browser sketches (M73), and we can honestly say it: the
    same LM solver the editor speaks with answers from the stored
    payload.  Tiny sketches, tiny solves."""
    name = sk.get("name", "Sketch")
    try:
        from tracer.core.sketch.model import model_from_dict
        m = model_from_dict(sk)
        s = m.sketch
        if not (s.points or s.lines or s.circles or s.arcs):
            return f"\u270e {name}"
        r = m.solve()
    except Exception:
        return f"\u270e {name}"
    if not r.converged:
        state = " (\u26a0 conflicting constraints)"
    elif r.dof == 0:
        state = " (fully constrained)"
    else:
        state = " (under-constrained)"
    return f"\u270e {name}{state}"


class FeatureTree(QTreeWidget):
    feature_menu = Signal(object, object)   # Feature, global QPoint
    cplane_menu = Signal(str, object)       # plane name, global QPoint
    caxis_menu = Signal(str, object)        # M125 work axis, same grammar
    body_menu = Signal(object, object)        # body name, global QPoint
    feature_delete = Signal(object)         # Feature (Del key, M72)
    feature_rename = Signal(object)         # Feature (F2 key, M72)

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
        elif role and role[0] == "caxis":
            self.caxis_menu.emit(role[1], self.viewport().mapToGlobal(pos))
        elif role and role[0] == "body":
            self.body_menu.emit(role[1], self.viewport().mapToGlobal(pos))

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

        # ---- Bodies (n) ▸ each body ▸ its own features (+ nested sketches)
        # M104: the folder stopped being theatre — one node per real body,
        # BOLD is the active one, grey carries the hidden-by-bulb truth.
        feats = list(self._doc.features)
        listed = self._doc.body_list()
        names = [b["name"] for b in listed] or (["Body 1"] if feats else [])
        bodies = QTreeWidgetItem([f"Bodies ({len(names)})"])
        bodies.setData(0, Qt.UserRole, ("folder", "bodies"))
        root.addChild(bodies)
        body_nodes: dict = {}
        for nm in names:
            entry = next((b for b in listed if b["name"] == nm), None)
            vis = True if entry is None else bool(entry.get("visible", True))
            mat = ((entry or {}).get("appearance") or {}).get("name")
            tag = f"  \u00b7 {mat}" if mat else ""   # painted → name it
            body_item = QTreeWidgetItem(
                [("\u25a3 " + nm + tag) if vis
                 else f"\u25a3 {nm}{tag}  (hidden)"])
            body_item.setData(0, Qt.UserRole, ("body", nm))
            if self._doc.active_body == nm:
                fnt = body_item.font(0)
                fnt.setBold(True)
                body_item.setFont(0, fnt)
            if not vis:
                body_item.setForeground(0, QColor(DARK["fg_faint"]))
            bodies.addChild(body_item)
            body_item.setExpanded(True)
            body_nodes[nm] = body_item
        if names:
            bodies.setExpanded(True)
        default = names[0] if names else "Body 1"
        for i, f in enumerate(feats):
            fillet = isinstance(f, BodyFilletFeature)
            glyph = ("\u25cb" if f.suppressed else            # suppressed wins
                     "\u25d0" if fillet else                  # body op, no boolean
                     _OP_GLYPH.get(f.op, f.op))
            kind = ("\u21bb" if isinstance(f, RevolveFeature)
                    else "\u2300" if isinstance(f, HoleFeature)
                    else "\u25a4" if isinstance(f, ShellFeature)
                    else "\u2702" if isinstance(f, SplitFeature)  # trim
                    else "\u2725" if isinstance(f, MoveFeature)   # move
                    else "\u27f3" if isinstance(f, RotateFeature)  # spin
                    else "\u2295" if isinstance(f, CombineFeature)  # combine
                    else "\u223f" if isinstance(f, SweepFeature)
                    else "\u25ac" if isinstance(f, ThickenFeature)  # wall
                    else "\u25b3" if isinstance(f, LoftFeature)
                    else "\u25c8" if isinstance(f, ImportedFeature)
                    else "\u25e7" if isinstance(f, MirrorFeature)
                    else "\u2240" if isinstance(f, ThreadFeature)  # ≀ screw
                    else "\u2312" if fillet                    # arc = fillet/chamfer
                    else "\u29c9" if isinstance(f, (LinearPatternFeature,
                                                    CircularPatternFeature,
                                                    GeometricPatternFeature))
                    else "\u25f1" if isinstance(f, ScaleFeature)  # ◱
                    else "\u2935" if isinstance(f, PathPatternFeature)
                    else "\u25a1")
            label = (f"{glyph} {f.name}" if fillet
                     else f"{glyph} {kind} {f.name}")
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, ("feature", i))
            if f.suppressed:
                item.setForeground(0, QColor(DARK["fg_faint"]))
            parent = body_nodes.get(getattr(f, "body", None) or default)
            if parent is None:                      # orphaned by hand-edit
                parent = body_nodes[default]
            parent.addChild(item)
            if (isinstance(f, (ExtrudeFeature, RevolveFeature, HoleFeature))
                    and f.sketch):
                sk = QTreeWidgetItem([_sketch_label(f.sketch)])
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
            it = QTreeWidgetItem([_sketch_label(feats[i].sketch)])
            it.setData(0, Qt.UserRole, ("sketch", i))
            sketches.addChild(it)

        # ---- Construction (n): Fusion parks construction planes here ------
        # (M125: work axes joined the same bulb — one datum family)
        planes = getattr(self._doc, "planes", [])
        axes = getattr(self._doc, "axes", [])
        constr = QTreeWidgetItem([f"Construction ({len(planes) + len(axes)})"])
        constr.setData(0, Qt.UserRole, ("folder", "construction"))
        root.addChild(constr)
        for pl in planes:
            it = QTreeWidgetItem(["\u25ad " + pl["name"]])   # ▭
            it.setData(0, Qt.UserRole, ("cplane", pl["name"]))
            constr.addChild(it)
        for ax in axes:
            it = QTreeWidgetItem(["\u2225 " + ax["name"]])   # ∥
            it.setData(0, Qt.UserRole, ("caxis", ax["name"]))
            constr.addChild(it)
        constr.setExpanded(bool(planes or axes))

        # ---- Sheets (n): M96 drawings ride the tree like everything else --
        # (Fusion only shows the folder once drawings exist)
        sheets = getattr(self._doc, "drawings", [])
        if sheets:
            sh = QTreeWidgetItem([f"Sheets ({len(sheets)})"])
            sh.setData(0, Qt.UserRole, ("folder", "sheets"))
            root.addChild(sh)
            for i, g in enumerate(sheets):
                it = QTreeWidgetItem([g.get("name", f"Drawing{i + 1}")])
                it.setData(0, Qt.UserRole, ("sheet", i))
                sh.addChild(it)
            sh.setExpanded(True)
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

    def keyPressEvent(self, ev):
        """Fusion's browser key grammar (M72): Del removes the selected
        feature, F2 renames it — same paths as the context menu."""
        f = self.current_feature()
        if f is not None and ev.key() in (Qt.Key_Delete,
                                          Qt.Key_Backspace):
            self.feature_delete.emit(f)
            return
        if f is not None and ev.key() == Qt.Key_F2:
            self.feature_rename.emit(f)
            return
        super().keyPressEvent(ev)


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
        self.unit = "mm"

    def set_unit(self, unit: str):
        self.unit = unit if unit in units.LABEL else "mm"

    def show_stats(self, volume: float, area: float):
        """Whole-body numbers, Fusion-inspector style (no selection)."""
        self._body.setText(
            f"<b>Body</b><br>volume: {units.V(volume, self.unit)}<br>"
            f"surface area: {units.A(area, self.unit)}<br>"
            f"<span style='color:{DARK['fg_faint']}'>click a face to "
            "measure it; ctrl+click to measure between</span>")

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
            lines.append(f"height: {units.L(feature.height, self.unit)}")
            if feature.fillet > 0:
                lines.append("vertical fillet: "
                             + units.L(feature.fillet, self.unit))
            if feature.chamfer > 0:
                lines.append("vertical chamfer: "
                             + units.L(feature.chamfer, self.unit))
            if abs(feature.taper) > 1e-9:
                lines.append(f"taper: {feature.taper:+.1f}\u00b0")
            if feature.symmetric:
                lines.append("extent: symmetric")
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
            lines.append(f"diameter: Ø{units.L(2 * feature.radius, self.unit)}"
                         f" ({kind})")
            lines.append("depth: through all" if feature.through
                         else f"depth: {units.L(feature.depth, self.unit)}")
            if feature.thread_pitch > 0:
                lines.append(
                    f"threaded: pitch "
                    f"{units.L(feature.thread_pitch, self.unit)}, "
                    f"{units.L(feature.thread_len, self.unit)} long")
            if feature.cb_radius > feature.radius:
                lines.append(
                    f"counterbore: "
                    f"Ø{units.val(2 * feature.cb_radius, self.unit):g}"
                    f" × {units.L(feature.cb_depth, self.unit)} deep")
            if feature.cs_radius > feature.radius:
                lines.append(f"countersink: Ø{2 * feature.cs_radius:g} at "
                             f"{feature.cs_angle:g}°")
        elif isinstance(feature, ThreadFeature):
            minor = 2 * (feature.radius - feature.pitch / 2)
            lines.append("external thread — pitch "
                         + units.L(feature.pitch, self.unit))
            lines.append(f"major: Ø{units.L(2 * feature.radius, self.unit)}, "
                         f"minor: Ø{units.L(minor, self.unit)}")
            lines.append(f"length: {units.L(feature.length, self.unit)} "
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
                             f"area {units.A(abs(a), self.unit, 0)}")
            if feature.closed:
                lines.append("ring loft (closed loop)")
        elif isinstance(feature, SweepFeature):
            import math as _m
            pts = feature.path
            length = sum(_m.dist(pts[i], pts[i + 1])
                         for i in range(len(pts) - 1)) if len(pts) > 1 else 0.0
            lines.append(f"profile: Ø{2 * feature.radius:g} circle")
            lines.append(f"path: {units.val(length, self.unit):.1f} "
                         f"{units.LABEL[self.unit]} "
                         + ("closed ring" if feature.closed else "open"))
        elif isinstance(feature, ThickenFeature):
            import math as _m
            total = 0.0
            for p in feature.paths:
                total += sum(_m.dist(p[i], p[i + 1])
                             for i in range(len(p) - 1)) if len(p) > 1 else 0
            lines.append(f"wall: {units.A(feature.thickness, self.unit)} "
                         f"thick × {units.A(feature.depth, self.unit)} deep")
            lines.append(f"chains: {len(feature.paths)} "
                         f"({units.val(total, self.unit):.1f} "
                         f"{units.LABEL[self.unit]} total)")
        elif isinstance(feature, ShellFeature):
            lines.append("wall thickness: "
                         + units.L(feature.thickness, self.unit))
            lines.append(f"faces removed: {len(feature.openings)}")
        elif isinstance(feature, PrimitiveFeature):
            lines.append(f"kind: {feature.kind}")
            for k, v in feature.dims.items():
                lines.append(f"{k}: {units.L(v, self.unit)}")
        elif isinstance(feature, ImportedFeature):
            lines.append(f"imported mesh: {len(feature.faces)} triangles")
        elif isinstance(feature, MirrorFeature):
            lines.append(f"mirror across {feature.plane}"
                         f" @ {units.L(feature.offset, self.unit)}")
        elif isinstance(feature, BodyFilletFeature):
            kind = "chamfer" if feature.chamfer else "fillet"
            lines.append(f"{kind}: {units.L(feature.radius, self.unit)}"
                         " on all sharp edges")
            if feature.n_rims:
                lines.append(f"circular rims rounded: {feature.n_rims}")
            baked = len(feature.res_faces)
            lines.append(f"baked triangles: {baked}" if baked
                         else "not yet computed")
        elif isinstance(feature, LinearPatternFeature):
            lines.append(f"pattern: {feature.count}x at "
                         f"({units.val(feature.vector[0], self.unit):g}, "
                         f"{units.val(feature.vector[1], self.unit):g}, "
                         f"{units.val(feature.vector[2], self.unit):g}) "
                         f"{units.LABEL[self.unit]}")
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
                         f"{units.L(length, self.unit)} path")
        elif isinstance(feature, SplitFeature):
            n = np.abs(np.asarray(feature.normal, float))
            ax = int(n.argmax())
            lines.append(f"split plane \u2702 through "
                         f"({'xyz'[ax]}="
                         f"{units.val(feature.origin[ax], self.unit):g} "
                         f"{units.LABEL[self.unit]})")
            lines.append("kept side: "
                         + ("flipped" if feature.flip else "default"))
        elif isinstance(feature, MoveFeature):
            x, y, z = (float(v) for v in feature.vec)
            lines.append(f"translate \u2725 ({units.val(x, self.unit):+g}, "
                         f"{units.val(y, self.unit):+g}, "
                         f"{units.val(z, self.unit):+g}) "
                         f"{units.LABEL[self.unit]}")
            if feature.copy:
                lines.append("copy: twin joined")
        elif isinstance(feature, RotateFeature):
            ax = "xyz"[int(np.argmax(np.abs(np.asarray(
                feature.axis, float))))]
            lines.append(f"rotate \u27f3 {feature.angle_deg:+.1f}\u00b0 "
                         f"about {ax.upper()} through "
                         f"({feature.center[0]:g}, {feature.center[1]:g}, "
                         f"{feature.center[2]:g})")
            if feature.copy:
                lines.append("copy: twin joined")
        elif isinstance(feature, CombineFeature):
            d = feature.dims
            shape = {"union": "join", "subtract": "cut",
                     "intersect": "intersect"}.get(feature.op,
                                                   feature.op)
            if feature.tool == "box":
                size = (f"{units.L(d.get('dx', 0), self.unit)} \u00d7 "
                        f"{units.L(d.get('dy', 0), self.unit)} \u00d7 "
                        f"{units.L(d.get('dz', 0), self.unit)}")
            elif feature.tool == "cylinder":
                size = (f"\u00d8{units.L(2 * d.get('radius', 0), self.unit)}"
                        f" \u00d7 {units.L(d.get('height', 0), self.unit)}")
            elif feature.tool == "cone":
                size = (f"\u00d8{units.L(2 * d.get('radius_bottom', 0), self.unit)}"
                        f" \u2192 \u00d8{units.L(2 * d.get('radius_top', 0), self.unit)}"
                        f" \u00d7 {units.L(d.get('height', 0), self.unit)}")
            elif feature.tool == "torus":
                size = (f"ring \u00d8"
                        f"{units.L(2 * d.get('major', 0), self.unit)}"
                        f" \u00d7 tube \u00d8"
                        f"{units.L(2 * d.get('minor', 0), self.unit)}")
            else:
                size = f"\u00d8{units.L(2 * d.get('radius', 0), self.unit)}"
            lines.append(f"combine \u2295 {shape} a {feature.tool}")
            lines.append(f"tool: {size}")
            lines.append("tool centre: "
                         f"({feature.center[0]:g}, "
                         f"{feature.center[1]:g}, "
                         f"{feature.center[2]:g}) mm")
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
