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
                seen_leg[key] = dict(extent=extent)
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
