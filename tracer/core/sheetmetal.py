"""M145 — sheet metal SM1: the flat-pattern law, pure core.

The shop law is one line, and it is NOT a standard:

    BA = theta_rad * (ri + K * t)          (bend allowance)

measuring the neutral fibre from the INSIDE face. K is a process
constant of brake and material; the 0.44 default is industry
folklore (mid-row of the fetched air-bend table at our r/t
regime) — there is no ISO 12195 and this file never pretends
there is. Two laws from running the numbers against OUR kernel
(research/sheet_metal_reprobe.md) shape the code:

1. Developed lengths travel through BA, NEVER a mesh arc sum:
   our tessellated band's neutral fibre is the geometric
   mid-surface, i.e. K = 0.5 BY CONSTRUCTION — +0.188 mm of
   silent error per bend the moment the shop says K = 0.44.

2. Bend facets never ship in the flat: band-collapse. The
   detector's (axis, ri, ro, angle) + measured leg extents
   rebuild the blank; unfolding at K = 0.5 must close back on
   the arc the mesh really contains (the gate pins this oracle).

The detector is the reprobe's §2.5, EXECUTED — and the execution
taught the design: merge coplanar facets, walk chains of soft
hinges with parallel axes, trim the big flat ends, fit a
de-planarised circle perpendicular to the axis — but a kernel
bend tessellates as TWO ribbon chains (outer chords all at adjR
= ro, inner all at ri), so a BEND is a pair of ribbons whose
axis LINES coincide; ri and ro are the two ribbon radii, exact
on tangent-clean kernel bands, and OCCT-grade soup dies at the
constant-radius + residual filter (§2.3). The angle reads the
flange normal pair — the probe's span formula had a wraparound
bug at some densities; normals never lie. A LEG (one flat
stretch of sheet) is its faces at once: canonical plane
coordinates along +axis, paired when the gap equals that band's
t — parallel faces FAR apart are PARALLEL LEGS, not a sheet. The
key is order- and representative-independent so two bands
sharing a leg name it IDENTICALLY, and the cycle guard (a closed
section needs a user-placed SEAM the mesh cannot see) never
misses. A chain whose bands disagree on t is a modelling error,
never an average.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

FOLD_FLAT, FOLD_SOFT = 0.4, 45.0      # deg: merge limit / band limit
AXIS_PAR = 0.999                      # chain walk: parallel hinges
TRIM = 2.5                            # flange facets: area > 2.5x med
K_DEFAULT = 0.44                      # folklore, NOT a standard


class SheetMetalError(ValueError):
    """The sheet's own refusal voice."""


# ---- THE LAW ---------------------------------------------------------
def bend_allowance(t: float, ri: float, angle_deg: float,
                   K: float = K_DEFAULT) -> float:
    """BA = theta_rad * (ri + K*t) — neutral radius off the INSIDE
    face. K is a shop constant, 0 < K <= 1; the fetched tables run
    0.33..0.50 by r/t and process."""
    if not 0.0 < K <= 1.0:
        raise ValueError(f"K={K}: the neutral fibre lives inside the "
                         "sheet — 0 < K <= 1")
    if t <= 0 or ri <= 0:
        raise ValueError("a bend needs positive thickness and an "
                         "inside radius")
    return math.radians(abs(angle_deg)) * (ri + K * t)


def outside_setback(t: float, ri: float, angle_deg: float) -> float:
    """OSSB = tan(theta/2) * (ri + t) — the OUTSIDE setback from the
    apex; the band's tangent lines live here."""
    return math.tan(math.radians(abs(angle_deg)) / 2.0) * (ri + t)


def bend_deduction(t: float, ri: float, angle_deg: float,
                   K: float = K_DEFAULT) -> float:
    """BD = 2*OSSB - BA — what one bend costs the to-apex dims."""
    return (2.0 * outside_setback(t, ri, angle_deg)
            - bend_allowance(t, ri, angle_deg, K))


# ---- the facet model (merge + soft-hinge graph), once per solid -----
def _facet_model(solid) -> dict:
    tm = solid.to_trimesh()
    V = np.asarray(tm.vertices, float)
    pairs = np.asarray(tm.face_adjacency, int)
    ae = np.asarray(tm.face_adjacency_edges, int)
    ang = np.degrees(np.asarray(tm.face_adjacency_angles, float))
    rad = np.asarray(tm.face_adjacency_radius, float)
    normals = np.asarray(tm.face_normals, float)
    areas = np.asarray(tm.area_faces, float)
    flat = pairs[ang < FOLD_FLAT]
    g = coo_matrix((np.ones(len(flat)), (flat[:, 0], flat[:, 1])),
                   shape=(len(tm.faces), len(tm.faces)))
    nf, lab = connected_components(g, directed=False)
    farea = np.zeros(nf)
    np.add.at(farea, lab, areas)
    fn = np.zeros((nf, 3))
    for i in range(len(tm.faces)):
        fn[lab[i]] += areas[i] * normals[i]
    good = np.linalg.norm(fn, axis=1) > 1e-12
    fn[good] /= np.linalg.norm(fn[good], axis=1)[:, None]
    gfaces = [np.flatnonzero(lab == f) for f in range(nf)]
    offs = np.zeros(nf)
    for f in range(nf):
        if len(gfaces[f]):
            offs[f] = float(fn[f] @ V[tm.faces[gfaces[f][0]][0]])
    agg: dict = {}
    for r in np.where(ang >= FOLD_FLAT)[0]:
        a, b = int(lab[pairs[r][0]]), int(lab[pairs[r][1]])
        if a == b:
            continue
        d = V[ae[r][1]] - V[ae[r][0]]
        nn = float(np.linalg.norm(d))
        if nn <= 0:
            continue
        d /= nn
        k = (min(a, b), max(a, b))
        e = agg.setdefault(k, [0.0, [], []])
        e[0] = max(e[0], float(ang[r]))
        if np.isfinite(rad[r]) and rad[r] > 0:
            e[2].append(float(rad[r]))
        e[1].append(d if (not e[1] or d @ e[1][0] >= 0) else -d)
    G: dict = {}
    for (a, b), (f, ds, RR) in agg.items():
        d = np.mean(ds, 0)
        d /= np.linalg.norm(d)
        G.setdefault(a, {})[b] = (f, d, RR)
        G.setdefault(b, {})[a] = (f, d, RR)
    return dict(tm=tm, V=V, lab=lab, nf=int(nf), farea=farea,
                fn=fn, offs=offs, gfaces=gfaces,
                soft={f: {k: v for k, v in G.get(f, {}).items()
                          if v[0] < FOLD_SOFT} for f in range(nf)})


# ---- the detector -----------------------------------------------------
def detect_bands(solid) -> list[dict]:
    """Every bend band. The mesh truth (p10, EXECUTED): a kernel
    bend tessellates as TWO ribbon chains — the outer chord strip
    (every hinge-adjacency radius = ro) and the inner chord strip
    (= ri), each walked as one chain because all fold axes are
    parallel. So: find ribbons (chains with a clean circular fit),
    then PAIR an outer with an inner whose axis LINES coincide —
    that pair is the bend. ri/ro are the two ribbon radii; the
    angle comes from the flange normal pair (the span formula had
    a wraparound bug at some densities; the normals never lie)."""
    m = _facet_model(solid)
    tm, V, lab, farea, soft = (m["tm"], m["V"], m["lab"], m["farea"],
                               m["soft"])
    nf = m["nf"]
    unv = {f for f in range(nf) if soft[f]}
    consumed: set = set()
    ribbons = []
    while unv:
        s = min(unv, key=lambda f: -farea[f])
        ch, seen, cur, ax = [s], {s}, s, None
        for _ in range(2000):
            cand = {k: v for k, v in soft[cur].items()
                    if k not in seen and k not in consumed}
            pick = None
            for k, v in cand.items():
                if ax is not None and abs(float(v[1] @ ax)) \
                        <= AXIS_PAR:
                    continue
                # a ribbon must not WALK THROUGH a tangent into the
                # next flat (multi-bend rings would fuse into one
                # garbage chain; the probe only ever saw one bend):
                # big flats are entered only AT THE START and shed
                # by the trim
                if cur != s and farea[k] > TRIM * farea[cur]:
                    continue
                pick = (k, v)
                break
            if pick is None:
                break
            k, v = pick
            ax = v[1]
            ch.append(k)
            seen.add(k)
            cur = k
        for f in ch:
            unv.discard(f)
        for _ in range(6):                       # trim the flat ends
            if len(ch) < 2:
                break
            med = np.median([farea[f] for f in ch])
            if farea[ch[0]] > TRIM * med:
                ch = ch[1:]
            elif farea[ch[-1]] > TRIM * med:
                ch = ch[:-1]
            else:
                break
        if len(ch) < 2:
            continue
        consumed.update(ch)
        ds = np.array([e[1] for f in ch
                       for k, e in soft[f].items() if k in ch])
        if len(ds) == 0:
            continue
        axis = np.linalg.svd(ds, full_matrices=False)[2][0]
        memb = np.flatnonzero(np.isin(lab, ch))
        P = V[np.unique(tm.faces[memb].ravel())]
        fit = _fit_cyl(P, axis)
        RR = [x for f in ch for k, e in soft[f].items()
              if k in ch for x in e[2]]
        if fit is None or not RR:
            continue
        r_med = float(np.median(RR))
        if r_med <= 1e-9:
            continue
        if (max(RR) - min(RR)) > 0.05 * r_med or fit[2] > 0.1 * r_med:
            continue        # a RIBBON is one clean cylinder; soup is
            #                 not (the §2.3 OCCT chains die here)
        adj = []
        for f in (ch[0], ch[-1]):
            for k, e in soft[f].items():
                if k not in ch and farea[k] > farea[f]:
                    adj.append(k)
        ribbons.append(dict(axis=axis, center=np.asarray(fit[0]),
                            r=r_med, ch=ch,
                            adj=list(dict.fromkeys(adj))))
    # ---- pair outer + inner ribbons of the SAME bend ----------------------
    bands = []
    used = set()
    for i in range(len(ribbons)):
        for j in range(i + 1, len(ribbons)):
            if i in used or j in used:
                continue
            r1, r2 = ribbons[i], ribbons[j]
            a1, a2 = r1["axis"], r2["axis"]
            if abs(float(a1 @ a2)) < AXIS_PAR:
                continue
            a = a1 if float(a1 @ a2) >= 0 else -a1
            if float(np.linalg.norm(np.cross(r2["center"]
                                             - r1["center"], a))) \
                    > 0.01:
                continue                      # different axis LINES
            if abs(r1["r"] - r2["r"]) <= 1e-6:
                continue                      # not one sheet's pair
            used.update((i, j))
            ri, ro = min(r1["r"], r2["r"]), max(r1["r"], r2["r"])
            t_i = ro - ri
            adj = list(dict.fromkeys(r1["adj"] + r2["adj"]))
            legs = _cluster_legs(adj, m, t_i)
            if len(legs) != 2:
                continue
            (kA, repA, fsA), (kB, repB, fsB) = legs
            A = math.degrees(math.acos(max(
                -1.0, min(1.0, float(m["fn"][repA]
                                     @ m["fn"][repB])))))
            bands.append(dict(axis=tuple(float(x) for x in a),
                              center=tuple(float(x) for x in
                                           (r1["center"]
                                            + r2["center"]) / 2),
                              ri=float(ri), ro=float(ro),
                              angle=float(A),
                              flanges=(int(repA), int(repB)),
                              legkeys=(kA, kB),
                              legfaces={kA: fsA, kB: fsB}))
    bands.sort(key=lambda b: -(b["ro"] ** 2 - b["ri"] ** 2))
    return bands


def _cluster_legs(adj, m, t_i):
    """Faces flanking one band -> at most two LEGS. Each face gets
    its plane coordinate along +axis (the normal's own sign folds
    INTO the offset, so a leg's two antiparallel faces share the
    axis key); families of coincident faces merge, and families
    one t apart pair into a leg. The key (axis, lo, hi) is order-
    and representative-independent — a leg seen by two bands is
    named identically, and the cycle guard cannot miss."""
    fam: dict = {}                    # axis -> [[faces, off], ...]
    for f in adj:
        n = m["fn"][f]
        can = int(np.argmax(np.abs(n)))
        sgn = 1.0 if n[can] > 0 else -1.0
        off = sgn * float(m["offs"][f]) / max(abs(float(n[can])),
                                              1e-12)
        d = fam.setdefault(can, [])
        hit = next((g for g in d if abs(off - g[1]) <= 0.05 * t_i),
                   None)
        if hit is None:
            d.append([[int(f)], off])
        else:
            hit[0].append(int(f))
            if m["farea"][f] > m["farea"][hit[0][0]]:
                hit[1] = off
    out = []
    for can, d in fam.items():
        d.sort(key=lambda g: g[1])
        i = 0
        while i < len(d):
            pair = (i + 1 < len(d)
                    and abs(abs(d[i + 1][1] - d[i][1]) - t_i)
                    <= 0.05 * t_i)
            grp = [d[i], d[i + 1]] if pair else [d[i]]
            faces = [x for g in grp for x in g[0]]
            rep = max(faces, key=lambda x: m["farea"][x])
            lo = min(g[1] for g in grp)
            hi = max(g[1] for g in grp)
            out.append(((can, round(lo / t_i, 2), round(hi / t_i, 2)),
                        rep, faces))
            i += 2 if pair else 1
    return sorted(out, key=lambda x: -m["farea"][x[1]])


def _fit_cyl(P, axis):
    """De-planarised least-squares circle perpendicular to the axis
    (rimfillet._fit_circle's algebra; band vertices live on a
    cylinder, not in a plane). Returns (center, r, residual)."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    M = np.eye(3) - np.outer(a, a)
    c0 = P.mean(0)
    Q = (M @ (P - c0).T).T
    s, v = np.linalg.eigh(M)
    v = v[:, s.argsort()[::-1]]
    e1, e2 = v[0], v[1]
    x, y = Q @ e1, Q @ e2
    A = np.column_stack([x, y, np.ones_like(x)])
    D, E, F = np.linalg.lstsq(A, -(x * x + y * y), rcond=None)[0]
    r2 = D * D / 4 + E * E / 4 - F
    if r2 <= 0:
        return None
    r = float(np.sqrt(r2))
    c2 = (-D / 2) * e1 + (-E / 2) * e2
    return c0 + c2, r, \
        float(np.abs(np.hypot(*(Q - c2).T) - r).max())


# ---- the tree: cycles and one honest thickness ------------------------
def _tree_check(bands):
    """Legs are nodes, bands are edges. A band closing a loop is a
    CLOSED SECTION (a seam is a draughtsman's cut, not a mesh
    feature — SM1 refuses); two bands sharing a leg at different t
    is a modelling error, never an average."""
    for i in range(len(bands)):
        for j in range(i + 1, len(bands)):
            shared = set(bands[i]["legkeys"]) & set(bands[j]["legkeys"])
            if shared:
                ti = bands[i]["ro"] - bands[i]["ri"]
                tj = bands[j]["ro"] - bands[j]["ri"]
                if abs(ti - tj) > 0.05 * max(ti, tj):
                    raise SheetMetalError(
                        f"one sheet cannot be {ti:.2f} and {tj:.2f} "
                        "mm at once — mixed thicknesses in one bend "
                        "chain are a modelling error, not an average")
    parent = {}

    def root(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for b in bands:
        ra, rb = root(b["legkeys"][0]), root(b["legkeys"][1])
        if ra == rb:
            raise SheetMetalError(
                "this is a CLOSED SECTION: the bend tree loops back "
                "on itself, and the flat needs a SEAM — a seam is a "
                "cut a draughtsman chooses, not a feature the mesh "
                "can find; SM1 does not place one yet")
        parent[ra] = rb
    return sorted(set(parent), key=str)


# ---- the unfold -------------------------------------------------------
def unfold_flat(solid, K: float = K_DEFAULT) -> dict:
    """The blank, as numbers: per-bend law values + the developed
    flat length. Bands collapse to their fold lines; the flat is
    SUM(leg extents) + SUM(BA) — the facets' arcs NEVER ship, and
    at K = 0.5 the total closes on the mesh's own mid-surface."""
    bands = detect_bands(solid)
    if not bands:
        raise SheetMetalError(
            "no bend bands found — this body has nothing to unfold "
            "(a sheet needs at least one inside radius)")
    _tree_check(bands)
    m = _facet_model(solid)
    ts = [b["ro"] - b["ri"] for b in bands]
    t = float(np.median(ts))
    # every leg's extent: its largest face's span perpendicular to
    # both the fold axis and the face normal (tangent-to-tangent on
    # a middle leg, tangent-to-end on the outer ones — the facet
    # merge trims exactly at the tangent lines)
    V, tm = m["V"], m["tm"]
    seen_leg: dict = {}
    for b in bands:
        axv = np.asarray(b["axis"], float)
        for key in b["legkeys"]:
            faces = b["legfaces"][key]
            rep = max(faces, key=lambda f: m["farea"][f])
            pts = V[tm.faces[m["gfaces"][rep]].ravel()]
            t_hat = np.cross(axv, m["fn"][rep])
            nn = float(np.linalg.norm(t_hat))
            extent = 0.0
            if nn > 1e-9:
                s = pts @ (t_hat / nn)
                extent = float(s.max() - s.min())
            cur = seen_leg.get(key)
            if cur is None or extent > cur["extent"]:
                # SM2's fix riding SM1's key law: the extent is
                # ANONYMOUS without the legkey, and the outline walk
                # needs "which leg comes next" — the key was already
                # the leg's identity, so carrying it changes nothing
                # that unfolded before.
                seen_leg[key] = dict(extent=extent, key=key)
    flanges = list(seen_leg.values())
    ba_total = sum(bend_allowance(t, b["ri"], b["angle"], K)
                   for b in bands)
    flat_length = sum(f["extent"] for f in flanges) + ba_total
    out_bands = [dict(b, ba=bend_allowance(t, b["ri"], b["angle"], K),
                      bd=bend_deduction(t, b["ri"], b["angle"], K))
                 for b in bands]
    return dict(thickness=float(t), K=float(K), bands=out_bands,
                flanges=flanges, ba_total=float(ba_total),
                flat_length=float(flat_length))


# ---- SM2: the flat as PAPER ------------------------------------------
def _straight_fold(bands) -> None:
    """SM2's own law, after unfold_flat's ONE choke has had its say:
    a developed rectangle exists only for a STRAIGHT-fold tree —
    every fold axis parallel (|dot| rules, not sign: the fold's
    direction is its own, the tree's is the axis LINE). A cross-
    fold needs seams and reliefs; that is SM3's conversation."""
    if len(bands) < 2:
        return
    a0 = np.asarray(bands[0]["axis"], float)
    for b in bands[1:]:
        if abs(float(np.asarray(b["axis"], float) @ a0)) <= AXIS_PAR:
            raise SheetMetalError(
                "SM2 unfolds STRAIGHT-fold trees only (all fold "
                "axes parallel) — a cross-fold needs seams and "
                "reliefs; that is SM3's conversation")


def _sheet_width(solid, u) -> float:
    """Sheet width = the span EVERY full-width leg takes along the
    common fold axis (the extrude direction of the profile that
    built the part). The MEDIAN, so a relief or a cut that trims
    one leg cannot shrink the blank — full-width legs are the
    majority of a real part."""
    a = np.asarray(u["bands"][0]["axis"], float)
    m = _facet_model(solid)
    V, tm = m["V"], m["tm"]
    spans = []
    for f in u["flanges"]:
        faces = None
        for b in u["bands"]:
            if f["key"] in b["legfaces"]:
                faces = b["legfaces"][f["key"]]
                break
        rep = max(faces, key=lambda g: m["farea"][g])
        pts = V[tm.faces[m["gfaces"][rep]].ravel()]
        s = pts @ a
        spans.append(float(s.max() - s.min()))
    return float(np.median(spans)) if spans else 0.0


def flat_outline(solid, K: float = K_DEFAULT) -> dict:
    """SM2: the flat pattern as outline geometry, law values all the
    way down (reprobe §2, EXECUTED).

    The developed OUTLINE of a straight-fold tree is exactly ONE
    RECTANGLE  L x W — L = the law's flat_length, and the stagger
    collapses because every leg is full-width W. Each bend is a
    BA-wide SLOT along L, and the shop drawing marks it with one
    centre line at the slot's middle. The annulus the mesh hints
    at (r_c = ri + K*t, radial span +-t/2, theta*r_c == BA as an
    IDENTITY, tangency C1-exact) is the ORACLE these slots stand
    for, never the ink: its boundaries sit at ri+(K-.5)t and
    ri+(K+.5)t, equal to the true ri/ro ONLY at K=0.5 — arcing the
    plan would silently assert K=0.5 under a dialog that says 0.44.

    Tree order rides the legkeys (SM1's order-independent key law:
    two bands naming a shared leg AGREE, so legs are nodes and
    bands are edges): the walk starts at the lowest-sorted leaf and
    never iterates a dict. Refusals ride unfold_flat's ONE choke
    (bendless, seam, mixed t); straight-fold and one-strip are
    SM2's own named laws — a branched sheet has no single
    rectangle and says so.
    """
    u = unfold_flat(solid, K=K)                  # THE choke
    bands = u["bands"]
    _straight_fold(bands)
    leg_extent = {f["key"]: f["extent"] for f in u["flanges"]}
    adj: dict = {}
    for i, b in enumerate(bands):
        k_a, k_b = b["legkeys"]
        adj.setdefault(k_a, []).append((i, k_b))
        adj.setdefault(k_b, []).append((i, k_a))
    if any(len(e) > 2 for e in adj.values()):
        raise SheetMetalError(
            "this sheet BRANCHES at a leg — SM2 unfolds ONE strip "
            "(leg, bend, leg, ...); a branched blank is not a "
            "rectangle")
    leaves = sorted(k for k, e in adj.items() if len(e) == 1)
    if len(leaves) != 2:
        # tree + max-degree-2 is a path, or the kernel is wrong
        raise SheetMetalError(
            "the fold tree is not a single open strip — nothing "
            "to unfold here")
    w = _sheet_width(solid, u)
    runs: list = []
    x, cur, used = 0.0, leaves[0], set()
    runs.append(dict(kind="leg", key=cur, x0=x,
                     extent=leg_extent[cur]))
    x += leg_extent[cur]
    while len(used) < len(bands):
        for i, other in adj[cur]:
            if i in used:
                continue
            used.add(i)
            b = bands[i]
            runs.append(dict(kind="band", index=i, x0=x, ba=b["ba"],
                             ri=b["ri"], ro=b["ro"], angle=b["angle"]))
            x += b["ba"]
            runs.append(dict(kind="leg", key=other, x0=x,
                             extent=leg_extent[other]))
            x += leg_extent[other]
            cur = other
            break
    flat = float(x)
    # the walk total meets the law total term by term — a drift
    # this big IS a kernel bug, not a part:
    if abs(flat - u["flat_length"]) > 1e-6:
        raise SheetMetalError(
            "the outline walk disagrees with the law total — that "
            "is a kernel bug, not a part: report it")
    outline = [(0.0, 0.0), (flat, 0.0), (flat, w), (0.0, w),
               (0.0, 0.0)]
    bend_lines = [dict(x=r["x0"] + r["ba"] / 2.0, y0=0.0, y1=w,
                       band=r["index"])
                  for r in runs if r["kind"] == "band"]
    return dict(runs=runs, outline=outline, bend_lines=bend_lines,
                flat_length=flat, width=w, K=float(u["K"]),
                thickness=u["thickness"], bands=bands)


# ---- SM3 (M149): the parametric sheet — inputs are law ----------------
#
# The detector path reads what a mesh confesses; the parametric path
# OWNS the bend: t, W, tangent-length legs and (angle, ri, K) bends
# are INPUTS, so the flat is FORMULA — `==`, not ~. Two derivations
# from one (legs, bends) walk:
#
#   param_flat     the developed blank: SM2's rectangle (plus relief
#                  notches), BA-wide slots, one centre line per bend.
#                  The annulus stays ORACLE, never ink (SM2 law); a
#                  closed cycle unwraps by ONE user-named seam.
#   fold_section   the folded cross-section: a centreline walk —
#                  legs tangent-to-tangent, bends circular arcs of
#                  centreline radius ri + t/2 — with the edges
#                  offset +-t/2 to the TRAVEL side (never
#                  inner/outer, so an S-bend cannot self-cross). A
#                  lone leg is the exact rectangle prism; the 90 deg
#                  twin reproduces the p13 recipe the detector reads.
#
# Fixed association order: the walk advances x += leg, then x += ba,
# in stream order — and every golden re-uses THAT order, because
# float addition is not associative. The order IS law.


def _param_check(t, W, legs, bends):
    """The parametric path's ONE refusal choke — SM1's discipline:
    one body, one law, one voice. K/ri/t law rides bend_allowance."""
    if t <= 0 or W <= 0:
        raise SheetMetalError("a sheet needs positive thickness and "
                              "width — this one has neither from you")
    if not len(legs):
        raise SheetMetalError("a sheet needs at least one leg")
    if any(float(L) <= 0 for L in legs):
        raise SheetMetalError("a leg of length zero is not a leg — "
                              "every leg must be positive")
    n = len(legs)
    if len(bends) not in (n - 1, n):
        raise SheetMetalError(
            f"{n} legs and {len(bends)} bends is neither an open strip "
            f"(wants {n - 1}) nor a closed cycle (wants {n})")
    for (a, r, k) in bends:
        if abs(float(a)) >= 180.0:
            raise SheetMetalError(
                f"a {abs(float(a)):g}-degree fold lies back on itself — "
                "v1 bends stay under 180 degrees")
        bend_allowance(t, r, a, k)          # K, ri, t law, SM1's voice


def attach_walk(nodes) -> dict:
    """SM4 (M151): the EDGE AS HOST projected onto the strip. A node
    is one flange feature — dict(name, uid, leg, bend, relief, host,
    side, witness) — and the whole list is stream order. A flange
    hangs on the START or END edge of its host leg; with one fold per
    edge every leg has degree <= 2, so the tree is a PATH and the flat
    is ONE strip (contract sm4 §2.1). Returns dict(legs, bends,
    reliefs, order, bands, free) in ASCENDING FLAT STATION — the
    association order param_flat demands (§3.5: the order IS a value).
    host == "" on a later node IS SM3's chain: bind to the previous
    stream node's end edge, byte-identical. Every refusal fires here,
    before any leg reaches param_flat (§5.2); _param_check is NOT
    grown."""
    nodes = list(nodes)
    if not nodes:
        raise SheetMetalError("a sheet needs at least one leg")
    if nodes[0]["host"]:
        # no stream position precedes the first node: a host there
        # CANNOT exist — the base was deleted (G14's orphan path)
        raise SheetMetalError(
            f"{nodes[0]['name']!r} hangs on leg {nodes[0]['host']!r}, "
            "which is gone — re-pick its edge or delete the flange "
            "too (Ctrl+Z first)")
    if nodes[0]["bend"] is not None:
        raise SheetMetalError(
            f"{nodes[0]['name']!r} is not a base flange — a sheet "
            "begins with one leg and no fold")
    by_uid = {nodes[0]["uid"]: nodes[0]}
    claimed, start_kid, end_kid = {}, {}, {}
    for prev, nd in zip(nodes, nodes[1:]):
        if not nd["host"]:                          # SM3 chain law
            nd = dict(nd, host=prev["uid"])
        name, host, side = nd["name"], nd["host"], nd["side"]
        h = by_uid.get(host)
        if h is None:
            raise SheetMetalError(
                f"{name!r} hangs on leg {host!r}, which is gone — "
                "re-pick its edge or delete the flange too "
                "(Ctrl+Z first)")
        if side not in ("start", "end"):
            raise SheetMetalError(
                f"edge {side!r} of {h['name']!r} folds ACROSS the "
                "sheet: v1 sheets bend on ONE axis (the section is "
                "swept along W) and two bend families meet at a "
                "corner no developable surface covers. The pan/box "
                "case needs miters and 2-bend corner reliefs — that "
                "is SM5's conversation")
        if nd["bend"] is None:
            raise SheetMetalError(
                f"{name!r} hangs without a fold — a flange carries "
                "its bend")
        # The edge this child stands on is used up, and so is the
        # CHILD's own facing edge: a second fold there would share a
        # station, which _param_check refuses only via a zero-length
        # leg (§2.2 belt) — claimed here so the voice names the fold.
        facing = "start" if side == "end" else "end"
        for slot, holder, other in (((host, side), h, name),
                                    ((nd["uid"], facing), nd,
                                     h["name"])):
            if slot in claimed:
                raise SheetMetalError(
                    f"{by_uid[slot[0]]['name']!r} already folds at "
                    f"its {slot[1]} edge (that is {claimed[slot]!r}); "
                    "v1 places ONE fold per edge — pick the new free "
                    "end instead")
            claimed[slot] = other
        if nd["witness"] is not None:
            w, hl = float(nd["witness"]), float(h["leg"])
            if w < -1e-9 or w > hl + 1e-9:
                raise SheetMetalError(
                    f"{name!r} was picked {w:.3f} mm along "
                    f"{h['name']!r}, which is only {hl:.3f} mm long "
                    "now — the host shrank below the witness; "
                    "re-pick its edge")
        (start_kid if side == "start" else end_kid)[host] = nd["uid"]
        by_uid[nd["uid"]] = nd
        nd["host"], nd["side"] = host, side         # resolve the ""

    out: list = []

    def walk(uid):                                  # ascending station
        nd = by_uid[uid]
        sc = start_kid.get(uid)
        if sc:
            walk(sc)                                # child owns the
            out.append(("band", sc))                # fold at host.start
        out.append(("leg", uid))
        ec = end_kid.get(uid)
        if ec:
            out.append(("band", ec))                # fold at host.end
            walk(ec)

    walk(nodes[0]["uid"])
    legs, bends, order, bands = [], [], [], {}
    for kind, ref in out:
        if kind == "leg":
            legs.append(float(by_uid[ref]["leg"]))
            order.append(by_uid[ref]["name"])
        else:
            bends.append(by_uid[ref]["bend"])
            bands[ref] = len(bends) - 1
    if len(bends) != len(legs) - 1:
        raise SheetMetalError(
            f"{len(legs)} legs and {len(bends)} folds is not a strip "
            "— the walk emits one fold per junction")
    reliefs = sorted((dict(bend=bands[nd["uid"]],
                           gap=nd["relief"]["gap"],
                           depth=nd["relief"]["depth"])
                      for nd in nodes if nd["relief"] is not None),
                     key=lambda d: d["bend"])
    free = [dict(uid=nd["uid"], name=nd["name"], side=side)
            for nd in nodes for side in ("start", "end")
            if (nd["uid"], side) not in claimed]
    return dict(legs=legs, bends=bends, reliefs=reliefs, order=order,
                bands=bands, free=free)


def param_flat(legs, bends, t, W, reliefs=(), seam=None) -> dict:
    """THE developed-blank law of a parametric chain, every float
    from formula. Open strip: len(bends) == len(legs) - 1. Closed
    cycle (len(bends) == len(legs), signed angles summing to +-360)
    needs a `seam` — ONE number on a flat leg — and the outline
    stays EXACTLY the rectangle [0, Lc] x [0, W]: the seam picks
    where the rectangle's edge falls on the cycle, it cuts nothing
    (kerf 0, v1). Bend lines ride (x - s) mod Lc; a seam inside a
    bend slot splits the band and refuses, named. `reliefs`
    ([{"bend": i, "gap": g, "depth": d}]) turn SM2's 5-point
    rectangle into the SAME chain plus notch vertices — without
    them the outline is SM2's, byte for byte.
    """
    _param_check(t, W, legs, bends)
    closed = len(bends) == len(legs)
    if reliefs and closed:
        raise SheetMetalError(
            "reliefs on a closed cycle wait for split-band seams — "
            "v1 notches the open strip only")
    runs: list = []
    x = 0.0
    runs.append(dict(kind="leg", x0=x, extent=float(legs[0])))
    x += float(legs[0])
    for i, (a, r, k) in enumerate(bends):
        b = bend_allowance(t, r, a, k)
        runs.append(dict(kind="band", x0=x, ba=b, ri=float(r),
                         K=float(k), angle=float(a)))
        x += b
        if i + 1 < len(legs):
            runs.append(dict(kind="leg", x0=x, extent=float(legs[i + 1])))
            x += float(legs[i + 1])
    flat = float(x)
    w = float(W)
    if closed:
        turn = sum(float(a) for (a, _r, _k) in bends)
        if abs(abs(turn) - 360.0) > 1e-9:
            raise SheetMetalError(
                f"the cycle turns {turn:g} degrees, not 360 — those "
                "legs and bends do not close")
        if seam is None:
            raise SheetMetalError(
                "this is a CLOSED SECTION: the bend chain loops back on "
                "itself and the flat needs a SEAM — a seam is a cut a "
                "draughtsman chooses; on the parametric path, NAME it: "
                "seam = a number on a flat leg")
        s = float(seam) % flat
        for rn in runs:
            if (rn["kind"] == "band"
                    and rn["x0"] <= s < rn["x0"] + rn["ba"]):
                raise SheetMetalError(
                    "the seam must live on a FLAT LEG (v1): a seam "
                    "through a bend slot splits the band")
        band_runs = [rn for rn in runs if rn["kind"] == "band"]
        lines = [dict(x=(rn["x0"] + rn["ba"] / 2.0 - s) % flat,
                      y0=0.0, y1=float(W), band=j)
                 for j, rn in enumerate(band_runs)]
        lines.sort(key=lambda d: d["x"])
        for rn in runs:                 # slots read the unwrapped x too
            if rn["kind"] == "band":
                rn["x0"] = (rn["x0"] - s) % flat
    else:
        lines = [dict(x=rn["x0"] + rn["ba"] / 2.0, y0=0.0, y1=float(W),
                      band=j)
                 for j, rn in enumerate(
                     rn for rn in runs if rn["kind"] == "band")]
    outline = [(0.0, 0.0), (flat, 0.0), (flat, w), (0.0, w), (0.0, 0.0)]
    if reliefs:
        outline = _relief_outline(runs, flat, w, reliefs)
    return dict(runs=runs, outline=outline, bend_lines=lines,
                flat_length=flat, width=w, thickness=float(t),
                closed=closed,
                seam=(None if seam is None else float(seam) % flat))


def _relief_cuts(runs, reliefs, W):
    """Validated, sorted (lo, hi, depth, band) notch cuts — the ONE
    voice reliefs obey, read alike by the flat outline and the 3-D
    blade. v1 laws: the notch lives inside its BA-wide slot (a wider
    relief waits for the leg-cutting v2), both edges' notches stop
    short of meeting mid-sheet, and a notch needs positive t."""
    band_runs = [rn for rn in runs if rn["kind"] == "band"]
    cuts = []
    for r in reliefs:
        i = int(r["bend"])
        if not 0 <= i < len(band_runs):
            raise SheetMetalError(
                f"relief on bend {i}: this strip has {len(band_runs)} "
                "bend(s) to relieve")
        g, d = float(r["gap"]), float(r["depth"])
        if g <= 0 or d <= 0:
            raise SheetMetalError("a relief needs positive gap and "
                                  "depth — or no relief at all")
        if 2.0 * d >= W:
            raise SheetMetalError(
                f"a {d:g} mm relief from both edges meets across the "
                f"middle of a {W:g} mm sheet — that severs the bend")
        rn = band_runs[i]
        if g >= rn["ba"]:
            raise SheetMetalError(
                f"a v1 relief must live inside its {rn['ba']:.3f} mm "
                f"bend slot (gap {g:g} is as wide) — reliefs that cut "
                "onto the legs wait for v2")
        xc = rn["x0"] + rn["ba"] / 2.0
        cuts.append((xc - g / 2.0, xc + g / 2.0, d, i))
    cuts.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
    for (lo, hi, _d, _j), (lo2, _hi2, _d2, _j2) in zip(cuts, cuts[1:]):
        if lo2 <= hi:
            raise SheetMetalError(
                "two reliefs overlap on the blank — widen the bends "
                "or spare one")
    return cuts


def _relief_outline(runs, flat, W, reliefs):
    """The SM2 rectangle PLUS axis-aligned notch vertices at both
    free edges of each relieved bend: still ONE closed chain, still
    line-only ink (SM2's DXF op grammar carries it unchanged)."""
    cuts = _relief_cuts(runs, reliefs, W)
    out = [(0.0, 0.0)]
    for (lo, hi, d, _j) in cuts:
        out += [(lo, 0.0), (lo, d), (hi, d), (hi, 0.0)]
    out += [(flat, 0.0), (flat, W)]
    for (lo, hi, d, _j) in reversed(cuts):
        out += [(hi, W), (hi, W - d), (lo, W - d), (lo, W)]
    out += [(0.0, W), (0.0, 0.0)]
    return out


def fold_section(legs, bends, t, n=15):
    """The folded cross-section as a CENTRELINE-offset polygon, and
    the band frames the relief blades read. The walk: legs at their
    tangent-to-tangent length, each bend a circular arc of centreline
    radius ri + t/2 spanning the signed angle; both edges sit +-t/2
    to the TRAVEL side — one rule everywhere, so an S-bend's edges
    never cross (an inner/outer rule inverts mid-leg and self-crosses).
    TANGENT LAW, earned the hard way: the tangent station is an
    explicit vertex (a chord that skips it shaves the corner, and the
    detector — correctly — reads the shave as the leg: leg 60 came
    back 60 + ro*sin(facet)). n is segments per QUADRANT, defaulting
    to p13's 15 so the folded twin carries the SM fixtures' arc
    density; law-volume gates raise it (chord deficits fall with 1/n).
    Refuses the closed cycle: the folded ring is v1 PAPER law only.
    """
    _param_check(t, 1.0, legs, bends)
    if len(bends) == len(legs):
        raise SheetMetalError(
            "a closed cycle is seam-law PAPER in v1 — the folded ring "
            "body (slit/kerf geometry) is queued; open the chain or "
            "drop a bend")
    pts, dirs = [], []
    pos = np.zeros(2)
    d = np.array([1.0, 0.0])
    pts.append(pos.copy())
    dirs.append(d.copy())
    frames: list = []
    x = 0.0
    for i, L in enumerate(legs):
        pos = pos + float(L) * d
        pts.append(pos.copy())
        dirs.append(d.copy())                       # tangent, or free end
        x += float(L)
        if i >= len(bends):
            break
        a, r, k = bends[i]
        th = math.radians(float(a))
        R = float(r) + float(t) / 2.0
        ba = bend_allowance(float(t), float(r), float(a), float(k))
        sgn = 1.0 if th >= 0 else -1.0
        C = pos + R * sgn * np.array([-d[1], d[0]])
        phi0 = math.atan2(pos[1] - C[1], pos[0] - C[0])
        segs = max(1, int(math.ceil(abs(th) / math.radians(90.0) * n)))
        for s_i in range(1, segs + 1):              # ends ON exit tangent
            phi = phi0 + th * s_i / segs
            pts.append(C + R * np.array([math.cos(phi), math.sin(phi)]))
            dirs.append(sgn * np.array([-math.sin(phi), math.cos(phi)]))
        pos, d = pts[-1], dirs[-1]
        frames.append(dict(cx=float(C[0]), cy=float(C[1]),
                           phi0=float(phi0), th=float(th), ba=float(ba),
                           x0=float(x), ri=float(r), K=float(k),
                           angle=float(a)))
        x += ba
    P, D = np.asarray(pts), np.asarray(dirs)
    nrm = np.column_stack([-D[:, 1], D[:, 0]])
    return (np.vstack([P + (t / 2.0) * nrm, (P - (t / 2.0) * nrm)[::-1]]),
            frames)


def sheet_solid(legs, bends, t, W, reliefs=(), seam=None, n=15):
    """The folded parametric sheet AS A SOLID; reliefs cut by radial
    blades (§2.5): developed x maps to angle about the band's centre
    (theta = phi0 + sweep * (x - x0) / BA), so a notch edge is a
    radial plane and each blade removes an EXACT annular sector —
    per side g * (rm / rc) * t * d, with rm = ri + t/2 (the part's
    geometric mid-surface) and rc = ri + K * t (the law's neutral
    radius): the K-mismatch made VISIBLE as a formula-predicted
    volume, never a measurement. n rides fold_section's p13
    convention; the blade samples at ~1 degree per chord so its
    chord-truncation error stays far under the 1e-2 dV law budget."""
    from .geometry import Solid
    pl = param_flat(legs, bends, t, W, reliefs=reliefs,
                    seam=seam)                    # the law, named
    sec, frames = fold_section(legs, bends, t, n=n)
    body = Solid.extrude(sec, height=float(W))
    cuts = _relief_cuts(pl["runs"], reliefs, W)
    if not cuts:
        return body
    tools = []
    for (lo, hi, d, j) in cuts:
        fr = frames[j]
        phi_a = fr["phi0"] + fr["th"] * (lo - fr["x0"]) / fr["ba"]
        phi_b = fr["phi0"] + fr["th"] * (hi - fr["x0"]) / fr["ba"]
        ri, ro = fr["ri"], fr["ri"] + float(t)
        a = np.linspace(phi_a, phi_b,
                        max(4, int(math.ceil(abs(phi_b - phi_a)
                                             / math.radians(1.0)))) + 1)
        C = np.array([fr["cx"], fr["cy"]])
        outer = C + np.column_stack([(ro + t) * np.cos(a),
                                     (ro + t) * np.sin(a)])
        inner = C + np.column_stack([0.25 * ri * np.cos(a[::-1]),
                                     0.25 * ri * np.sin(a[::-1])])
        blade = Solid.extrude(np.vstack([outer, inner]), height=d)
        tools.append(blade)
        tools.append(blade.translated((0.0, 0.0, float(W) - d)))
    return body.subtract(Solid.batch_union(tools))
