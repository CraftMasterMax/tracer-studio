"""M93 — the drawing sheet canvas: white paper, live views, zoom & pan.

Views are never stored: every paint re-derives silhouettes from the
model in front of it, so the sheet can't rot while the solid changes —
the same honesty Fusion's views buy by rebuilding.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPageLayout, QPageSize,
                           QPen, QPdfWriter)

from PySide6.QtWidgets import QWidget

from ..core import drawing
from ..core import fits
from ..core import gdt
from ..core.geometry import Solid
from .theme import DRAWING

# the sheet is paper: its inks never follow the UI theme (a drawing
# prints the same in dark or light chrome); tokens live in theme.DRAWING
_DESK = QColor(DRAWING["desk"])
_DESK_EDGE = QColor(DRAWING["desk_edge"])
_PAPER = QColor(DRAWING["paper"])
_VIEW_EDGE = QColor(DRAWING["view_edge"])
_SHEET = QColor(DRAWING["sheet"])
_BORDER = QColor(DRAWING["border"])
_DETAIL = QColor(DRAWING["detail"])
_HATCH = QColor(DRAWING["hatch"])
_FAINT = QColor(DRAWING["faint"])
_RED = QColor(DRAWING["red"])
_SELECT = QColor(DRAWING["select"])


def scale_label(factor: float) -> str:
    """The caption under a scaled view, drawn the way drawings say it:
    0.5 -> "1:2", 2 -> "2:1", 1 -> "1:1"."""
    if abs(factor - 1.0) < 1e-9:
        return "1:1"
    if factor < 1.0:
        return f"1:{1.0 / factor:.6g}"
    return f"{factor:.6g}:1"


# [DWG-REF-DRAWING-VIEW-DLG, verbatim] the Style members in printed
# order; only these TWO are offered - the line-art truth (see
# DrawingCanvas._view_dialog).  The reference form "Visible Edges and
# Hidden Edges" rules; the task pages' "Visible and Hidden Edges" is
# the flagged vendor label drift (cache/view32/live.md).
VIEW_STYLES = ("Visible Edges", "Visible Edges and Hidden Edges")
# [DWG-REF-DRAWING-VIEW-DLG, verbatim] "From Parent: Inherits the
# view style from the parent view. (Projected view, section view, and
# detail view only.)" - the page PRINTS it first and scopes it AWAY
# from base views, so it enters this kernel on the SECTION door only
# (M201 R34); the base dialog's VIEW_STYLES pair stays the page's
# law for base views.
VIEW_STYLE_INHERIT = "From Parent"
# The page prints Default: ZERO times (bare "default" too - live lane D
# count) - the resting member is OURS-declared: every base view today
# draws dashed back ink (M97/M101), which IS this member.
VIEW_STYLE_DEFAULT = "Visible Edges and Hidden Edges"
SCALE_CHOICES = ["Fit (auto)", "1:1", "1:2", "1:5", "1:10", "2:1", "5:1"]


class DrawingCanvas(QWidget):
    dim_added = Signal(str, tuple, tuple, dict)  # view, a, b, opts (M94/95)
    balloon_added = Signal(str, tuple, int)      # view, model xy, item (M110)
    fit_requested = Signal(str, int)             # M114: view, dim index
    gdt_requested = Signal(str, int)             # M144: view, dim index
    view_drag_begin = Signal()                   # M96: undo capture hook
    view_scale_requested = Signal(str)           # M100: Scale dialog ask
    section_added = Signal(dict)                 # M136: {parent,p0,p1,flip}
    detail_added = Signal(dict)                  # M201 R36: {parent,c,r,at}
    breakout_added = Signal(dict)                # M201 R37: {view,loop}
    breakout_edit_requested = Signal(int)        # R37: dbl-click a profile
    #   (the INDEX into sheet()["breakouts"] - a Signal(dict] would hand
    #   the handler a QVariant-marshalled COPY, and an edit that mutates
    #   a copy is the loudest kind of lie)
    section_edit_requested = Signal(str)         # M137: dbl-click a child
    tool_note = Signal(str)                      # M136: canvas says, status

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.page = "A3"
        self.sheet_idx = -1                      # M96: which sheet shows
        self._zoom = 1.6                       # screen px per sheet mm
        self._center = QPointF(0.0, 0.0)       # sheet mm coords at centre
        self._drag = None
        self._dim_mode = False                 # M94: bubble tool armed?
        self._dim_first = None                 # first endpoint (view, xy)
        self._balloon_mode = False             # M110: balloon tool armed?
        self._sec_mode = False                 # M136: section-line tool
        self._excl_src: dict = {}              # M139: (result id,
                                               #  excludes) -> cut source
        self._sec_pts = []                     # parent MODEL xy of clicks
        self._sec_view = None
        self._sec_hover = None                 # page xy of the rubber tip
        self._det_mode = False                 # M201 R36: detail tool armed?
        self._det_view = None                  # parent under the boundary
        self._det_c = None                     # boundary centre, parent
        #   MODEL xy (travels with the view, like the M136 line)
        self._det_r = None                     # boundary radius, mm
        self._det_a = 0.7853981633974483       # identifier angle (the
        #   drag's direction; 45° is only the untouched-rest default)
        self._det_hover = None                 # page xy of the rubber tip
        self._bk_mode = False                  # M201 R37: breakout armed?
        self._bk_view = None                   # the view holding the loop
        self._bk_pts: list = []                # loop pts, view MODEL xy
        self._bk_hover = None                  # page xy of the rubber tip
        self._pre_breakout: dict = {}          # R37: sources BEFORE the cuts
        self._printing = False                 # M143: publishing to paper
        self._fit_mode = False                 # M114: fit-callout armed?
        self._gdt_mode = False                 # M144: FCF editor armed?
        self._view_drag = None                 # M96: (view, start, base)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)

    def set_document(self, doc, idx: int | None = None):
        """Show a sheet (M96: idx picks it; default = newest)."""
        self.doc = doc
        if doc is not None and doc.drawings:
            self.sheet_idx = (idx if idx is not None
                              else len(doc.drawings) - 1)
            self.sheet_idx = max(0, min(self.sheet_idx,
                                        len(doc.drawings) - 1))
            self.page = self.sheet().get("page", "A3")
        else:
            self.sheet_idx = -1
        self._center = QPointF(*[v / 2 for v in
                             drawing.sheet_size(self.page)])
        self._dim_first = None
        self._view_drag = None
        self.update()

    def sheet(self) -> dict:
        """The sheet on the table right now (empty dict if none)."""
        if self.doc is None or not self.doc.drawings:
            return {}
        return self.doc.drawings[max(
            0, min(self.sheet_idx, len(self.doc.drawings) - 1))]

    # ---- data -----------------------------------------------------------
    def sections(self) -> list:
        """M102: the stored cuts on this sheet ({name, axis, at} or
        M136 line-on-view {name, parent, p0, p1, flip})."""
        return list(self.sheet().get("sections") or [])

    def details(self) -> list:
        """M201 R36 [Detail views, verbatim] "A detail view is a
        drawing view that shows a portion of another drawing view at
        an enlarged scale" - the sheet's stored boundaries: {name
        (letter), parent, c (parent MODEL xy of the centre), r (mm)}
        plus any user Name. COPY semantics ride (the sections()
        trap): write through sheet()["details"] for real edits."""
        return list(self.sheet().get("details") or [])

    def breakouts(self) -> list:
        """M201 R37 [Breakout section views, verbatim] "a breakout
        section is part of an existing drawing view" - the sheet's
        stored profiles: {view (the name it cuts), loop (closed
        polyline in that view's MODEL xy - it rides a nudged view
        like every other furniture), depth (typed distance; ABSENT
        means the page's own default, "half of your design's depth",
        held LIVE so a grown design deepens the cut)}. One entry per
        view - [verbatim] "A drawing view can contain only one
        breakout section." COPY semantics ride: write through
        sheet()["breakouts"] for real edits."""
        return list(self.sheet().get("breakouts") or [])

    def _sec_src(self, sec):
        """M139: which bodies a cut reads, and what stands in whole.
        An entry's "exclude" filters the CUT SOURCE (the union that
        the plane breaks, the wound that hatches); the excluded
        bodies UNION BACK into the projected half, whole. That
        add-back is the difference between ASME's 'drawn whole,
        unhatched' and silent deletion: the child projects ONLY the
        kept half, so filtering without adding back erases the body
        outright (verified against the vendor ask, queue doc). An
        exclude name that no body answers is inert — the M130 rename
        law, honest degradation. The union is cached per (result
        identity, exclude set) so paints stay cheap."""
        exc = [str(n) for n in (sec.get("exclude") or [])]
        if not exc:
            return self.doc.result, []
        bodies = self.doc.body_solids()
        keep = [n for n in sorted(bodies) if n not in exc]
        if not keep:
            raise ValueError("a section must cut at least one body — "
                             "excluded is all of them")
        key = (id(self.doc.result), tuple(sorted(exc)))
        hit = self._excl_src.get(key)
        if hit is not None and hit[0] is self.doc.result:
            src = hit[1]
        else:
            src = bodies[keep[0]] if len(keep) == 1 \
                else Solid.batch_union([bodies[n] for n in keep])
            if len(self._excl_src) > 8:
                self._excl_src.clear()
            self._excl_src[key] = (self.doc.result, src)
        return src, [bodies[n] for n in sorted(bodies) if n in exc]

    def _sec_cut(self, sec) -> dict:
        """M136: the one place a stored section entry becomes a cut —
        the M102 axis dialog form or the two-click line on a parent;
        both return {"half", "view", "cut"}, and a line section's
        "view" is a basis TUPLE that the whole projection pipeline
        already carries. M138: a line entry carrying "pts" is a
        JOGGED polyline — its halves union into the one solid the
        child projects and its caps concatenate across the steps, so
        every downstream consumer reads a jog like a straight cut.
        M139: an entry carrying "exclude" cuts a filtered source and
        stands the excluded bodies in whole (see _sec_src); an entry
        without the key is byte-for-byte the pre-M139 path."""
        src, back = self._sec_src(sec)
        if "pts" in sec:
            segs, basis = drawing.plane_from_polyline(
                sec["parent"], sec["pts"], bool(sec.get("flip")))
            res = drawing.section_jogged(
                src, segs, basis,
                mode=str(sec.get("mode", "full")),
                dist=sec.get("dist"))
        elif "parent" in sec:
            o, a, dl = drawing.plane_from_line(
                sec["parent"], sec["p0"], sec["p1"],
                bool(sec.get("flip")))
            res = drawing.section_on(src, o, a, right=dl,
                                     mode=str(sec.get("mode", "full")),
                                     dist=sec.get("dist"))
        else:
            res = drawing.section(src, sec["axis"], float(sec["at"]))
        if back and res["half"] is not None:
            res = dict(res, half=Solid.batch_union([res["half"]]
                                                    + back))
        return res

    def _sources(self) -> dict:
        """view name -> (solid to project, standard view key), live.
        The four standards project the full result; a section projects
        its half through the standard basis that reads the cut face.
        M137: a SLICE section has no half at all (None) — views()
        substitutes its cap loops, and everything that paints a solid
        skips it."""
        if self.doc is None or self.doc.result is None:
            return {}
        out = {v: (self.doc.result, v) for v in drawing.STANDARD}
        for sec in self.sections():
            try:
                d = self._sec_cut(sec)
            except Exception:
                continue
            out[sec["name"]] = (d["half"], d["view"])
        # M201 R36 [Create a detail view, verbatim] "Select a base
        # view, projected view, or section view on the current sheet
        # as the parent view" - a detail is JUST ANOTHER SOURCE: the
        # parent's solid clipped by the sight-axis cookie (the core's
        # detail_cookie), projected through the parent's own basis.
        # Every consumer - place(), drag, the style walk, hidden
        # lines - gets the detail for free, and it re-derives on
        # every repaint: a detail is a projection, never a picture.
        # A SLICE parent (solid None) has no depth to clip: the
        # honest answer is absence, not invention.
        for det in self.details():
            src = out.get(det.get("parent"))
            if src is None or src[0] is None:
                continue
            try:
                cook = drawing.detail_cookie(src[0], src[1], det["c"],
                                             det["r"])
            except Exception:
                continue
            out[det["name"]] = (cook, src[1])
        # M201 R37 [Breakout section views, verbatim] a breakout "is
        # PART OF AN EXISTING DRAWING VIEW" - it adds no source, it
        # CUTS one: the same name now projects the solid with the
        # drawn profile removed to depth. The pre-cut sources are kept
        # (_pre_breakout) so the edit door can re-check a new depth
        # against the WHOLE solid, never against its own cut. Drawn
        # once, re-derived every repaint; the page's Reset Start Point
        # is our non-feature - the front of the design is read LIVE
        # from the solid, there is no stale anchor to reset. A stored
        # depth a later model shrink swallowed (a section, not a
        # breakout) cuts NOTHING: the view reverts to whole ink, the
        # entry survives for the drafter to fix - absence, not
        # invention.
        pre = dict(out)
        for bk in self.breakouts():
            src = out.get(bk.get("view"))
            if src is None or src[0] is None:
                continue
            try:
                cut, _ = drawing.breakout_solid(src[0], src[1],
                                                bk["loop"],
                                                bk.get("depth"))
            except Exception:
                continue
            out[bk["view"]] = (cut, src[1])
        self._pre_breakout = pre
        fp = self.doc.flat_feature()               # M147: the flat
        if fp is not None:                         # pattern rides EVERY
            sol = self.doc.body_solids().get("_flat")   # sheet (v1);
            if sol is not None:                    # added last — a
                out["Flat"] = (sol, "top")         # user "Flat" section
        flats = self.doc.sheet_flats()             # SM3: a parametric
        if flats:                                  # sheet answers Flat
            slab = self.doc.flat_slab(sorted(flats)[0])  # with its LIVE
            if slab is not None:                   # walk — law needs
                out["Flat"] = (slab, "top")        # no snapshot
        # (a snapshot run on a parametric body anyway AGREES to ==;
        # the walk, being the newer law, speaks last)
        return out                                 # yields to the paper

    def views(self) -> dict:
        """Live silhouette views of the current result (model space),
        sections included. M137: a SLICE section shows the cut face
        alone — its cap loops are already chains in the child's page
        basis, so place/hatch/measure all just work."""
        out: dict = {}
        for name, (sol, v) in self._sources().items():
            if sol is not None:
                out[name] = drawing.project_view(sol, view=v)
                continue
            sec = self._sec_by_name(name)
            if sec.get("mode") == "slice":
                out[name] = [list(L) for L in self._sec_cut(sec)["cut"]]
        return out

    def _sec_by_name(self, name: str) -> dict:
        """The stored entry behind a section view's name."""
        return next(s for s in self.sections() if s["name"] == name)

    def chains(self, view: str = "top") -> list:
        return self.views().get(view, [])

    def _secs_by_name(self) -> dict:
        return {s["name"]: s for s in self.sections()}

    def _dets_by_name(self) -> dict:
        return {d["name"]: d for d in self.details()}

    def effective_style(self, name: str) -> str:
        """M201 R34 [DWG-REF-DRAWING-VIEW-DLG, verbatim] "From
        Parent: Inherits the view style from the parent view." -
        what the ink REALLY does on a view, resolved through any
        inheritance chain:
          * an explicit stored member answers itself;
          * a stored "From Parent" walks to the parent view (a base,
            or another section - nesting is real);
          * no stored style is the OURS-declared rest: a base view
            shows the pair (dashed back ink today), a section obeys
            its M137 flag (slice never shows ink: there is no depth
            left to hide behind - the mode outranks the style).
        A cycle (hand-edited files only - creation cannot make one)
        resolves to the rest, never to a hang."""
        vs = self.sheet().get("vstyle") or {}
        secs = self._secs_by_name()
        seen = set()
        while name not in seen:
            seen.add(name)
            st = vs.get(name)
            if st in VIEW_STYLES:
                return st
            if st == VIEW_STYLE_INHERIT:
                parent = (secs.get(name) or {}).get("parent") \
                    or (self._dets_by_name().get(name) or {}).get(
                        "parent")     # M201 R36: the page grants
                #   "From Parent" to detail views too - the walk
                #   already exists, one hop is one hop whatever the
                #   child's kind
                if parent is None:            # nothing to inherit
                    #   from (legacy or hand-edited record): the rest
                    break
                name = parent
                continue
            sec = secs.get(name)
            if sec is None:
                return VIEW_STYLE_DEFAULT     # base view at rest
            if sec.get("mode") == "slice":
                return "Visible Edges"
            return (VIEW_STYLE_DEFAULT if sec.get("hidden")
                    else "Visible Edges")
        return VIEW_STYLE_DEFAULT

    def _hidden_off(self) -> set:
        """M137: section views read WITHOUT back ink (ASME omits
        hidden lines in section — the wound already shows the
        interior); a section opts back in per entry, and a SLICE
        never opts: there is no depth left to hide behind.
        M201 R32 [DWG-REF-DRAWING-VIEW-DLG, verbatim] the Style row:
        a base/projected view answering "Visible Edges" (one of the
        page's two offered members) joins the set - the member is
        exactly the ink the kernel already computes and can remove.
        M201 R34: a section storing "From Parent" now LETS THE
        PARENT ANSWER - inherited Visible Edges hides its ink, the
        inherited pair returns it (overriding its own flag: that IS
        inheriting); a slice's mode still outranks any inheritance."""
        off = {s["name"] for s in self.sections()
               if s.get("mode") == "slice" or not s.get("hidden")}
        vs = self.sheet().get("vstyle") or {}
        off |= {v for v, st in vs.items() if st == "Visible Edges"}
        secs = self._secs_by_name()
        for v, st in vs.items():
            if st != VIEW_STYLE_INHERIT:
                continue
            eff = self.effective_style(v)
            if eff == "Visible Edges":
                off.add(v)
            elif eff == VIEW_STYLE_DEFAULT and (
                    v not in secs or secs[v].get("mode") != "slice"):
                off.discard(v)               # inheritance GIVES ink
                #   back - but a slice has none to give (mode law)
        return off

    def hidden_views(self) -> dict:
        """M97: dashed back creases per view (model space, live)."""
        off = self._hidden_off()
        return {name: drawing.project_hidden(sol, view=v)
                for name, (sol, v) in self._sources().items()
                if name not in off and sol is not None}

    def hidden_page(self, view: str) -> list:
        """Hidden chains in sheet-mm page coords — moves included,
        since the frame they ride on already carries the view's move."""
        if view in self._hidden_off():       # M137: sections default
            return []                        # to no back ink
        src = self._sources().get(view)
        if src is None or src[0] is None:
            return []
        sol, vkey = src
        sc, off = self.frames()[view]
        return [[(float(p[0] * sc + off[0]), float(p[1] * sc + off[1]))
                 for p in c]
                for c in drawing.project_hidden(sol, view=vkey)]

    def _flat_lines(self) -> list:
        """The Flat view's bend centre-lines in model space: the LIVE
        walk of a parametric sheet answers FIRST (its numbers are the
        features'), else the M147 snapshot's stored segments. Both
        carry {x, y0, y1} — one mapping serves two laws (§4)."""
        if self.doc is None:
            return []
        flats = self.doc.sheet_flats()
        if flats:
            return flats[sorted(flats)[0]]["bend_lines"]
        fp = self.doc.flat_feature()
        return [] if fp is None else fp.bend_lines

    def bends_page(self, view: str) -> list:
        """M147: the flat view's bend centre-lines in sheet-mm page
        coords — read from the FLAT's stored segments (analytic ink;
        the rail finding says never re-fit lines or arcs from the
        slab's mesh), mapped through the view's frame like hidden ink:
        moves ride, the display spin does not. Every other view
        answers empty."""
        if self.doc is None or view != "Flat":
            return []
        lines = self._flat_lines()
        if not lines:
            return []
        fr = self.frames().get(view)
        if fr is None:
            return []
        sc, off = fr
        return [[(bl["x"] * sc + off[0], bl["y0"] * sc + off[1]),
                 (bl["x"] * sc + off[0], bl["y1"] * sc + off[1])]
                for bl in lines]

    def bend_labels(self, view: str) -> list:
        """SM3: per-bend text for the LIVE flat — "90° ↑ R3.00
        K=0.44" built FROM THE PARAMS, the analytic-truth lesson
        (SM2 §4.5) aimed at words. A detector snapshot answers []:
        its paper says what was measured and invents no ownership.
        (page-x, page-y, text) in sheet-mm; bands ride bl["band"],
        so a seam-sorted line still names its own bend."""
        if self.doc is None or view != "Flat":
            return []
        flats = self.doc.sheet_flats()
        if not flats:
            return []
        body = sorted(flats)[0]
        fr = self.frames().get(view)
        if fr is None:
            return []
        sc, off = fr
        bends = self.doc.sheet_states()[body]["bends"]
        out = []
        for bl in flats[body]["bend_lines"]:
            n = bl["band"]
            a, r, k = bends[n]
            arrow = "\u2191" if float(a) >= 0 else "\u2193"
            # the shop stamps ALTERNATE sides: two labels on one
            # baseline collide the moment bends sit close together
            yy = (float(bl["y1"]) + 1.5 if n % 2 == 0
                  else float(bl["y0"]) - 3.3)
            out.append(((float(bl["x"]) * sc + off[0],
                         yy * sc + off[1]),
                        f"{abs(float(a)):g}\u00b0 {arrow} "
                        f"R{float(r):.2f} K={float(k):g}"))
        return out

    def cuts_page(self) -> dict:
        """M102: section name -> closed cut-face loops in sheet-mm page
        coords (moves and per-view scales ride the frame). M109: a view
        rotated for display carries its hatch around with it."""
        srcs = self._sources()
        out: dict = {}
        placed = self.placed()
        for sec in self.sections():
            name = sec["name"]
            if name not in srcs or name not in placed:
                continue
            try:
                d = self._sec_cut(sec)
            except Exception:
                continue
            out[name] = [[self._m2p(placed[name], p) for p in L]
                         for L in d["cut"]]
        return out

    def placed(self, views: dict | None = None) -> dict:
        """Per view: {sc, off, min, max, chains, rot, ctr} — the shared
        M94 placement (page = model * sc + off, y-up sheet mm). M96: the
        draughtsman's per-view moves ride on the assistant's slots. M109:
        a per-view display rotation (deg, about the view's own centre) is
        attached as `rot` (radians) + `ctr` (its page centre); it is a
        PRESENTATION transform only — the model-space chains/dims the
        numbers are measured from are never touched, and rot = 0 makes
        every map below the exact identity it always was. Pass `views` to
        reuse a fresh projection instead of redoing it."""
        views = self.views() if views is None else views
        placed = drawing.place(views, page=self.page,
                               moves=self.sheet().get("move"),
                               scales=self.sheet().get("vscale"))
        rots = self.sheet().get("rot") or {}
        for name, p in placed.items():
            try:
                deg = float(rots.get(name, 0.0))
            except (TypeError, ValueError):
                deg = 0.0
            p["rot"] = math.radians(deg)
            p["ctr"] = (p["off"][0] + 0.5 * (p["min"][0] + p["max"][0]),
                        p["off"][1] + 0.5 * (p["min"][1] + p["max"][1]))
        return placed

    # ---- M109: per-view rotation (a page-space spin about the view ctr) --
    @staticmethod
    def _spin(fr: dict, pt, neg: bool = False):
        """Rotate a page point about the view's centre by +/- its rot.
        A no-op (identity) when the view is unrotated."""
        a = fr.get("rot", 0.0)
        if not a:
            return (float(pt[0]), float(pt[1]))
        if neg:
            a = -a
        cx, cy = fr["ctr"]
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = pt[0] - cx, pt[1] - cy
        return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)

    def model_to_page(self, view: str, model_pt) -> tuple:
        """model (view 2D mm) -> DISPLAYED page mm, rotation applied last."""
        p = self.placed().get(view)
        if p is None:
            return (float(model_pt[0]), float(model_pt[1]))
        return self._m2p(p, model_pt)

    def page_to_model(self, view: str, page_pt) -> tuple:
        """DISPLAYED page mm -> model, de-rotating the click first so the
        dim tool sees true model coordinates whatever the view's angle."""
        p = self.placed().get(view)
        if p is None:
            return (float(page_pt[0]), float(page_pt[1]))
        return self._p2m(p, page_pt)

    @classmethod
    def _m2p(cls, fr: dict, model_pt) -> tuple:
        """model -> displayed page, straight from a placed frame (the hot
        paint path holds frames already, so skip the name lookup)."""
        sc, off = fr["sc"], fr["off"]
        return cls._spin(fr, (model_pt[0] * sc + off[0],
                              model_pt[1] * sc + off[1]))

    @classmethod
    def _p2m(cls, fr: dict, page_pt) -> tuple:
        """displayed page -> model: un-rotate about ctr, then the plain
        inverse of page = model * sc + off."""
        sc, off = fr["sc"], fr["off"]
        cx, cy = cls._spin(fr, page_pt, neg=True)
        return ((cx - off[0]) / sc, (cy - off[1]) / sc)

    def _cm(self, fr: dict, canon_page) -> tuple:
        """CANONICAL page (place()'s own space, pre-rotation) -> model."""
        sc, off = fr["sc"], fr["off"]
        return ((canon_page[0] - off[0]) / sc, (canon_page[1] - off[1]) / sc)

    def layout(self) -> dict:
        """Page-coordinate chains (mm, y-up, origin lower-left)."""
        return {v: p["chains"] for v, p in self.placed().items()}

    def frames(self) -> dict:
        """view -> (scale, off): the page point of model (0, 0) is off,
        so the CANONICAL map is page_to_model's inverse before rotation."""
        return {v: (p["sc"], p["off"]) for v, p in self.placed().items()}

    # ---- dimensions (M94) -------------------------------------------------
    def set_dim_mode(self, on: bool):
        self._dim_mode = bool(on)
        self._dim_first = None
        if on:
            self._balloon_mode = False        # M110: one tool at a time
            self._fit_mode = False            # M114
            self._sec_mode = False            # M136
            self._gdt_mode = False            # M144
            self._det_mode = False            # M201 R36: one tool
            self._bk_mode = False            # M201 R37: one tool
        self.update()

    def set_balloon_mode(self, on: bool):
        """M110: arm the balloon click — one click on a view pins the
        next item number there, in MODEL millimetres (the bubble
        travels with the body and survives a view spin, like a dim)."""
        self._balloon_mode = bool(on)
        if on:
            self._dim_mode = False
            self._dim_first = None
            self._fit_mode = False            # M114
            self._sec_mode = False            # M136
            self._gdt_mode = False            # M144
            self._det_mode = False            # M201 R36
            self._bk_mode = False            # M201 R37: one tool
        self.update()

    def set_fit_mode(self, on: bool):
        """M114: arm the fit-callout click — one click NEAR a dimension
        bubble opens the ISO 286 class picker for that dim."""
        self._fit_mode = bool(on)
        if on:
            self._dim_mode = False
            self._balloon_mode = False
            self._dim_first = None
            self._sec_mode = False            # M136
            self._gdt_mode = False            # M144
            self._det_mode = False            # M201 R36
            self._bk_mode = False            # M201 R37: one tool
        self.update()

    def set_gdt_mode(self, on: bool):
        """M144: arm the GD&T frame click — one click NEAR a dimension
        bubble opens the feature-control dialog for that dim. The
        frame rides the dim (model-space anchor), so it travels,
        spins and saves with its host for free."""
        self._gdt_mode = bool(on)
        if on:
            self._dim_mode = False
            self._dim_first = None
            self._balloon_mode = False
            self._fit_mode = False
            self._sec_mode = False
            self._det_mode = False            # M201 R36
            self._bk_mode = False            # M201 R37: one tool
        self.update()

    def set_section_mode(self, on: bool):
        """M136: arm the section-line tool — two clicks ON a parent
        view draw the cutting line where a draughtsman draws it, and
        the child section view (A-A, hatched cap, live like every
        other projection) arrives with it. Shift on the closing click
        flips which half the section keeps; a second line can be
        dragged without re-arming; click the button again to stand
        down."""
        self._sec_mode = bool(on)
        self._sec_pts, self._sec_view, self._sec_hover = [], None, None
        if on:
            self._dim_mode = False
            self._dim_first = None
            self._balloon_mode = False
            self._fit_mode = False
            self._gdt_mode = False            # M144
            self._det_mode = False            # M201 R36
            self._bk_mode = False            # M201 R37: one tool
            self.tool_note.emit("Section line: click where the cut "
                                "BEGINS on the top, front or right "
                                "view")
        self.update()

    def set_detail_mode(self, on: bool):
        """M201 R36 [Create a detail view, verbatim] "Click a point on
        the parent view to place the center point of the detail
        boundary" / "Drag the cursor away from the center point to
        adjust the size of the detail boundary and location of the
        identifier, then click to place them" / "Click to place the
        detail view on the sheet" - THREE beats, exactly as printed:
        click the centre (the boundary is born under the cursor),
        drag out the circle and click again (radius is INTERACTIVE -
        the page prints no radius field, so none is offered), move
        and click once more on bare paper (the view lands where the
        drafter put it, scale 2:1 at first - the page's own word is
        "enlarged"). The tool stays armed for the next detail, like
        the section line; click the button again to stand down."""
        self._det_mode = bool(on)
        self._det_view, self._det_c = None, None
        self._det_r, self._det_hover = None, None
        if on:
            self._dim_mode = False
            self._dim_first = None
            self._balloon_mode = False
            self._fit_mode = False
            self._gdt_mode = False
            self._sec_mode = False
            self._bk_mode = False            # M201 R37: one tool
            self.tool_note.emit("Detail: click the CENTER of the "
                                "area to enlarge, on a base or "
                                "section view")
        self.update()

    def set_breakout_mode(self, on: bool):
        """M201 R37 [Create breakout section views, verbatim] "Click to
        place the first point of the breakout section profile" / "Click
        to place the next point" / "Continue placing points as needed.
        The Check icon displays after you place at least 3 points" -
        the profile is the TOOL, not a dialog. The page's "Select the
        drawing view on which you want to create the breakout section"
        is answered by the FIRST CLICK being inside the view; every
        later click must stay on it. A double-click closes the profile
        (M138's own law: "a double-click is the FINISHING gesture - the
        vendor's polyline grammar") and so does a click back ON the
        first point once three stand - that marker ring is the page's
        Check made visible on paper. The dialog then asks the page's
        Section Depth: blank is the page's default, half of the
        design's depth, held live. The page names NO parent
        restriction (the detail's page did name one), so every view
        WITH MATERIAL answers - the iso included, which the core's
        gates prove cuts as true. One breakout per view, verbatim.
        The tool stays armed for the next view; click the button again
        to stand down."""
        self._bk_mode = bool(on)
        self._bk_pts, self._bk_view, self._bk_hover = [], None, None
        if on:
            self._dim_mode = False
            self._dim_first = None
            self._balloon_mode = False
            self._fit_mode = False
            self._gdt_mode = False
            self._sec_mode = False
            self._det_mode = False
            self.tool_note.emit("Breakout: click INSIDE the view to "
                                "break out, then place the profile's "
                                "points - double-click closes it once "
                                "it holds three")
        self.update()

    def _dim_disp(self, d) -> str:
        """Bubble text plus its ISO 286 callout, if the draughtsman
        pinned one (M114). Paper furniture: the geometry and the DXF
        stay nominal — a dimension carries truth, a class carries fit."""
        cls = d.get("fit")
        if not cls:
            return d["text"]
        try:
            return f"{d['text']} {fits.callout(d.get('fit_nom', 0.0), cls)}"
        except ValueError:                  # stale class on new geometry
            return f"{d['text']} {cls}"

    def _dim_at(self, page_pt, placed):
        """(view, index) of the dim whose leader passes nearest this
        sheet point (~14 screen px of slack); None when nothing is close."""
        best, best_d = None, 14.0 / max(self._zoom, 1e-6)
        for i, d in enumerate(self.sheet().get("dims", [])):
            fr = placed.get(d["view"])
            if fr is None:
                continue
            if d.get("diameter") or d.get("radius"):
                c = self.s2p(*self._m2p(fr, d.get("center", (0, 0))))
                rim = self.s2p(*self._m2p(fr, (float(d["center"][0])
                                               + float(d.get("r", 0.0)),
                                               float(d["center"][1]))))
                r_px = math.hypot(rim.x() - c.x(), rim.y() - c.y())
                dist = abs(math.hypot(page_pt[0] - c.x(),
                                      page_pt[1] - c.y()) - r_px)
            else:
                A = self.s2p(*self._m2p(fr, d["a"]))
                B = self.s2p(*self._m2p(fr, d["b"]))
                dx, dy = B.x() - A.x(), B.y() - A.y()
                L2 = dx * dx + dy * dy
                t = (0.0 if L2 < 1e-12 else
                     max(0.0, min(1.0, ((page_pt[0] - A.x()) * dx
                                        + (page_pt[1] - A.y()) * dy) / L2)))
                dist = math.hypot(page_pt[0] - (A.x() + t * dx),
                                  page_pt[1] - (A.y() + t * dy))
            if dist < best_d:
                best, best_d = (d["view"], i), dist
        return best

    def _view_at(self, page_pt, placed, slack=3.0):
        """Which view's frame (with draughting slack) holds this click?
        The click is in DISPLAYED sheet mm; un-rotate it into each view's
        canonical page space first (identity when that view is upright)."""
        best = None
        for name, p in placed.items():
            lo = np.asarray(p["min"]) - slack
            hi = np.asarray(p["max"]) + slack
            click = self._spin(p, page_pt, neg=True)
            q = np.asarray(click) - np.asarray(p["off"])
            if np.all(q >= lo) and np.all(q <= hi):
                # nearest frame centre wins if two overlap in the slack
                d = np.linalg.norm(q - 0.5 * (np.asarray(p["min"])
                                              + np.asarray(p["max"])))
                if best is None or d < best[1]:
                    best = (name, d)
        return best[0] if best else None

    def _snap(self, view, page_pt, placed, radius=3.0):
        """Grab the nearest projected chain endpoint (model space). Chains
        live in canonical page space, so the displayed click is un-rotated
        in and the answer mapped canonical -> model."""
        p = placed[view]
        q = np.asarray(self._spin(p, page_pt, neg=True))
        best, bd = q, radius
        for c in p["chains"]:
            for pt in c:
                d = float(np.linalg.norm(np.asarray(pt) - q))
                if d < bd:
                    best, bd = pt, d
        return self._cm(p, best) if bd < radius else self._cm(p, q)

    def rel_anchor(self, view: str, model_pt) -> list | None:
        """The endpoint as a fraction of the view's model-space extent
        (M94): (0, 0)..(1, 1) over the silhouette bbox. Fractions are
        what let a bubble FOLLOW a stretch — a raw (40, 0) can't know
        it was the RIGHT corner."""
        pv = self.placed().get(view)
        if pv is None:
            return None
        sc = pv["sc"]
        lo = (pv["min"][0] / sc, pv["min"][1] / sc)
        hi = (pv["max"][0] / sc, pv["max"][1] / sc)
        sx, sy = hi[0] - lo[0], hi[1] - lo[1]
        if sx < 1e-9 or sy < 1e-9:
            return None
        return [(model_pt[0] - lo[0]) / sx, (model_pt[1] - lo[1]) / sy]

    def resolve_dims(self, placed: dict | None = None):
        """The number can't lie and the arrow can't dangle: re-solve
        every bubble against the LIVE model (M94/M95). Linear bubbles
        re-derive endpoints from their view-fraction anchors; diameter
        bubbles re-FIND the projected circle nearest their centre and
        adopt its true radius (redrill 4->7 and the bubble reads
        Ø 14.00 by itself)."""
        if self.doc is None or not self.doc.drawings:
            return
        placed = placed if placed is not None else self.placed()
        views_cache: dict = {}
        arcs_cache: dict = {}
        srcs = self._sources()
        for g in self.doc.drawings:
            for d in g.get("dims", []):
                pv = placed.get(d["view"])
                if pv is None:
                    continue
                if d.get("diameter"):
                    key = d["view"]
                    if key not in views_cache:
                        chains = self.views().get(key, [])
                        views_cache[key] = [
                            fit for fit in (drawing.fit_circle(L)
                                            for L in chains)
                            if fit is not None]
                    want = d.get("center", d.get("a"))
                    best = None
                    for (cx, cy), r in views_cache[key]:
                        dd = math.dist((cx, cy), want)
                        if dd <= max(4.0, 0.6 * r) and (
                                best is None or dd < best[2]):
                            best = ((cx, cy), r, dd)
                    if best is not None:
                        (cx, cy), r, _ = best
                        d["center"] = [cx, cy]
                        d["r"] = r
                        ux, uy = d.get("dir", (1.0, 0.0))
                        d["a"] = [cx, cy]
                        d["b"] = [cx + ux * r, cy + uy * r]
                    d["text"] = "\u00d8 %.2f" % float(d.get("r", 0.0) * 2)
                    continue
                if d.get("radius"):
                    key = d["view"]
                    if key not in arcs_cache:
                        src = srcs.get(key)
                        arcs_cache[key] = (
                            drawing.find_arcs(self.views().get(key, []))
                            if src is not None
                            and src[1] in ("top", "front", "right")
                            else [])
                    want = d.get("center", d.get("a"))
                    best = None
                    for (cx, cy), r in arcs_cache[key]:
                        dd = math.dist((cx, cy), want)
                        if dd <= max(4.0, 0.6 * r) and (
                                best is None or dd < best[2]):
                            best = ((cx, cy), r, dd)
                    if best is not None:
                        (cx, cy), r, _ = best
                        d["center"] = [cx, cy]
                        d["r"] = r
                        ux, uy = d.get("dir", (1.0, 0.0))
                        d["a"] = [cx, cy]
                        d["b"] = [cx + ux * r, cy + uy * r]
                    d["text"] = "R %.2f" % float(d.get("r", 0.0))
                    continue
                sc = pv["sc"]
                lo = (pv["min"][0] / sc, pv["min"][1] / sc)
                hi = (pv["max"][0] / sc, pv["max"][1] / sc)
                for k in ("a", "b"):
                    r = d.get(k + "_rel")
                    if r is not None:
                        d[k] = [lo[0] + r[0] * (hi[0] - lo[0]),
                                lo[1] + r[1] * (hi[1] - lo[1])]
                d["text"] = f"{math.dist(d['a'], d['b']):.2f}"

    def _dim_click(self, ev):
        """Two endpoint clicks lay a linear bubble; ONE click on a
        projected circle lays a diameter (M95). Endpoints live in
        model space so the solid moving takes the dimension with it."""
        placed = self.placed()
        if not placed:
            return
        sheet = self.p2s(ev.position())
        view = self._view_at(sheet, placed)
        if view is None:
            self._dim_first = None
            self.update()
            return
        raw = self.page_to_model(view, sheet)
        for L in self.views().get(view, []):        # M95: a circle?
            fit = drawing.fit_circle(L)
            if fit is None:
                continue
            (cx, cy), r = fit
            if abs(math.dist(raw, (cx, cy)) - r) <= max(2.0, 0.35 * r):
                dx, dy = raw[0] - cx, raw[1] - cy
                dd = math.hypot(dx, dy) or 1.0
                self._dim_first = None
                self.dim_added.emit(
                    view, (cx, cy), (cx + dx / dd * r, cy + dy / dd * r),
                    {"diameter": True, "center": (cx, cy),
                     "dir": (dx / dd, dy / dd), "r": r})
                self.update()
                return
        src = self._sources().get(view)             # M103: an arc?
        if src is not None and src[1] in ("top", "front", "right"):
            for (cx, cy), r in drawing.find_arcs(
                    self.views().get(view, [])):
                if abs(math.dist(raw, (cx, cy)) - r) <= max(2.0, 0.35 * r):
                    dx, dy = raw[0] - cx, raw[1] - cy
                    dd = math.hypot(dx, dy) or 1.0
                    self._dim_first = None
                    self.dim_added.emit(
                        view, (cx, cy),
                        (cx + dx / dd * r, cy + dy / dd * r),
                        {"radius": True, "center": (cx, cy),
                         "dir": (dx / dd, dy / dd), "r": r})
                    self.update()
                    return
        pt = self._snap(view, sheet, placed)
        if self._dim_first is None or self._dim_first[0] != view:
            self._dim_first = (view, pt)
            self.update()
            return
        _v, a = self._dim_first
        self._dim_first = None
        if math.dist(a, pt) < 1e-9:
            self.update()
            return
        self.dim_added.emit(view, tuple(a), tuple(pt), {})
        self.update()

    # ---- paint ----------------------------------------------------------
    def _w(self, mm: float) -> float:
        """Frame/border ink: true mm on paper, 1-px floor on screen.
        The body strokes are already max(floor, mm*zoom) — inert at
        print zoom (§8 trap 1 self-heals); only raw 1-px pens and the
        cosmetic 0-width pen needed a voice for paper."""
        return mm * self._zoom if self._printing else max(1.0,
                                                          mm * self._zoom)

    def s2p(self, x: float, y: float) -> QPointF:
        """Sheet mm -> widget px: centred, y flipped (sheet y is up)."""
        w, h = self.width(), self.height()
        return QPointF(w / 2 + (x - self._center.x()) * self._zoom,
                       h / 2 - (y - self._center.y()) * self._zoom)

    def p2s(self, pos) -> tuple:
        """Widget px -> sheet mm (the exact inverse of s2p)."""
        w, h = self.width(), self.height()
        return ((pos.x() - w / 2) / self._zoom + self._center.x(),
                (h / 2 - pos.y()) / self._zoom + self._center.y())

    def _paint_zones(self, p: QPainter):
        """M201 R31 [DWG-REF-SHEET-SIZE, verbatim] the zone pair: 'To
        specify horizontal zones, type in a positive even number. The
        maximum value is 1000.'  The book is PROVEN silent on how zones
        look (164/164 crawl, cache/size31/live.md), so this ruler is
        OURS and says so: letters across the top, numbers up the left,
        short ticks at the cell breaks, no full gridlines.  Zones are
        Custom-only, exactly as the row heading prints it - a family
        member sheet shows none whatever its stored values."""
        zones = self.sheet().get("zones") or (0, 0)
        if not (zones[0] or zones[1]):
            return
        if not str(self.page).startswith("Custom"):
            return
        W, H = drawing.sheet_size(self.page)
        g = drawing.zone_grid(W, H, *zones)
        p.setPen(QPen(_BORDER, self._w(0.35)))
        for x in g["xs"]:
            p.drawLine(self.s2p(x, H), self.s2p(x, H - 3.0))
        for y in g["ys"]:
            p.drawLine(self.s2p(0, y), self.s2p(3.0, y))
        f = QFont(p.font())
        f.setPixelSize(max(9, int(4.0 * self._zoom)))
        p.setFont(f)
        # The label rects ride PIXELS, not millimetres: a mm-thick
        # rect is sub-pixel at fit zoom and Qt silently clips the
        # text away (the trap this gate's first run measured).
        for xc, lab in g["top"]:
            c = self.s2p(xc, H - 1.9)
            p.drawText(QRectF(c.x() - 9, c.y() - 9, 18, 18),
                       Qt.AlignCenter, lab)
        for yc, lab in g["left"]:
            c = self.s2p(2.1, yc)
            p.drawText(QRectF(c.x() - 9, c.y() - 9, 18, 18),
                       Qt.AlignCenter, lab)

    def paintEvent(self, ev):
        p = QPainter(self)
        self.paintPage(p)
        p.end()

    def paintPage(self, p: QPainter):
        p.setRenderHint(QPainter.Antialiasing)
        # M143: the page is a VIEW — desk, ring, ghosts. On paper the
        # device IS the sheet: fill paper edge to edge, no desk, no
        # dark 1-px ring (the trap the spike reproduced pixel-wise).
        p.fillRect(self.rect(), _PAPER if self._printing else _DESK)
        W, H = drawing.sheet_size(self.page)
        a = self.s2p(0, 0)
        b = self.s2p(W, H)
        sheet = QRectF(min(a.x(), b.x()), min(a.y(), b.y()),
                       abs(b.x() - a.x()), abs(b.y() - a.y()))
        p.setPen(Qt.NoPen if self._printing else QPen(_DESK_EDGE, 1))
        p.setBrush(_PAPER)                        # the paper
        p.drawRect(sheet)
        p.setBrush(Qt.NoBrush)
        self._paint_zones(p)                                 # M201 R31
        self._paint_block(p)                                 # M108 title block
        self._paint_bom(p)                                   # M110 parts list
        # views + section hatch + hidden ink + bubbles (one pass)
        views = self.views()
        placed = self.placed(views)
        p.setPen(QPen(_VIEW_EDGE, max(1.0, 0.35 * self._zoom)))
        for view in placed.values():
            for c in view["chains"]:
                if len(c) < 2:
                    continue
                pts = [self.s2p(*self._spin(view, (x, y))) for x, y in c]
                for i in range(len(pts) - 1):
                    p.drawLine(pts[i], pts[i + 1])
        cuts = self.cuts_page()
        if cuts:                        # M102: 45° hatch fills the wound
            p.setPen(QPen(_DETAIL,
                          max(0.6, 0.22 * self._zoom)))
            for loops in cuts.values():
                for ha, hb in drawing.hatch_region(loops):
                    p.drawLine(self.s2p(*ha), self.s2p(*hb))
        if self.doc is not None and self.doc.result is not None:
            hp = QPen(_HATCH, max(0.8, 0.28 * self._zoom))
            hp.setStyle(Qt.DashLine)
            p.setPen(hp)                        # M101: depth-hidden ink
            srcs = self._sources()
            h_off = self._hidden_off()          # M137: sections read
            for name in placed:                 # without back ink
                src = srcs.get(name)
                if src is None or name in h_off or src[0] is None:
                    continue
                for c in drawing.project_hidden(src[0], view=src[1]):
                    pts = [self.s2p(*self._m2p(placed[name], p2))
                           for p2 in c]
                    for i in range(len(pts) - 1):
                        p.drawLine(pts[i], pts[i + 1])
        # M147: the flat's bend centre-lines — the shop's dash pattern,
        # analytic ink from the stored segments (never re-fit)
        bend_segs = [(n, s) for n in placed for s in self.bends_page(n)]
        if bend_segs:
            bp = QPen(_DETAIL, max(0.8, 0.28 * self._zoom))
            bp.setStyle(Qt.DashLine)
            p.setPen(bp)
            for _, seg in bend_segs:
                p.drawLine(self.s2p(*seg[0]), self.s2p(*seg[1]))
        # SM3: the live flat's bend labels — words built from params,
        # riding the same dash like the shop's stamp beside the fold
        labels = self.bend_labels("Flat")
        if labels:
            f3 = p.font()
            f3.setPointSizeF(max(5.0, 6.2 * min(self._zoom, 2.0)))
            p.setFont(f3)
            p.setPen(QPen(_DETAIL))
            for at, txt in labels:
                pt = self.s2p(*at)
                w2 = p.fontMetrics().horizontalAdvance(txt) / 2.0
                p.drawText(QPointF(pt.x() - w2, pt.y()), txt)
        # M100: a view on an explicit scale wears its ratio as a caption;
        # M102: a section wears its letter (A-A · 1:2 when both);
        # M201 R36: a detail wears the page's printed triple in the
        # page's ORDER - "name, identifier, and scale" [DWG-REF-DRAWING-
        # VIEW-DLG] - on THIS house caption, not a competing one (the
        # boundary's edge bubble stays the identifier's page position,
        # the drag decided).
        vs = self.sheet().get("vscale") or {}
        sec_names = {s["name"] for s in self.sections()}
        dets = self._dets_by_name()
        if vs or sec_names or dets:
            f2 = p.font()
            f2.setPointSizeF(max(5.5, 7 * min(self._zoom, 2.0)))
            p.setFont(f2)
            for name, fr in placed.items():
                fac = vs.get(name)
                bits = []
                if name in sec_names:
                    bits.append(name)
                det = dets.get(name)
                if det is not None:
                    word = str(det.get("label") or "").strip()
                    if word:
                        bits.append(word)
                    bits.append(name)
                if fac:
                    bits.append(scale_label(float(fac)))
                if not bits:
                    continue
                # caption sits below the view centre; M109 rotates that
                # anchor with the view (its own spin, text stays upright)
                c0 = self.s2p(*self._spin(
                    fr, (fr["ctr"][0], fr["off"][1] + fr["min"][1] - 3.0)))
                p.setPen(QPen(_FAINT))
                p.drawText(QRectF(c0.x() - 80, c0.y(), 160,
                                  14 * self._zoom),
                           Qt.AlignHCenter | Qt.AlignTop,
                           " \u00b7 ".join(bits))
        self._draw_dims(p, placed)
        self._draw_balloons(p, placed)               # M110 item bubbles
        self._draw_hole_notes(p, placed)             # M129 table + marks
        self._draw_datum_ids(p, placed)              # M150 letters
        self._draw_section_lines(p, placed)          # M136 cutting lines
        self._draw_details(p, placed)                # M201 R36 boundaries
        self._draw_breakouts(p, placed)              # M201 R37 profiles

    # ---- publish (M143) ---------------------------------------------------
    _Q_PAGE = {"A3": QPageSize.A3, "A4": QPageSize.A4}

    def publish_pdf(self, path, indices=None, dpi=300) -> int:
        """The vendor's bundle law: every sheet — creation order —
        into ONE vector PDF. Reuse is a DEVICE SWAP, spike-pinned:
        shadow the three geometry getters, set _zoom = dpi/25.4 and
        _center to the sheet centre, and the existing mm coefficients
        become physical paper (print px floors go inert; the pt
        clamps are fine because a pt ON PAPER is physical). The
        writer's factory defaults — A4 portrait, 10 mm margins — get
        NO vote: an explicit QPageLayout (size, Landscape, zero
        margins) goes down per sheet BEFORE its paint, or Qt crops
        the sheet silently (reproduced pixel-wise, contract §3). One
        painter across the bundle, newPage() between sheets (FreeCAD
        rule: no begin/end mid-run); QPdfWriter finalises on
        destruction — PySide6 has no close(). The borrow is a loan:
        _printing hides the view chrome, the transient tools are
        stashed off the sheet and returned afterwards, and every
        swapped field lands back exactly where it was. Pages
        written."""
        if self.doc is None or not self.doc.drawings:
            raise ValueError("no sheets to publish")
        order = (list(range(len(self.doc.drawings))) if indices is None
                 else [int(i) for i in indices])
        if not order:
            raise ValueError("no sheets selected")
        try:
            open(path, "ab").close()               # FreeCAD's Windows
        except OSError as e:                       # lesson: pre-check
            raise OSError(f"cannot write {path}: {e}") from e
        writer = QPdfWriter(path)
        writer.setCreator("Tracer Studio")
        writer.setTitle(str(self.doc.drawings[order[0]].get("name",
                                                            "Drawing")))
        painter = None
        saved = (self.sheet_idx, self.page, self._zoom, self._center,
                 self._printing, self._dim_first, self._sec_pts,
                 self._sec_view, self._sec_hover, self._det_c, self._det_r,
                 self._det_hover, self._det_view,
                 self._bk_pts, self._bk_view, self._bk_hover)
        try:
            for k, idx in enumerate(order):
                self.sheet_idx = idx              # _block_meta reads it
                self.page = self.sheet().get("page", "A3")
                layout = QPageLayout(
                    self._Q_PAGE.get(self.page, QPageSize.A3),
                    QPageLayout.Landscape, QMarginsF(0, 0, 0, 0))
                writer.setPageLayout(layout)
                writer.setResolution(dpi)
                px = layout.fullRectPixels(dpi)
                self.width = lambda: px.width()   # the shadow swap:
                self.height = lambda: px.height()  # s2p reads only
                self.rect = lambda: QRectF(0, 0, px.width(), px.height())
                #                                            these five
                self._center = QPointF(*[v / 2.0 for v in
                         drawing.sheet_size(self.page)])
                self._zoom = dpi / 25.4
                self._printing = True
                self._dim_first = None            # ghosts stay off
                self._sec_pts = []                # the sheet; the
                self._sec_view = None             # user keeps them
                self._sec_hover = None            # after
                self._det_c = None                #   the print, and
                self._det_r = None                #   pick the same
                self._det_hover = None            #   ghost state back
                self._det_view = None             #   when they do
                self._bk_pts = []                 # R37: the breakout
                self._bk_view = None              #   ghost stays off
                self._bk_hover = None             #   the sheet too
                if painter is None:
                    painter = QPainter(writer)
                else:
                    writer.newPage()    # PySide6 puts newPage on the
                    #        device; same rule: one painter, no end mid-run
                self.paintPage(painter)
        finally:
            if painter is not None:
                painter.end()
            (self.sheet_idx, self.page, self._zoom, self._center,
             self._printing, self._dim_first, self._sec_pts,
             self._sec_view, self._sec_hover, self._det_c, self._det_r,
             self._det_hover, self._det_view,
             self._bk_pts, self._bk_view, self._bk_hover) = saved
            for gone in ("width", "height", "rect"):
                self.__dict__.pop(gone, None)     # unshadow the widget
        return len(order)

    def _draw_details(self, p, placed):
        """M201 R36: the boundary circle rides its PARENT (stored in
        parent MODEL xy, so a nudged or spun parent carries the crop
        with it - the cookie re-clips where the part now sits); the
        IDENTIFIER bubble stands at the circle's edge in the drag's
        own direction, the page's "location of the identifier" made
        real; and the child carries the label in the page's printed
        order - [DWG-REF-DRAWING-VIEW-DLG] name, identifier and scale
        - under the enlarged view. A parent that walked off the sheet
        keeps its ink absent, not invented (fr None: skip). While the
        tool is mid-drag the same circle draws as a rubber ghost, so
        the drafter sees the boundary they are pulling before it
        exists."""
        dets = self.details()
        if not dets and self._det_c is None:
            return
        p.save()
        f = QFont(p.font())
        f.setPixelSize(max(9, int(4.2 * self._zoom)))
        for det in dets:
            fr = placed.get(det.get("parent"))
            if fr is None:
                continue
            ctr = np.asarray(self._m2p(fr, det["c"]), float)
            rr = float(det["r"]) * fr["sc"]          # model mm -> page mm
            pen = QPen(_VIEW_EDGE, max(0.8, 0.24 * self._zoom))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(self.s2p(*ctr), rr * self._zoom,
                          rr * self._zoom)
            a = float(det.get("a", 0.7853981633974483))
            bub = ctr + np.array([math.cos(a), math.sin(a)]) * (rr + 2.6)
            c = self.s2p(*bub)
            rpx = max(9, int(2.2 * self._zoom))
            p.setBrush(_PAPER)
            p.drawEllipse(c, rpx, rpx)
            p.setPen(QPen(_VIEW_EDGE, max(0.9, 0.22 * self._zoom)))
            p.setFont(f)
            p.drawText(QRectF(c.x() - rpx, c.y() - rpx, 2 * rpx, 2 * rpx),
                       Qt.AlignCenter, str(det["name"]))
        if self._det_mode and self._det_c is not None \
                and self._det_view in placed:
            fr = placed[self._det_view]
            ctr = np.asarray(self._m2p(fr, self._det_c), float)
            tip = (np.asarray(self._det_hover, float)
                   if self._det_hover is not None else None)
            p.setPen(QPen(_DETAIL, max(0.8, 0.2 * self._zoom),
                          Qt.DashLine))
            if self._det_r is not None:
                rr = self._det_r * fr["sc"]
                p.drawEllipse(self.s2p(*ctr), rr * self._zoom,
                              rr * self._zoom)
            elif tip is not None:
                rr = float(np.hypot(*(tip - ctr))) * self._zoom
                p.drawEllipse(self.s2p(*ctr), rr, rr)
                p.drawLine(self.s2p(*ctr), self.s2p(*tip))
        p.restore()

    def _draw_breakouts(self, p, placed):
        """M201 R37: the CLOSED profile rides its view (stored in that
        view's MODEL xy - a nudged view carries the cut with it, the
        prism re-sinks where the part now sits). The boundary is the
        only furniture on paper: [Create breakout section views] "The
        view displays a defined area of removed material" - the removed
        area's ink is the PROJECTION'S OWN (the cut floor and walls
        arrive as live edges through _sources), never a painted fake.
        While the tool holds points the polyline draws open to the
        cursor, and once three stand a ring marks the first point: the
        page's Check, made clickable on the paper itself."""
        bks = self.breakouts()
        if not bks and not self._bk_pts:
            return
        p.save()
        pen = QPen(_VIEW_EDGE, max(0.8, 0.24 * self._zoom))
        p.setBrush(Qt.NoBrush)
        for bk in bks:
            fr = placed.get(bk.get("view"))
            if fr is None or len(bk.get("loop") or []) < 3:
                continue
            qs = [self.s2p(*np.asarray(self._m2p(fr, q), float))
                  for q in bk["loop"]]
            p.setPen(pen)
            for a, b in zip(qs, qs[1:] + qs[:1]):
                p.drawLine(a, b)
        if self._bk_mode and self._bk_pts and self._bk_view in placed:
            fr = placed[self._bk_view]
            qs = [self.s2p(*np.asarray(self._m2p(fr, q), float))
                  for q in self._bk_pts]
            p.setPen(QPen(_DETAIL, max(0.8, 0.2 * self._zoom),
                          Qt.DashLine))
            for a, b in zip(qs, qs[1:]):
                p.drawLine(a, b)
            if self._bk_hover is not None and qs:
                p.drawLine(qs[-1], self.s2p(*np.asarray(self._bk_hover,
                                                        float)))
            if len(qs) >= 3:                    # the Check, on the ring
                c = qs[0]
                rpx = max(6, int(1.6 * self._zoom))
                p.setBrush(_PAPER)
                p.drawEllipse(c, rpx, rpx)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, rpx, rpx)
        p.restore()

    def _draw_section_lines(self, p, placed):
        """M136: the cutting line rides its parent view — thin long
        dashes along the cut, thick end caps, arrowheads standing off
        toward the kept side, the letter past each end: the drafter's
        sentence 'look here, from this side'. Entries store parent
        MODEL xy (the line travels with a nudged view, like dims and
        balloons); the page map is place()'s own, so the ink follows."""
        line_secs = [s for s in self.sections() if "parent" in s]
        if not line_secs and not (self._sec_pts and self._sec_view):
            return
        p.save()
        for sec in line_secs:
            fr = placed.get(sec["parent"])
            if fr is None:
                continue
            pts = sec.get("pts") or [sec["p0"], sec["p1"]]
            qs = [np.asarray(self._m2p(fr, q), float) for q in pts]
            qs = [q for i, q in enumerate(qs)
                  if i == 0 or np.hypot(*(q - qs[i - 1])) > 1e-9]
            if len(qs) < 2:
                continue
            u0 = qs[1] - qs[0]
            u0 /= max(float(np.hypot(*u0)), 1e-12)
            u1 = qs[-1] - qs[-2]
            u1 /= max(float(np.hypot(*u1)), 1e-12)
            n2 = np.array([u0[1], -u0[0]])    # eye = 90 CW of first leg
            if sec.get("flip"):
                n2 = -n2
            ext = 3.0 * fr["sc"]              # page overhang: 3 model mm
            self._cut_line_ink(p, [qs[0] - u0 * ext] + qs[1:-1]
                               + [qs[-1] + u1 * ext], n2,
                               str(sec["name"][0]))
        if self._sec_pts and self._sec_view in placed:
            fr = placed[self._sec_view]
            qs = [np.asarray(self._m2p(fr, q), float)
                  for q in self._sec_pts]
            tip = (np.asarray(self._sec_hover, float)
                   if self._sec_hover is not None
                   else qs[-1])
            if np.hypot(*(tip - qs[-1])) > 1e-9:
                qs = qs + [tip]
            p.setPen(QPen(_DETAIL, max(0.8, 0.2 * self._zoom),
                          Qt.DashLine))
            for a, b in zip(qs, qs[1:]):          # the whole chain with
                p.drawLine(self.s2p(*a), self.s2p(*b))   # a rubber tip
        p.restore()

    def _cut_line_ink(self, p, qs, n2, letter):
        """One finished cutting line in canonical page mm: dash body
        along the CHAIN (two points = M136's straight; three or more
        = M138's step — the standards draw no line where the plane
        turns), thick caps square across the two OUTER ends, open-V
        arrows toward the kept side on the outer legs, letter past
        each end."""
        if len(qs) < 2:
            return
        z = self._zoom
        p.setPen(QPen(_VIEW_EDGE, max(0.7, 0.18 * z), Qt.DashLine,
                      Qt.FlatCap))
        for a, b in zip(qs, qs[1:]):
            p.drawLine(self.s2p(*a), self.s2p(*b))
        p.setPen(QPen(_VIEW_EDGE, max(1.6, 0.5 * z), Qt.SolidLine,
                      Qt.RoundCap))
        cap = 2.5                                        # page-mm caps
        ends = [(qs[0], qs[1] - qs[0]), (qs[-1], qs[-1] - qs[-2])]
        for e, d in ends:
            d = d / max(float(np.hypot(*d)), 1e-12)
            p.drawLine(self.s2p(*(e - d * cap)),
                       self.s2p(*(e + d * cap)))
        p.setPen(QPen(_VIEW_EDGE, max(1.0, 0.3 * z)))
        ah = 3.2                                         # arrow height
        if len(qs) == 2:
            spots = [(qs[0], qs[1], 0.3), (qs[0], qs[1], 0.7)]
        else:                       # one arrow per OUTER leg (the M136
            spots = [(qs[0], qs[1], 0.5),                 # straight law:
                     (qs[-2], qs[-1], 0.5)]               # a pair astride
        for a, b, t in spots:
            d = b - a
            d = d / max(float(np.hypot(*d)), 1e-12)
            foot = a + (b - a) * t
            tip = foot + n2 * ah
            p.drawLine(self.s2p(*foot), self.s2p(*tip))
            for wing in (tip - n2 * 1.0 + d * 1.2,
                         tip - n2 * 1.0 - d * 1.2):
                p.drawLine(self.s2p(*tip), self.s2p(*wing))
        f2 = p.font()
        f2.setPointSizeF(max(6.5, 8.0 * min(z, 2.0)))
        p.setFont(f2)
        p.setPen(QPen(_VIEW_EDGE, self._w(0.18)))   # M143: the
        for e, d, sgn in ((qs[0], qs[1] - qs[0], -1.0),
                          (qs[-1], qs[-1] - qs[-2], 1.0)):
            d = d / max(float(np.hypot(*d)), 1e-12)
            at = self.s2p(*(e + d * sgn * 5.0 + n2 * 2.0))
            p.drawText(QRectF(at.x() - 12, at.y() - 10, 24, 20),
                       Qt.AlignCenter, letter)

    def _block_meta(self) -> dict:
        """Derived title-block strings the canvas (not the sheet) knows:
        fitted print scale and sheet position within the drawing set."""
        n = max(1, len(self.doc.drawings)) if self.doc else 1
        sc = max(1, round(1 / self.page_scale())) if self.views() else 1
        return {"scale": f"1:{sc}", "sheet": f"{self.sheet_idx + 1} / {n}"}

    def _paint_block(self, p: QPainter):
        """Draw the ISO title block bottom-right from the pure resolver.
        It's sheet furniture, not view geometry: it paints here (and thus
        into the PNG) but never enters the DXF line stream — and it saves /
        restores the painter so its pen + font can't leak into the views,
        bubbles and section hatch painted after it."""
        p.save()
        tb = drawing.title_block(self.sheet(), meta=self._block_meta(),
                                 page=self.page)
        p.setPen(QPen(_BORDER, self._w(0.35)))
        for (ax, ay), (bx, by) in tb["lines"]:
            p.drawLine(self.s2p(ax, ay), self.s2p(bx, by))
        p.setPen(QPen(_SHEET))
        self._paint_cells(p, tb["cells"])
        p.restore()

    def _paint_cells(self, p: QPainter, cells):
        """Paint resolver cells inside their column boxes (shared by the
        title block, M108, and the parts list, M110): text is clipped to
        its own box so a long description can never bleed across a
        divider, and the bold flag marks a heading row."""
        for c in cells:
            if not c["text"]:
                continue
            top = self.s2p(c["xa"], c["y"] + c["size"])
            bot = self.s2p(c["xb"], c["y"] - c["size"])
            box = QRectF(min(top.x(), bot.x()), min(top.y(), bot.y()),
                         abs(bot.x() - top.x()), abs(bot.y() - top.y()))
            f = p.font()
            f.setPixelSize(max(5, int(c["size"] * self._zoom)))
            f.setBold(bool(c.get("bold")))
            p.setFont(f)
            al = {"l": Qt.AlignLeft, "c": Qt.AlignHCenter,
                  "r": Qt.AlignRight}[c["align"]]
            p.drawText(box.adjusted(2, 0, -2, 0), al | Qt.AlignVCenter,
                       c["text"])

    def _paint_bom(self, p: QPainter):
        """The parts list (M110, ISO 7573): rows are DERIVED from the
        document at paint time — bodies, volumes, materials — so the
        list can no more go stale than the title block's scale. Docks
        on the block's top edge; paper-only, like the block: the DXF
        line stream never sees it."""
        if self.doc is None or not self.doc.drawings:
            return
        if not self.sheet().get("bom"):
            return
        p.save()
        rows = drawing.parts_list(self.doc.body_list(),
                                  self.doc.body_solids())
        tb = drawing.title_block(self.sheet(), meta=self._block_meta(),
                                 page=self.page)
        t = drawing.parts_list_table(rows, tb["rect"], page=self.page)
        p.setPen(QPen(_BORDER, self._w(0.35)))
        for (ax, ay), (bx, by) in t["lines"]:
            p.drawLine(self.s2p(ax, ay), self.s2p(bx, by))
        if t["overflow"]:
            x0, y0, w, h = t["rect"]
            t["cells"].append({"text": f"… {t['overflow']} more",
                               "xa": x0, "xb": x0 + w,
                               "y": y0 + h + 2.5, "size": 1.6,
                               "align": "l"})
        p.setPen(QPen(_SHEET))
        self._paint_cells(p, t["cells"])
        p.restore()

    def _draw_balloons(self, p: QPainter, placed: dict):
        """ISO 6433 item references (M110): a leader dot on the part,
        a circle, the item number — anchored in MODEL millimetres, so
        a spun or dragged view carries its balloons like dimensions
        do. Numbers speak in sheet px, staying upright and legible."""
        g = self.sheet()
        groups = g.get("balloons") or {}
        if not groups:
            return
        f = p.font()
        f.setPixelSize(max(8, int(5.0 * self._zoom)))
        p.setFont(f)
        r = max(6.0, 3.4 * self._zoom)
        for view, items in groups.items():
            fr = placed.get(view)
            if fr is None:
                continue
            for b in items:
                ax, ay = self._m2p(fr, (b["x"], b["y"]))
                a = self.s2p(ax, ay)
                cx, cy = a.x() + 2 * r, a.y() - 2 * r
                c = QPointF(cx, cy)
                p.setPen(QPen(_SHEET,
                              max(1.0, 0.35 * self._zoom)))
                p.drawLine(a, QPointF(cx - r * 0.8, cy + r * 0.8))
                p.setBrush(_PAPER)
                p.drawEllipse(c, r, r)
                p.setBrush(Qt.NoBrush)
                p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r),
                           Qt.AlignCenter, str(b.get("item", "")))

    def _draw_hole_notes(self, p: QPainter, placed: dict):
        """M129: the hole story told from metadata — a counted table in
        the sheet's free upper-left corner, a centreline cross and an
        item bubble on every hole, in the view you look DOWN the bore
        from.  Rows are HoleFeature fields, never mesh chords (a
        24-gon under-reads a diameter), so the notes are as un-stale
        as the BOM — and paper-only like it.  Opt-out is the sheet's
        hole_notes flag; default ON: a holed part drawn without hole
        notes is the surprise."""
        if self.doc is None or not self.doc.drawings:
            return
        if not self.sheet().get("hole_notes", True):
            return
        rows = drawing.hole_rows(self.doc)
        if not rows:
            return
        marks = drawing.hole_marks(self.doc)     # may be empty for
        p.save()                                 # steeply tilted bores
        f = p.font()
        f.setPixelSize(max(8, int(5.0 * self._zoom)))
        p.setFont(f)
        rb = max(6.0, 3.4 * self._zoom)
        for view, items in marks.items():
            fr = placed.get(view)
            if fr is None:
                continue
            # M201 R35 [DWG-REF-DRAWING-VIEW-DLG, verbatim] "Automated
            # Center Marks and Center Lines: Automatically create center
            # lines and center marks for all holes in a view." / "Hole:
            # Creates a center mark for hole features." - the page puts
            # that control IN THIS DIALOG ("...or later by double-clicking
            # the view"), so the cross answers the view's own answer.
            # Rest is ON (the page prints zero defaults; M129 shipped the
            # cross ON). Only the MARK retires: the item bubble and the
            # hole table are different families' ink and stay put.
            on = (self.sheet().get("hmarks") or {}).get(view, True)
            for m in items:
                a = self.s2p(*self._m2p(fr, (m["x"], m["y"])))
                rp = m["r"] * fr["sc"] * self._zoom
                L = rp + max(4.0, 1.2 * self._zoom)   # run out past
                if on:                                    # the rim, as
                    p.setPen(QPen(_SHEET, max(0.8, 0.25 * self._zoom),
                                  Qt.DashDotLine))         # centrelines do
                    p.drawLine(QPointF(a.x() - L, a.y()),
                               QPointF(a.x() + L, a.y()))
                    p.drawLine(QPointF(a.x(), a.y() - L),
                               QPointF(a.x(), a.y() + L))
                cx, cy = a.x() - 2 * rb, a.y() - 2 * rb
                c = QPointF(cx, cy)                     # bubble up-LEFT:
                p.setPen(QPen(_SHEET,                   # balloons own
                              max(1.0, 0.35 * self._zoom)))
                p.drawLine(QPointF(a.x() - rp * 0.707, # the up-right
                                   a.y() - rp * 0.707),
                           QPointF(cx + rb * 0.8, cy + rb * 0.8))
                p.setBrush(_PAPER)
                p.drawEllipse(c, rb, rb)
                p.setBrush(Qt.NoBrush)
                p.drawText(QRectF(c.x() - rb, c.y() - rb,
                                  2 * rb, 2 * rb),
                           Qt.AlignCenter, str(m["item"]))
        t = drawing.hole_table(rows, page=self.page)
        p.setPen(QPen(_BORDER, self._w(0.35)))
        for (ax, ay), (bx, by) in t["lines"]:
            p.drawLine(self.s2p(ax, ay), self.s2p(bx, by))
        if t["overflow"]:
            x0, y0, w, h = t["rect"]
            t["cells"].append({"text": f"… {t['overflow']} more",
                               "xa": x0, "xb": x0 + w,
                               "y": y0 - 2.5, "size": 1.6,
                               "align": "l"})
        p.setPen(QPen(_SHEET))
        self._paint_cells(p, t["cells"])
        p.restore()

    def datum_ids_page(self) -> list:
        """M150: the datum identifiers in SHEET-MM page coords —
        (letter, page-pt, leader page-pt or None). Anchors live in
        MODEL space (the dims' trick): the stamp travels, spins and
        saves for free. Legacy sheets carry no "datums" key and
        answer empty — the byte-identical paper law."""
        out = []
        for e in self.sheet().get("datums", []):
            fr = self.placed().get(e["view"])
            if fr is None:
                continue
            pt = self._m2p(fr, e["anchor"][:2])
            lead = (self._m2p(fr, e["leader"][:2])
                    if e.get("leader") else None)
            out.append((str(e["letter"]), (float(pt[0]), float(pt[1])),
                        None if lead is None else (float(lead[0]),
                                                   float(lead[1]))))
        return out

    def _draw_datum_ids(self, p: QPainter, placed: dict):
        """Letter-in-a-square with a leader — the vendor separates
        the identifier from the frame, so it is its own annotation:
        the FIRST paper object that is not a dim (opt-in key, black
        sheet ink, not the dims' red)."""
        ids = self.datum_ids_page()
        if not ids:
            return
        p.save()
        f = p.font()
        f.setPixelSize(max(8, int(5.2 * self._zoom)))
        p.setFont(f)
        pen = QPen(_SHEET, max(0.9, 0.3 * self._zoom))
        p.setPen(pen)
        for letter, (px, py), lead in ids:
            a = self.s2p(px, py)
            if lead is not None:
                lq = self.s2p(*lead)
                p.drawLine(a, lq)
                cx, cy = lq.x(), lq.y()
            else:
                cx, cy = a.x(), a.y()
            half = max(3.4, 2.2 * self._zoom)
            p.setBrush(_PAPER)                     # the square kills
            p.drawRect(QRectF(cx - half, cy - half,                # the
                              2 * half, 2 * half))                 # ink
            p.setBrush(Qt.NoBrush)
            p.drawText(QRectF(cx - half, cy - half,
                              2 * half, 2 * half),
                       Qt.AlignCenter, letter)
        p.restore()

    def _draw_dims(self, p: QPainter, placed: dict):
        """Draughtsman bubbles: extension lines, arrowed dimension line
        offset away from the view, and the live millimetre text in a
        knocked-out gap.  Endpoints live in MODEL space, so the solid
        moving carries the dimension with it (M94)."""
        if self.doc is None or not self.doc.drawings:
            return
        g = self.sheet()                           # M96: this sheet only
        dims = g.get("dims", [])
        self.resolve_dims(placed)
        ink = QPen(_RED, max(1.0, 0.5 * self._zoom))
        f = p.font()
        f.setPointSizeF(max(6.5, 9 * min(self._zoom, 2.0)))
        if self._dim_first is not None:                   # pending pick
            view = placed.get(self._dim_first[0])
            if view is not None:
                q = self.s2p(*self._m2p(view, self._dim_first[1]))
                p.setPen(QPen(_SELECT, 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(q, 5, 5)
        for d in dims:
            view = placed.get(d["view"])
            if view is None:
                continue
            if d.get("diameter"):                          # M95 Ø style
                self._draw_diameter(p, f, ink, d, view)
                continue
            if d.get("radius"):            # M103: R, centre to rim
                self._draw_radius(p, f, ink, d, view)
                continue
            A = self.s2p(*self._m2p(view, d["a"]))
            B = self.s2p(*self._m2p(view, d["b"]))
            v = B - A
            L = math.hypot(v.x(), v.y())
            if L < 1e-6:
                continue
            u = QPointF(v.x() / L, v.y() / L)             # along the dim
            n = QPointF(-u.y(), u.x())                    # perpendicular
            # offset the dim line AWAY from the view's centre, draughting-
            # like, then lay extension lines and arrows along it.  ctr is
            # the view centre; a spin (M109) leaves it fixed, so a plain
            # s2p of it is correct at any angle.
            ctr = self.s2p(*view["ctr"])
            mid = QPointF(0.5 * (A.x() + B.x()), 0.5 * (A.y() + B.y()))
            if ((mid.x() - ctr.x()) * n.x()
                    + (mid.y() - ctr.y()) * n.y()) < 0:     # side test
                n = QPointF(-n.x(), -n.y())
            od = max(12.0, 4.0 * self._zoom)              # dim-line offset
            A2 = QPointF(A.x() + n.x() * od, A.y() + n.y() * od)
            B2 = QPointF(B.x() + n.x() * od, B.y() + n.y() * od)
            p.setPen(ink)
            p.drawLine(A, QPointF(A2.x() + n.x() * 3,
                                  A2.y() + n.y() * 3))    # ext lines
            p.drawLine(B, QPointF(B2.x() + n.x() * 3,
                                  B2.y() + n.y() * 3))
            p.drawLine(A2, B2)
            for tip, sgn in ((A2, 1.0), (B2, -1.0)):      # arrowheads
                base = QPointF(tip.x() + u.x() * 7 * sgn,
                               tip.y() + u.y() * 7 * sgn)
                w1 = QPointF(base.x() + n.x() * 1.8, base.y() + n.y() * 1.8)
                w2 = QPointF(base.x() - n.x() * 1.8, base.y() - n.y() * 1.8)
                path = QPainterPath()
                path.moveTo(tip)
                path.lineTo(w1)
                path.lineTo(w2)
                path.closeSubpath()
                p.setBrush(_RED)
                p.setPen(Qt.NoPen)
                p.drawPath(path)
                p.setPen(ink)
                p.setBrush(Qt.NoBrush)
            fm = p.fontMetrics()
            disp = self._dim_disp(d)
            br = fm.boundingRect(disp)
            gap = QRectF(mid.x() + n.x() * od - br.width() / 2 - 3,
                         mid.y() + n.y() * od - br.height() / 2 - 2,
                         br.width() + 6, br.height() + 4)
            p.setPen(Qt.NoPen)
            p.setBrush(_PAPER)                 # knockout gap
            p.drawRect(gap)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(_RED))
            p.setFont(f)
            p.drawText(gap, Qt.AlignCenter, disp)
            self._draw_gdt(p, d, gap)        # M144: frame + basic box

    def _draw_diameter(self, p: QPainter, f, ink, d, fr):
        """A Ø bubble spans the whole circle: from the far rim through
        the centre to the near rim, arrowheads at both, text in the
        middle. Endpoints come from centre + dir*r, so the span follows
        the live circle resolve_dims just re-found (M109: the whole span
        is mapped through _m2p so a spun view carries its bubble with
        it, while the text stays upright)."""
        cx, cy = d["a"]
        ux, uy = d.get("dir", (1.0, 0.0))
        r = float(d.get("r", math.dist(d["a"], d["b"])))
        if r < 1e-9:
            return
        far = self.s2p(*self._m2p(fr, (cx - ux * r, cy - uy * r)))
        near = self.s2p(*self._m2p(fr, (cx + ux * r, cy + uy * r)))
        p.setPen(ink)
        p.drawLine(far, near)
        v = near - far
        L = math.hypot(v.x(), v.y())
        if L < 1e-6:
            return
        u = QPointF(v.x() / L, v.y() / L)
        n = QPointF(-u.y(), u.x())
        for tip, sgn in ((far, 1.0), (near, -1.0)):
            base = QPointF(tip.x() + u.x() * 7 * sgn,
                           tip.y() + u.y() * 7 * sgn)
            path = QPainterPath()
            path.moveTo(tip)
            path.lineTo(QPointF(base.x() + n.x() * 1.8,
                                base.y() + n.y() * 1.8))
            path.lineTo(QPointF(base.x() - n.x() * 1.8,
                                base.y() - n.y() * 1.8))
            path.closeSubpath()
            p.setBrush(_RED)
            p.setPen(Qt.NoPen)
            p.drawPath(path)
            p.setPen(ink)
            p.setBrush(Qt.NoBrush)
        fm = p.fontMetrics()
        disp = self._dim_disp(d)
        br = fm.boundingRect(disp)
        mid = QPointF(0.5 * (far.x() + near.x()),
                      0.5 * (far.y() + near.y()))
        gap = QRectF(mid.x() - br.width() / 2 - 3,
                     mid.y() - br.height() / 2 - 2,
                     br.width() + 6, br.height() + 4)
        p.setPen(Qt.NoPen)
        p.setBrush(_PAPER)
        p.drawRect(gap)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_RED))
        p.setFont(f)
        p.drawText(gap, Qt.AlignCenter, disp)
        self._draw_gdt(p, d, gap)                        # M144

    def _draw_radius(self, p: QPainter, f, ink, d, fr):
        """M103: an R leader runs from the arc's centre out to the rim,
        one arrowhead on the rim, text on the paper just past the tip.
        Endpoints ride centre + dir*r so the leader follows the live
        arc resolve_dims re-found (a redrilled scallop moves alone).
        M109 maps both through _m2p so a spun view carries its leader."""
        cx, cy = d["a"]
        ux, uy = d.get("dir", (1.0, 0.0))
        r = float(d.get("r", math.dist(d["a"], d["b"])))
        if r < 1e-9:
            return
        centre = self.s2p(*self._m2p(fr, (cx, cy)))
        rim = self.s2p(*self._m2p(fr, (cx + ux * r, cy + uy * r)))
        p.setPen(ink)
        p.drawLine(centre, rim)
        v = rim - centre
        L = math.hypot(v.x(), v.y())
        if L < 1e-6:
            return
        u = QPointF(v.x() / L, v.y() / L)
        n = QPointF(-u.y(), u.x())
        base = QPointF(rim.x() - u.x() * 7, rim.y() - u.y() * 7)
        path = QPainterPath()
        path.moveTo(rim)
        path.lineTo(QPointF(base.x() + n.x() * 1.8, base.y() + n.y() * 1.8))
        path.lineTo(QPointF(base.x() - n.x() * 1.8, base.y() - n.y() * 1.8))
        path.closeSubpath()
        p.setBrush(_RED)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        fm = p.fontMetrics()
        disp = self._dim_disp(d)
        br = fm.boundingRect(disp)
        mid = QPointF(0.5 * (centre.x() + rim.x()) + n.x() * 9,
                      0.5 * (centre.y() + rim.y()) + n.y() * 9)
        gap = QRectF(mid.x() - br.width() / 2 - 3,
                     mid.y() - br.height() / 2 - 2,
                     br.width() + 6, br.height() + 4)
        p.setPen(Qt.NoPen)
        p.setBrush(_PAPER)
        p.drawRect(gap)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_RED))
        p.setFont(f)
        p.drawText(gap, Qt.AlignCenter, disp)
        self._draw_gdt(p, d, gap)                        # M144

    # ---- GD&T frames (M144) ------------------------------------------------
    def _dim_font(self) -> QFont:
        """The dim/bubble typeface in ONE place: the FCF cell widths
        must measure the same metrics the host text paints with."""
        f = QFont(self.font())
        f.setPointSizeF(max(6.5, 9.0 * min(self._zoom, 2.0)))
        return f

    def _gdt_cells_widths(self, gap, frame) -> list[float]:
        """Honest cell widths for one frame under this host text:
        the SYMBOL cell is the square box height, the value cell is
        its advance plus padding, datum cells at least 0.75 box.
        Shared by painter and gate — the rect is always the sum."""
        fm = QFontMetrics(self._dim_font())
        box = 1.5 * max(8.0, gap.height() - 4.0)      # 1.5 h_text law
        widths = []
        for c in gdt.gdt_cells(frame):
            if c["kind"] == "glyph":
                widths.append(box)
            elif c["kind"] == "text":
                widths.append(fm.horizontalAdvance(c["s"]) + 0.5 * box)
            elif c["kind"] == "proj":
                # the CIRCLE belongs to the width math (one-source
                # law): P inside it, height beside it, nothing eats
                # the neighbour's compartment.
                rr = max(2.5, 0.5 * fm.horizontalAdvance("P")
                         + 0.10 * box)
                widths.append(2 * rr + fm.horizontalAdvance(
                    c["s"][2:]) + 0.3 * box)
            else:
                widths.append(max(0.75 * box,
                                  fm.horizontalAdvance(c["s"])
                                  + 0.4 * box))
        return widths

    def _paint_glyph(self, p, key, cell, box):
        """Unit box -> cell, y running DOWN like the page (the §1
        specs are authored in screen orientation — the perpendicular
        bar sits at y=0.90). PAINTED shapes: the probe verified the
        whole U+2300 block is TOFU on real paper fonts."""
        side = (2.0 / 3.0) * box
        ox = cell.center().x() - side / 2.0
        oy = cell.center().y() - side / 2.0
        for op in gdt.GLYPHS[key]:
            if op[0] == "poly":
                pts = [QPointF(ox + x * side, oy + y * side)
                       for x, y in op[1]]
                if len(op) > 2 and op[2]:
                    path = QPainterPath()
                    path.moveTo(pts[0])
                    for q in pts[1:]:
                        path.lineTo(q)
                    path.closeSubpath()
                    p.drawPath(path)
                else:
                    for a, b in zip(pts, pts[1:]):
                        p.drawLine(a, b)
            elif op[0] == "arc":
                (_, (ccx, ccy), r, a0, a1) = op
                rect = QRectF(ox + (ccx - r) * side,
                              oy + (ccy - r) * side,
                              2.0 * r * side, 2.0 * r * side)
                path = QPainterPath()
                path.arcMoveTo(rect, a0)
                path.arcTo(rect, a0, a1 - a0)
                p.drawPath(path)
            elif op[0] == "arrow":
                (_, (x0, y0), (x1, y1)) = op
                ax, ay = ox + x0 * side, oy + y0 * side
                bx, by = ox + x1 * side, oy + y1 * side
                p.drawLine(QPointF(ax, ay), QPointF(bx, by))
                import math as _m
                ang = _m.atan2(by - ay, bx - ax)
                for sgn in (-1.0, 1.0):
                    ha = ang + _m.radians(180.0 + 22.0 * sgn)
                    p.drawLine(QPointF(bx, by), QPointF(
                        bx + 0.20 * side * _m.cos(ha),
                        by + 0.20 * side * _m.sin(ha)))
            else:
                (_, (ccx, ccy), r) = op
                p.drawEllipse(QPointF(ox + ccx * side, oy + ccy * side),
                              r * side, r * side)

    def _draw_gdt_frame(self, p, frame, gap) -> QRectF:
        """One [|sym][value][A][B] box centred under its host, in
        the host's OWN red pen — the frame never overpowers the
        dimension it annotates. Returns the rect: rung-2 stacked
        frames hang off each other (ISO cl.6.4)."""
        cells = gdt.gdt_cells(frame)
        widths = self._gdt_cells_widths(gap, frame)
        box = 1.5 * max(8.0, gap.height() - 4.0)
        total = sum(widths)
        x = gap.center().x() - total / 2.0
        top = gap.bottom() + 0.25 * box
        rect = QRectF(x, top, total, box)
        p.setPen(QPen(_RED, max(1.0, 0.5 * self._zoom)))
        p.setFont(self._dim_font())
        p.drawRect(rect)
        cx = x
        for c, w in zip(cells, widths):
            cell = QRectF(cx, top, w, box)
            if cx > x:
                p.drawLine(QPointF(cx, top), QPointF(cx, top + box))
            if c["kind"] == "glyph":
                self._paint_glyph(p, c["key"], cell, box)
            elif c["kind"] == "proj":
                # M150: the projected-zone compartment — a painted
                # circle around P (the balloon family, not the
                # tofu U+24C5) and the height beside it; the width
                # function already reserved exactly this.
                fm = QFontMetrics(self._dim_font())
                s = c["s"]
                rr = max(2.5, 0.5 * fm.horizontalAdvance("P")
                         + 0.10 * box)
                pcx = cell.left() + rr
                p.drawEllipse(QPointF(pcx, cell.center().y()), rr, rr)
                p.drawText(QRectF(pcx - rr, cell.top(), 2 * rr, box),
                           Qt.AlignCenter, "P")
                p.drawText(QRectF(pcx + rr, cell.top(),
                                  cell.right() - pcx - rr, box),
                           Qt.AlignVCenter | Qt.AlignLeft, s[2:])
            else:
                p.drawText(cell, Qt.AlignCenter, c["s"])
            cx += w
        return rect

    def _draw_gdt(self, p, d, gap):
        """The dim's paper kit: the ISO box (cl.11 — a TED "shall
        ... be enclosed in a frame") and the FCF stack below it.
        A stale entry that no longer validates never eats the sheet:
        cells raise -> this dim simply carries no frame."""
        anchor = gap
        if d.get("basic"):
            anchor = QRectF(gap)                       # the box IS
            p.setPen(QPen(_RED, max(1.0, 0.5 * self._zoom)))   # the
            p.drawRect(anchor)                                # gap's
        for frame in d.get("gdt", []):                 # own edge
            try:
                anchor = self._draw_gdt_frame(p, frame, anchor)
            except (KeyError, ValueError):
                return

    def page_scale(self) -> float:
        views = self.views()
        if not views:
            return 1.0
        return drawing.fit_scale(views, page=self.page)

    # ---- navigation -----------------------------------------------------
    def wheelEvent(self, ev):
        self._zoom = min(8.0, max(0.25, self._zoom *
                                  (1.15 if ev.angleDelta().y() > 0
                                   else 1 / 1.15)))
        self.update()

    def mousePressEvent(self, ev):
        if self._sec_mode and ev.button() == Qt.LeftButton:
            self._sec_click(ev)              # M136: cutting line clicks
            return
        if self._det_mode and ev.button() == Qt.LeftButton:
            self._det_click(ev)              # M201 R36: boundary beats
            return
        if self._bk_mode and ev.button() == Qt.LeftButton:
            self._bk_click(ev)               # M201 R37: profile beats
            return
        if self._balloon_mode and ev.button() == Qt.LeftButton:
            self._balloon_click(ev)          # M110: pin, don't pan
            return
        if self._fit_mode and ev.button() == Qt.LeftButton:
            placed = self.placed()                      # M114: annotate
            if placed:
                hit = self._dim_at(self.p2s(ev.position()), placed)
                if hit is not None:
                    self.fit_requested.emit(*hit)
            return
        if self._gdt_mode and ev.button() == Qt.LeftButton:
            placed = self.placed()                # M144: frame it too
            if placed:
                hit = self._dim_at(self.p2s(ev.position()), placed)
                if hit is not None:
                    self.gdt_requested.emit(*hit)
            return
        if self._dim_mode and ev.button() == Qt.LeftButton:
            self._dim_click(ev)          # M94: bubbles, not panning
            return
        if ev.button() == Qt.LeftButton:
            # M96: a press ON a view grabs the view; the desk still pans
            placed = self.placed()
            view = self._view_at(self.p2s(ev.position()), placed,
                                 slack=0.0) if placed else None
            if view is not None:
                base = self.sheet().get("move", {}).get(view, (0.0, 0.0))
                self._view_drag = [view, self.p2s(ev.position()),
                                   (float(base[0]), float(base[1])),
                                   False]
                return
        if ev.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._drag = ev.position()

    def _sec_click(self, ev):
        """M136: the two clicks of a cutting line, drawn ON the parent;
        M138 grew the jog: Alt at a click sets a CORNER and keeps the
        tool armed, every leg after the first must run straight on or
        turn square, and a double-click finishes. Two plain clicks
        still finish a straight section exactly as rung one shipped —
        the entry byte for byte unchanged. Clicks live in the parent's
        MODEL xy (they travel with the view when it is nudged, like
        dims and balloons — and survive its M109 spin, so they come
        through the de-rotating _p2m); the entry leaves letterless —
        MainWindow letters and keeps it."""
        placed = self.placed()
        if not placed:
            return
        page = self.p2s(ev.position())
        if not self._sec_pts:
            view = self._view_at(page, placed, slack=6.0)
            if view not in ("top", "front", "right"):
                self.tool_note.emit(
                    "Section lines start ON the top, front or right "
                    "view" + (" (click inside one)" if view is None
                              else f" — {view} is not a legal parent "
                                   "(v1: the three orthogonal views)"))
                return
            self._sec_view = view
            self._sec_pts = [self._p2m(placed[view], page)]
            self.tool_note.emit(f"Section on {view}: click where the "
                                "cut ENDS (Shift flips the kept side; "
                                "Alt sets a corner to jog)")
            self.update()
            return
        if self._view_at(page, placed, slack=6.0) != self._sec_view:
            self.tool_note.emit("Stay inside the parent — the cutting "
                                "line is drawn ON it")
            return
        p1 = self._p2m(placed[self._sec_view], page)
        if math.dist(self._sec_pts[-1], p1) < 0.5:
            self.tool_note.emit("That leg is too short to mean a corner")
            return
        if len(self._sec_pts) >= 2:           # jog leg: square or bust
            d = np.asarray(self._sec_pts[1], float) \
                - np.asarray(self._sec_pts[0], float)
            d /= max(float(np.linalg.norm(d)), 1e-12)
            u = np.asarray(p1, float) - np.asarray(self._sec_pts[-1],
                                                   float)
            u /= max(float(np.linalg.norm(u)), 1e-12)
            a = abs(float(u @ d))
            if a < 0.999 and a > 0.001:
                self.tool_note.emit("Jogs must turn SQUARE: run on, "
                                    "or bend at right angles")
                return
        corner = bool(ev.modifiers()
                      & Qt.AltModifier)
        self._sec_pts.append((float(p1[0]), float(p1[1])))
        if corner:
            self.tool_note.emit("Corner set — click the next leg, "
                                "double-click to finish")
            self.update()
            return
        if len(self._sec_pts) == 2:
            self._finish_section_line(ev)     # rung one: two plain
        else:                                 # clicks finish a         \
            self.update()                     # straight cut


    def _finish_section_line(self, ev):
        """Close the polyline into an entry: two points ship the M136
        straight form untouched; three or more ship "pts" and the
        jogged machinery reads them. Shift at the closing gesture
        flips the kept side."""
        if len(self._sec_pts) < 2:
            self.tool_note.emit("A cutting line needs at least two "
                                "points")
            return
        entry = {"parent": self._sec_view,
                 "p0": tuple(self._sec_pts[0]),
                 "p1": tuple(self._sec_pts[-1]),
                 "flip": bool(ev.modifiers() & Qt.ShiftModifier)}
        if len(self._sec_pts) > 2:
            entry["pts"] = [tuple(p) for p in self._sec_pts]
        try:
            if "pts" in entry:
                drawing.plane_from_polyline(entry["parent"],
                                            entry["pts"], entry["flip"])
        except ValueError as e:
            self.tool_note.emit(str(e) + " — the line stands, keep "
                                "clicking")
            return
        self.section_added.emit(entry)
        self._sec_pts, self._sec_view, self._sec_hover = [], None, None
        self.update()

    def _bk_click(self, ev):
        """M201 R37: the breakout profile's beats (the page clicks
        points, the Check closes - ours closes on the double-click,
        handled by mouseDoubleClickEvent, or on a click that lands on
        the first point once three stand)."""
        placed = self.placed()
        if not placed:
            return
        page = self.p2s(ev.position())
        view = self._view_at(page, placed, slack=6.0)
        if not self._bk_pts:                        # the first point
            if view is None:
                self.tool_note.emit(
                    "Breakout: click INSIDE the view to break out - "
                    "the page's dialog says select the drawing view "
                    "on which you want to create the breakout section")
                return
            src = self._sources().get(view)
            if src is None or src[0] is None:
                self.tool_note.emit(
                    f"{view} cannot host a breakout - a slice shows "
                    "the cut face alone, with no material left to "
                    "remove to depth")
                return
            if any(b.get("view") == view for b in self.breakouts()):
                self.tool_note.emit(
                    f"{view} already carries a breakout - the page's "
                    "own note: a drawing view can contain only one "
                    "breakout section")
                return
            self._bk_view = view
            self._bk_pts = [self._p2m(placed[view], page)]
            self._bk_hover = page
            self.tool_note.emit(
                f"Breakout on {view}: click to place the next point - "
                "double-click, or click the first point, closes the "
                "profile once it holds three")
            self.update()
            return
        if view != self._bk_view:
            self.tool_note.emit("Stay inside the view - the profile "
                                "is drawn ON it")
            return
        q = self._p2m(placed[self._bk_view], page)
        if len(self._bk_pts) >= 3 and math.dist(q, self._bk_pts[0]) < 2.0:
            self._bk_close()                        # closed on its start
            return
        if math.dist(q, self._bk_pts[-1]) < 0.5:
            self.tool_note.emit("That point lands on the last one - "
                                "give the profile room to read")
            return
        self._bk_pts.append(q)
        self._bk_hover = page
        n = len(self._bk_pts)
        self.tool_note.emit(
            "Breakout: double-click, or click the first point, to "
            "close the profile" if n >= 3 else
            f"Breakout: point {n} placed - the page's Check appears "
            f"after at least three (now {n})")
        self.update()

    def restart_breakout_profile(self) -> bool:
        """M136's Esc ladder, R37 rung: the FIRST Esc erases a
        half-drawn breakout profile and the tool keeps its seat."""
        if not self._bk_mode or not self._bk_pts:
            return False
        self._bk_pts, self._bk_view, self._bk_hover = [], None, None
        self.tool_note.emit("Breakout: profile cleared - the tool "
                            "keeps its seat")
        self.update()
        return True

    def _bk_close(self):
        """The Check made real: [verbatim] "A closed profile defines
        the breakout section", so closing is the moment the entry
        exists - it goes to the window for the page's Breakout Section
        View dialog (Section Depth), and the tool stands its loop down
        but keeps its seat."""
        if len(self._bk_pts) < 3:
            self.tool_note.emit("Breakout: the Check icon displays "
                                "after you place at least 3 points - "
                                "this profile is not closeable yet")
            return
        self.breakout_added.emit(
            {"view": self._bk_view,
             "loop": [[float(u), float(v)] for u, v in self._bk_pts]})
        self._bk_pts, self._bk_view, self._bk_hover = [], None, None
        self.update()

    def _det_click(self, ev):
        """M201 R36: the three beats of the detail boundary, verbatim
        off [Create a detail view] - and every refusal speaks the
        page's own parent list BY NAME. The centre and radius live in
        the PARENT's model xy (they travel with the parent's drag and
        survive its spin, exactly like the M136 cutting line and the
        balloons); the placement click lives in sheet mm (it is paper
        furniture, like a view's move). The identifier angle is the
        drag's own direction - the page ties it to the drag, so it is
        stored, not decorated."""
        placed = self.placed()
        if not placed:
            return
        page = self.p2s(ev.position())
        if self._det_c is None:                       # beat 1: the centre
            view = self._view_at(page, placed, slack=6.0)
            det_names = {d["name"] for d in self.details()}
            if view is None:
                self.tool_note.emit("Detail: click INSIDE the view to "
                                    "enlarge - the page's parent list "
                                    "is a base, projected or section "
                                    "view")
                return
            src = self._sources().get(view)
            if view in det_names:
                self.tool_note.emit(f"{view} is a detail - the page's "
                                    "parent list is a base, projected "
                                    "or section view; a detail of a "
                                    "detail is unoffered")
                return
            if view == "iso":
                self.tool_note.emit("iso cannot host a detail - it is "
                                    "on no true plane, so a detail of "
                                    "it could not stand its section "
                                    "line (the page's list: base, "
                                    "projected or section view)")
                return
            if src is None or src[0] is None:
                self.tool_note.emit(f"{view} cannot host a detail - a "
                                    "slice shows the cut face alone, "
                                    "with no depth left to enlarge")
                return
            self._det_view = view
            self._det_c = self._p2m(placed[view], page)
            self._det_hover = page
            self.tool_note.emit(f"Detail on {view}: drag the radius "
                                "out from the center and click - the "
                                "identifier rides the circle's edge")
            self.update()
            return
        if self._det_r is None:                       # beat 2: the drag
            if self._view_at(page, placed, slack=6.0) != self._det_view:
                self.tool_note.emit("Stay inside the parent - the "
                                    "boundary is drawn ON it")
                return
            p1 = self._p2m(placed[self._det_view], page)
            r = math.dist(self._det_c, p1)
            if r < 0.5:
                self.tool_note.emit("That boundary is too small to "
                                    "read - drag further out")
                return
            self._det_r = r
            self._det_a = math.atan2(p1[1] - self._det_c[1],
                                     p1[0] - self._det_c[0])
            self.tool_note.emit("Detail: click bare paper to place "
                                "the enlarged view")
            self.update()
            return
        if self._view_at(page, placed, slack=2.0) is not None:
            self.tool_note.emit("Place the detail on BARE PAPER - the "
                                "spot holds another view")
            return
        at = (float(page[0]), float(page[1]))
        self.detail_added.emit({"parent": self._det_view,
                                "c": [float(self._det_c[0]),
                                      float(self._det_c[1])],
                                "r": float(self._det_r),
                                "a": float(self._det_a), "at": list(at)})
        # the page arms the next pick after placing ("Click to place...
        # then click again for another"): stand down THIS boundary,
        # keep the tool in its seat.
        self._det_view = self._det_c = self._det_r = self._det_a = None
        self._det_hover = None
        self.update()

    def mouseMoveEvent(self, ev):
        if self._det_mode and self._det_c is not None \
                and self._det_r is None:            # R36 rubber circle
            self._det_hover = self.p2s(ev.position())
            self.update()
            return
        if self._bk_mode and self._bk_pts:          # R37 rubber profile
            self._bk_hover = self.p2s(ev.position())
            self.update()
            return
        if self._sec_mode and self._sec_pts:          # M136 rubber band
            self._sec_hover = self.p2s(ev.position())
            self.update()
            return
        if self._view_drag is not None:                  # M96: move a view
            view, start, base, moved = self._view_drag
            sp = self.s2p(start[0], start[1])
            pdx = (ev.position().x() - sp.x()) / self._zoom
            pdy = -(ev.position().y() - sp.y()) / self._zoom
            if not moved and abs(ev.position().x() - sp.x()) + \
                    abs(ev.position().y() - sp.y()) <= 2.0:
                return
            if not moved:
                self._view_drag[3] = moved = True
                self.view_drag_begin.emit()              # undo capture
            g = self.sheet()
            g.setdefault("move", {})[view] = [base[0] + pdx,
                                              base[1] + pdy]
            if self.doc is not None:
                self.doc.dirty = True
            self.update()
            return
        if self._drag is not None:
            d = ev.position() - self._drag
            self._center += QPointF(-d.x() / self._zoom, d.y() / self._zoom)
            self._drag = ev.position()
            self.update()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        self._view_drag = None

    def restart_section_line(self) -> bool:
        """M136: erase a half-drawn cutting line (the tool stays
        armed); True when there was one to erase. This is Esc's
        first rung on the sheet — the in-flight line yields before
        the tools, the same ladder law as the viewport."""
        if not self._sec_pts:
            return False
        self._sec_pts, self._sec_view, self._sec_hover = [], None, None
        self.tool_note.emit("Section line restarted")
        self.update()
        return True

    def mouseDoubleClickEvent(self, ev):
        # M138: while the cut-line tool is armed a double-click is the
        # FINISHING gesture (the vendor's polyline grammar) — never a
        # dialog. M100: otherwise double-click a view -> its Scale
        # dialog. M137: a SECTION child answers the same gesture with
        # its own props — depth, kept side, hidden lines, scale — one
        # dialog, because a section IS a view and the draughtsman
        # reaches for the same click twice for the second time.
        if self._sec_mode and ev.button() == Qt.LeftButton:
            if len(self._sec_pts) >= 2:
                self._finish_section_line(ev)
            elif self._sec_mode:
                self.tool_note.emit("Double-click finishes the cut — "
                                    "give it at least two points first")
            return
        if self._bk_mode and ev.button() == Qt.LeftButton:
            if len(self._bk_pts) >= 3:
                self._bk_close()               # R37: the Check gesture
            else:
                self.tool_note.emit("Breakout: the Check icon displays "
                                    "after at least three points - this "
                                    "profile cannot close yet")
            return
        if self._dim_mode or ev.button() != Qt.LeftButton:
            return
        placed = self.placed()
        if not placed:
            return
        view = self._view_at(self.p2s(ev.position()), placed, slack=0.0)
        if view is None:
            return
        # M201 R37: double-click ON a stored breakout profile answers
        # ITS door - [Edit breakout sections, verbatim] "Double-click
        # the breakout section to edit it"; the click must land near
        # the outline itself (the page grabs the OUTLINE: "hover
        # highlights the cut outline"), and a double-click anywhere
        # else in the view keeps the view's own door untouched.
        page = self.p2s(ev.position())
        for i, bk in enumerate(self.breakouts()):
            if bk.get("view") != view:
                continue
            fr = placed.get(view)
            if fr is None or len(bk.get("loop") or []) < 3:
                continue
            qs = [np.asarray(self._m2p(fr, q), float) for q in bk["loop"]]
            n = len(qs)

            def _d2seg(x, a, b):
                ab = b - a
                t = float(np.clip((x - a) @ ab / max(ab @ ab, 1e-12),
                                  0.0, 1.0))
                return float(np.hypot(*(x - (a + t * ab))))

            if min(_d2seg(page, qs[k], qs[(k + 1) % n])
                   for k in range(n)) <= 2.0:
                self.breakout_edit_requested.emit(i)
                return
        if any(s["name"] == view for s in self.sections()):
            self.section_edit_requested.emit(view)
        else:
            self.view_scale_requested.emit(view)

    def _balloon_click(self, ev):
        """One click, one balloon (M110): the anchor is stored in MODEL
        millimetres like a dimension, so spins and drags carry it; the
        item number is the next unused one across the sheet — balloons
        count parts, and the parts list already ordered them."""
        placed = self.placed()
        if not placed:
            return
        sheet = self.p2s(ev.position())
        view = self._view_at(sheet, placed)
        if view is None:
            return
        raw = self.page_to_model(view, sheet)
        self.balloon_added.emit(view, (float(raw[0]), float(raw[1])),
                                self._next_balloon_item())
        self.update()

    def _next_balloon_item(self) -> int:
        items = [b.get("item", 0)
                 for group in (self.sheet().get("balloons") or {}).values()
                 for b in group]
        return max(items, default=0) + 1

    def _view_dialog(self, cur, view=None):
        """M201 R32: the page's own dialog. [DWG-REF-DRAWING-VIEW-DLG,
        verbatim] "In the Drawing View dialog, you can edit the
        properties of a drawing view" - the TITLE is page-printed -
        and the Appearance section prints its rows in this order:
        "Adjust the Orientation, Style, Scale, and Name settings."
        The two rows the kernel can back for a base view are Style
        then Scale ("Select the view style for the selected drawing
        view.").  OFFERED members are the two the line-art painter
        draws: "From Parent" the page itself scopes away from base
        views ("(Projected view, section view, and detail view
        only.)"), and "Shaded"/"Shaded with Hidden Edges" stay
        UNOFFERED-BY-NAME - every view brush on this sheet is
        NoBrush, and decoration is forbidden (the Show-Hatch law).
        The page prints NO default anywhere ("Default:" counts 0), so
        the resting member is OURS-declared: VIEW_STYLE_DEFAULT is
        what today's painter actually shows - hidden ink on.  Scale
        rides M100's picker verbatim; the typed-custom the page also
        prints ("or type a custom scale") stays unoffered - the
        dropdown is our honest coin (declared stamp).  Returns the
        answer dict (None = cancelled; Cancel rides the book-wide
        silence, and the task pages' "Select OK." is their voice, not
        quotable from the reference page)."""
        from . import cmddialog
        word = "Fit (auto)"
        if cur.get("scale"):
            lab = scale_label(float(cur["scale"]))
            word = lab if lab in SCALE_CHOICES else "Fit (auto)"
        fields = [
            dict(key="style", kind="combo", label="Style",
                 choices=list(VIEW_STYLES),
                 default=cur.get("style") or VIEW_STYLE_DEFAULT),
            dict(key="scale", kind="combo", label="Scale",
                 choices=list(SCALE_CHOICES), default=word),
        ]
        # M201 R35 [DWG-REF-DRAWING-VIEW-DLG, verbatim] the group AFTER
        # Appearance: "Automated Center Marks and Center Lines:
        # Automatically create center lines and center marks for all
        # holes in a view." with "Center Marks: Choose the hole types
        # that receive automated center marks." -> "Hole: Creates a
        # center mark for hole features." The task page says the group
        # is reached "while creating the view, or later by
        # double-clicking the view" - THIS door. OFFERED BY THE INK:
        # the row appears only where hole_marks() really stands a cross
        # for this view (an ISO view shows no true circle, a bore across
        # the sight shows none - the row would be decoration).
        # UNOFFERED BY NAME, each one because this kernel owns no such
        # record: "Round Extrudes", "Round Cuts", "Pattern", "Fillet"
        # and their "Minimum/Maximum fillet radius" fields (no feature
        # classification to read), and the whole "Center Lines" sub-group
        # (no automated centre-LINE ink exists - the page's own words
        # would then be a lie). Rest is CHECKED: the page prints zero
        # defaults and M129 shipped the cross ON (the declared rest).
        if view and self.doc is not None and \
                view in drawing.hole_marks(self.doc):
            hm = (self.sheet().get("hmarks") or {}).get(view, True)
            fields.append(dict(
                key="hmarks", kind="checks", label="Center Marks",
                group="Automated Center Marks and Center Lines",
                choices=["Hole"], checked=["Hole"] if hm else []))
        return cmddialog.ask(self, "Drawing View", fields)

    def view_style(self, name: str) -> str:
        """The view's style member; absent means the OURS-declared
        rest (the page prints zero defaults - see _view_dialog)."""
        return (self.sheet().get("vstyle") or {}).get(name) \
            or VIEW_STYLE_DEFAULT
