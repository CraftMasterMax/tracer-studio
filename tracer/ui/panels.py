"""Left rail: feature tree + properties stub. M2 grows the properties
panel into a live editor; keeping it a label now is honest, not lazy.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem, QLineEdit,
                               QLabel, QVBoxLayout,
                               QTabWidget, QWidget, QFrame)

from ..core import units
from ..core.document import (BodyFilletFeature, CircularPatternFeature,
                             CoilFeature, CombineFeature,
                             Document, ExtrudeFeature, GeometricPatternFeature,
                             HoleFeature,
                             ImportedFeature, LinearPatternFeature,
                             MoveFeature, ScaleFeature,
                             PathPatternFeature, RotateFeature, SplitFeature,
                             MirrorFeature, PrimitiveFeature, RevolveFeature,
                             ShellFeature, SweepFeature, LoftFeature,
                             ThickenFeature,
                             ThreadFeature)
from . import icons
from .theme import DARK

_OP_GLYPH = {"union": "+", "subtract": "−", "intersect": "∩"}


def _sketch_state(sk: dict) -> tuple:
    """('✎ Sketch1 (fully constrained)', True) — M73 banked the TEXT
    (Fusion appends the constraint state to browser sketches), M186 R3
    adds the documented RED LOCK beside it — and both voices come from
    ONE solve of the stored payload on purpose: the label and the lock
    are the same answer read once, they can never disagree. Tiny
    sketches, tiny solves.
    """
    name = sk.get("name", "Sketch")
    try:
        from tracer.core.sketch.model import model_from_dict
        m = model_from_dict(sk)
        s = m.sketch
        if not (s.points or s.lines or s.circles or s.arcs):
            return f"\u270e {name}", False
        r = m.solve()
    except Exception:
        return f"\u270e {name}", False
    if not r.converged:
        return f"\u270e {name} (\u26a0 conflicting constraints)", False
    if r.dof == 0:
        return f"\u270e {name} (fully constrained)", True
    return f"\u270e {name} (under-constrained)", False


def _paint_eye(p: QPainter, x: float, cy: float, hidden: bool):
    """M162 (FD3 LAW-1.1): the visibility eye, token-skinned —
    visible is the mid gray, hidden is the faint gray WITH the slash.
    Recorded state language: two grays plus the slash is the truth
    carrier (FD3 read the vendor's own wording, no hexes exist)."""
    p.setRenderHint(QPainter.Antialiasing)
    col = QColor(DARK["fg_faint"]) if hidden else QColor(DARK["fg_dim"])
    pen = QPen(col)
    pen.setWidthF(1.3)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(x, cy - 4.0, 14.0, 8.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawEllipse(QPointF(x + 7.0, cy), 2.0, 2.0)
    if hidden:
        p.setPen(pen)
        p.drawLine(QPointF(x + 1.0, cy + 6.0), QPointF(x + 13.0, cy - 6.0))


class BrowserDelegate(QStyledItemDelegate):
    """M162's ONE paint door for the browser (FD3 receipts): the eye
    gutter (LAW-1.1 — ALWAYS rendered, never hover-revealed: their own
    support KB exists because users begged for hover-toggle and got
    refused), the ACTIVE DOT on the active row (LAW-1.6 — the
    documented deviation: Fusion's missing active marker is its
    community's #1 browser complaint; we ship the dot always), the
    ancestry dotted underline on canvas-select (LAW-5.2) and the
    find-in-browser dashed flash (LAW-5.1). Text shifts 20 px clear of
    the gutter — no stylesheet surgery, no per-row widgets."""

    GUTTER = 20

    def paint(self, p, opt, idx):
        tree = self.parent()
        role = idx.data(Qt.UserRole)
        it = tree.itemFromIndex(idx)
        p.save()
        if role is not None and tree.has_eye(role):
            _paint_eye(p, opt.rect.left() + 3.0,
                       float(opt.rect.center().y()),
                       tree.eye_hidden(role))
        if role in tree._under:                    # LAW-5.2 underline
            pen = QPen(QColor(DARK["accent"]))
            pen.setWidthF(1.2)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.drawLine(opt.rect.left() + self.GUTTER,
                       opt.rect.bottom() - 2,
                       opt.rect.right() - 6, opt.rect.bottom() - 2)
        opt.rect = opt.rect.adjusted(self.GUTTER, 0, 0, 0)
        super().paint(p, opt, idx)                 # name, selection, tree
        if (role and role[0] == "body" and self._doc_active() == role[1]):
            p.setPen(Qt.PenStyle.NoPen)            # LAW-1.6 active dot
            p.setBrush(QColor(DARK["accent"]))
            p.drawEllipse(QPointF(float(opt.rect.right() - 8),
                                  float(opt.rect.center().y())), 3.5, 3.5)
        if it is not None and it is tree._flash:   # LAW-5.1 flash
            pen = QPen(QColor(DARK["line_hi"]))
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(tree.visualRect(idx).adjusted(1, 1, -1, -1))
        p.restore()

    def setModelData(self, editor, model, idx):
        """M162: the rename rides the KERNEL door (feature_renamed →
        _apply_rename → counted relinks) — never a raw model write. A
        refused name must not stain the row; the reload repaints truth.
        """
        pass

    def setEditorData(self, editor, idx):
        """The inline rename pre-fills the BARE NAME — the row's text
        is decorated (+ and a box glyph), and the in-place field edits
        the name, not the makeup."""
        tree = self.parent()
        role = idx.data(Qt.UserRole)
        if (tree._renaming is not None
                and isinstance(editor, QLineEdit)
                and role and role[0] == "feature"
                and tree._doc is not None):
            feats = list(tree._doc.features)
            if 0 <= role[1] < len(feats):
                editor.setText(feats[role[1]].name)
                return
        super().setEditorData(editor, idx)

    def _doc_active(self):
        doc = self.parent()._doc
        return doc.active_body if doc is not None else None


class FeatureTree(QTreeWidget):
    feature_menu = Signal(object, object)   # Feature, global QPoint
    cplane_menu = Signal(str, object)       # plane name, global QPoint
    caxis_menu = Signal(str, object)        # M125 work axis, same grammar
    body_menu = Signal(object, object)        # body name, global QPoint
    joint_menu = Signal(object, object)       # M146: joint id, QPoint
    root_menu = Signal(object)                # M134: doc-row (isolation
                                              # exits live here — leaving
                                              # must not require finding
                                              # the isolated row)
    feature_delete = Signal(object)         # Feature (Del key, M72)
    feature_rename = Signal(object)         # Feature (F2 key, M72)
    row_leave = Signal()                    # M160/FD2-L4: the pointer
                                            #   left the whole tree
                                            #   (hover wash dies)
    eye_toggled = Signal(object)            # M162/FD3-1.1: an eye was
                                            #   clicked — the ROLE tuple
                                            #   (body / bodies folder);
                                            #   the WINDOW owns the kernel
    feature_renamed = Signal(object, str)   # M162/FD3-2.3: inline
                                            #   rename committed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setUniformRowHeights(True)
        self.setIndentation(14)
        self._doc: Document | None = None
        self.feature_selected = None  # callback(feature|None)
        # ---- M162 state ----------------------------------------------------
        # LAW-1.3: the Bodies folder wears its own eye and OVERRIDES the
        # chain — children keep their latent state, the layer says no.
        # It is VIEW state: a new document opens with clean eyes.
        self.folder_vis = True
        self._under: list = []               # LAW-5.2 ancestry role tuples
        self._flash = None                   # LAW-5.1 row being flashed
        self._renaming = None                # LAW-2.3 inline editor owner
        self.setItemDelegate(BrowserDelegate(self))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        #   (the ONLY edit door is editItem() from the name double-click)
        # M162's latent-law repair: Qt's DEFAULT expandsOnDoubleClick
        # was swallowing the first double-click on every row with kids —
        # M104's "double-click a body activates" and the sketch/sheet
        # edit doors were UNREACHABLE by mouse (m96/m104 emitted the
        # signal directly to test around it). Fusion's double-click
        # acts on the row; expansion is the arrow's own job (which
        # still toggles — that is a different Qt mechanism).
        self.setExpandsOnDoubleClick(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def leaveEvent(self, ev):
        """M160/FD2-L4: the row-hover wash is a guest — it dies the
        instant the pointer leaves the tree, and Qt fires no signal for
        that, so this widget speaks one."""
        super().leaveEvent(ev)
        self.row_leave.emit()

    # ---- eyes (M162, FD3 LAW-1.1/1.3/2.2) ----------------------------------
    def has_eye(self, role) -> bool:
        """Which rows wear an eye: the ones whose visibility kernel is
        REAL — bodies (doc truth) and the Bodies folder (the AND-chain
        layer). An eye that controlled nothing would be a lie, so
        sketch/datum rows bank theirs until their kernels exist."""
        return (role is not None
                and (role[0] == "body"
                     or (role[0] == "folder" and role[1] == "bodies")))

    def eye_hidden(self, role) -> bool:
        if self._doc is None:
            return False
        if role[0] == "folder":
            return not self.folder_vis
        for b in self._doc.body_list():
            if b["name"] == role[1]:
                return not bool(b.get("visible", True))
        return False

    def _eye_band(self, it) -> QRect:
        r = self.visualRect(self.indexFromItem(it))
        return QRect(r.left(), r.top(), BrowserDelegate.GUTTER, r.height())

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            it = self.itemAt(ev.position().toPoint())
            role = it.data(0, Qt.UserRole) if it is not None else None
            if (role and self.has_eye(role)
                    and self._eye_band(it).contains(ev.position().toPoint())):
                # Fusion's bulb law: an eye click TOGGLES — it never
                # selects, never moves the current row.
                self.eye_toggled.emit(role)
                return
        super().mousePressEvent(ev)

    # ---- inline rename on the NAME (M162, FD3 LAW-2.3) ---------------------
    def _text_left(self, it) -> int:
        """Where a row's TEXT begins: the gutter plus the branch zone
        ((depth+1) indentations of arrows) — a double-click left of it
        stays Qt's own expand/collapse law, right of it is the name."""
        lvl, p = 0, it.parent()
        while p is not None:
            lvl += 1
            p = p.parent()
        return (lvl + 1) * self.indentation() + BrowserDelegate.GUTTER

    def mouseDoubleClickEvent(self, ev):
        it = self.itemAt(ev.position().toPoint())
        role = it.data(0, Qt.UserRole) if it is not None else None
        if (role and role[0] == "feature"
                and ev.position().x() >= self._text_left(it)):
            # Double-click ON THE NAME renames in place (Enter commits,
            # Escape abstains). The icon side keeps the old activation
            # door — two truths, one row, the vendor's own split.
            self._renaming = it
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            self.editItem(it)
            return
        super().mouseDoubleClickEvent(ev)

    def commitData(self, editor):
        it = self._renaming
        if it is not None and self._doc is not None:
            role = it.data(0, Qt.UserRole)
            text = editor.text().strip()
            if role and role[0] == "feature" and text:
                feats = list(self._doc.features)
                i = role[1]
                if 0 <= i < len(feats):
                    self.feature_renamed.emit(feats[i], text)
        self._renaming = None
        super().commitData(editor)

    def closeEditor(self, editor, hint):
        if self._renaming is not None:      # Escape lands here without
            self._renaming.setFlags(        #   commitData — the row
                self._renaming.flags()      #   forgets it was editable
                & ~Qt.ItemIsEditable)
        self._renaming = None
        super().closeEditor(editor, hint)

    # ---- find in browser (M162, FD3 LAW-5.1) --------------------------------
    def reveal_feature(self, feature) -> bool:
        """Light the feature's row, scroll it in, and flash the dashed
        outline while it is found — the probe's own words: the row
        appears with \"dashed lines\". The flash is timed, not eternal."""
        if self._doc is None or feature not in self._doc.features:
            return False
        want = ("feature", self._doc.features.index(feature))

        def walk(it):
            for i in range(it.childCount()):
                ch = it.child(i)
                if ch.data(0, Qt.UserRole) == want:
                    return ch
                got = walk(ch)
                if got is not None:
                    return got
            return None

        it = walk(self.topLevelItem(0))
        if it is None:
            return False
        self.setCurrentItem(it)
        self.scrollToItem(it, QAbstractItemView.PositionAtCenter)
        self._flash = it
        QTimer.singleShot(900, self._end_flash)
        self.viewport().update()
        return True

    def _end_flash(self):
        self._flash = None
        self.viewport().update()

    # ---- ancestry underline (M162, FD3 LAW-5.2) -----------------------------
    def set_ancestry(self, body_name):
        """Canvas-select draws the dotted lineage: root ▸ Bodies ▸ the
        owning body. None clears. Roles are stored, not items — a reload
        rebuilds rows and the lineage survives."""
        self._under = ([("root", None), ("folder", "bodies"),
                        ("body", body_name)] if body_name else [])
        self.viewport().update()

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
        elif role and role[0] == "plane":
            # M135: origin planes get the same menu (section rides them);
            # the builder knows XY/XZ/YZ are not renameable or deletable.
            self.cplane_menu.emit(role[1], self.viewport().mapToGlobal(pos))
        elif role and role[0] == "caxis":
            self.caxis_menu.emit(role[1], self.viewport().mapToGlobal(pos))
        elif role and role[0] == "body":
            self.body_menu.emit(role[1], self.viewport().mapToGlobal(pos))
        elif role and role[0] == "joint":      # M146: Delete Joint
            self.joint_menu.emit(role[1], self.viewport().mapToGlobal(pos))
        elif role and role[0] == "root":
            self.root_menu.emit(self.viewport().mapToGlobal(pos))

    def set_document(self, doc: Document):
        self._doc = doc
        # M162: a new document opens with clean eyes and no washes
        # (folder_vis is VIEW state — LAW-1.3; the doc carries its own
        # per-body truth, which reload reads fresh).
        self.folder_vis = True
        self._under = []
        self._flash = None
        self.reload()

    @staticmethod
    def datum_badges(doc) -> dict:
        """M152: the registry as the tree sees it — {ref: [letters]},
        plane/axis refs keyed by NAME, hole refs by UID (rename-
        immune, the two binding families the registry already speaks).
        Pure over the registry: no geometry, no lookups that fail."""
        out: dict = {}
        if doc is None:
            return out
        for d in getattr(doc, "datums", []):
            out.setdefault(d["ref"], []).append(d["letter"])
        return out

    def reload(self):
        self.clear()
        if not self._doc:
            return
        # M130: the ladder's cheap familiarity — duplicate feature names
        # ride the browser as "Name (1)", "Name (2)" in first-appearance
        # order (Fusion's disambiguation). Display only: the model, the
        # rename prompt and every reference keep the RAW name.
        from collections import Counter
        dupe = Counter(f.name for f in self._doc.features)
        seen: dict = {}
        root = QTreeWidgetItem([self._doc.title])
        root.setFlags(root.flags() & ~Qt.ItemIsSelectable)
        root.setData(0, Qt.UserRole, ("root", None))   # M134: right-
        self.addTopLevelItem(root)                      # clickable home
                                                        # for exits

        # ---- Origin: point + axes + planes, like Fusion's folder ----------
        origin = QTreeWidgetItem(["Origin"])
        origin.setData(0, Qt.UserRole, ("folder", "origin"))
        root.addChild(origin)
        # rung D (M152): the letters the registry wears, and the names
        # whose attachment state is speaking (warn fg — amber is the
        # sibling of M118's red, and red still outranks it: an error
        # badge means the row is already the log's business).
        badges = self.datum_badges(self._doc)
        warn_names = set()
        for line in getattr(self._doc, "attachment_warnings", []) or []:
            if " — " in line:
                warn_names.add(line.split(" — ")[0])
            if "'s datum" in line:
                warn_names.add(line.split("'s datum")[0])

        def _badge(ref):
            letters = badges.get(ref)
            return (" [" + " ".join(letters) + "]") if letters else ""

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
            it = QTreeWidgetItem(["\u25ad " + pl + _badge(pl[:2])])
            it.setData(0, Qt.UserRole, ("plane", pl[:2]))   # M152 [A]
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
            # M162 (FD3-1.1): the row text is just the NAME — visibility
            # truth rides the ALWAYS-rendered eye the delegate paints in
            # its gutter (the ▣ prefix and the "(hidden)" suffix retire;
            # a word is not an affordance, an icon you can click is).
            body_item = QTreeWidgetItem([nm + tag])
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

        # ---- Joints (n) ▸ one row per relation (M146, assembly rung 1).
        # The folder appears ONLY when joints exist: a plain part's
        # browser stays exactly what it always was. Rows name the pair
        # by DISPLAY name — the record underneath binds ids.
        joints = list(getattr(self._doc, "joints", []) or [])
        if joints:
            jf = QTreeWidgetItem([f"Joints ({len(joints)})"])
            jf.setData(0, Qt.UserRole, ("folder", "joints"))
            root.addChild(jf)
            by_id = {b.get("id"): b["name"] for b in listed}
            for j in joints:
                it = QTreeWidgetItem([
                    "\u27f7 " + by_id.get(j["b"], "?") + " \u2192 "
                    + by_id.get(j["a"], "?")])
                it.setData(0, Qt.UserRole, ("joint", j["id"]))
                jf.addChild(it)
            jf.setExpanded(True)

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
                    else "\u2307" if isinstance(f, CoilFeature)  # ⌇ bolt
                    else "\u2935" if isinstance(f, PathPatternFeature)
                    else "\u25a1")
            nm = f.name
            if dupe[nm] > 1:                        # shared name → (k)
                seen[nm] = seen.get(nm, 0) + 1
                nm = f"{nm} ({seen[nm]})"
            label = (f"{glyph} {nm}" if fillet
                     else f"{glyph} {kind} {nm}")
            if isinstance(f, HoleFeature):
                label += _badge(f.uid)      # M152: ◯ Hole 1 [C] —
            #                                 the hole family binds uid
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, ("feature", i))
            if f.suppressed:
                item.setForeground(0, QColor(DARK["fg_faint"]))
            elif f.name in warn_names:      # M152 rung D: the amber
                item.setForeground(0, QColor(DARK["warn"]))
            parent = body_nodes.get(getattr(f, "body", None) or default)
            if parent is None:                      # orphaned by hand-edit
                parent = body_nodes[default]
            parent.addChild(item)
            if (isinstance(f, (ExtrudeFeature, RevolveFeature, HoleFeature))
                    and f.sketch):
                base, full = _sketch_state(f.sketch)
                lbl = base + _badge(
                    f.sketch.get("host") or "")   # M152: ✎ → [A]
                sk = QTreeWidgetItem([lbl])
                sk.setIcon(0, icons.sketch_icon(locked=full))
                sk.setData(0, Qt.UserRole, ("sketch", i))
                if f.name in warn_names:
                    sk.setForeground(0, QColor(DARK["warn"]))
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
            base, full = _sketch_state(feats[i].sketch)
            it = QTreeWidgetItem([base])
            it.setIcon(0, icons.sketch_icon(locked=full))
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
            it = QTreeWidgetItem(["\u25ad " + pl["name"]     # ▭
                                  + _badge(pl["name"])])     # M152 [A]
            it.setData(0, Qt.UserRole, ("cplane", pl["name"]))
            constr.addChild(it)
        for ax in axes:
            it = QTreeWidgetItem(["\u2225 " + ax["name"]     # ∥
                                  + _badge(ax["name"])])     # M152 [B]
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

    def select_body(self, name: str | None) -> bool:
        """Canvas -> browser (M131): light up the row for the body that
        owns the picked faces and scroll it into view. Selecting emits
        currentItemChanged, which re-announces properties exactly as a
        hand-click would — one selection truth, one reaction path."""
        if not name:
            return False

        def walk(it):
            for i in range(it.childCount()):
                ch = it.child(i)
                role = ch.data(0, Qt.UserRole)
                if role and role[0] == "body" and role[1] == name:
                    self.blockSignals(True)
                    self.setCurrentItem(ch)
                    self.blockSignals(False)
                    self.scrollToItem(ch, QAbstractItemView.PositionAtCenter)
                    self.viewport().update()
                    return True
                if walk(ch):
                    return True
            return False
        root = self.topLevelItem(0)
        return bool(root and walk(root))

    def keyPressEvent(self, ev):
        """Fusion's browser key grammar (M72): Del removes the selected
        feature, F2 renames it — same paths as the context menu.
        M162 adds LAW-2.2: V toggles the visibility of the selection."""
        f = self.current_feature()
        if f is not None and ev.key() in (Qt.Key_Delete,
                                          Qt.Key_Backspace):
            self.feature_delete.emit(f)
            return
        if f is not None and ev.key() == Qt.Key_F2:
            self.feature_rename.emit(f)
            return
        if ev.key() == Qt.Key_V:
            it = self.currentItem()
            role = it.data(0, Qt.UserRole) if it is not None else None
            if role and self.has_eye(role):
                self.eye_toggled.emit(role)
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
