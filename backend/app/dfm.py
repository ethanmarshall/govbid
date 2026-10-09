"""Manufacturability (DFM) checks for a STEP part, by process.

Each finding is {rule, severity (info | warn | cost), title, detail, suggestion, cost_effect, count,
location: {point: [x, y, z] in inches, points: [...], faces: ["f12", ...]}}. Face ids are the
order OpenCascade explores the faces of the loaded shape (the same order cad.mesh uses).

What is checked:
  - Thin walls (all but sheet metal): two opposite-facing planar faces with material between them and
    overlapping where they face each other, closer than the wall limit for the process and material.
  - Holes (machining): depth over 4x diameter (peck drilling) and over 10x (gun drill or EDM), holes
    under 0.040 in, and holes that are not a standard twist drill size (nearest size suggested).
  - Sharp internal vertical corners (milling): a concave straight edge between two planar faces where
    no flat-bottom tool can reach it along either face's normal. A rotating tool always leaves a radius.
  - Small corner radii in deep pockets (milling): vertical concave fillets deeper than 4x the largest
    tool that fits them (tool diameter = 2 x corner radius).
  - Setups and undercuts (milling): the fewest of the six principal directions from which every planar
    face and hole can be reached in a straight line; faces reachable from none are undercuts, faces at
    odd angles need a tilted setup or 5-axis.
  - Sheet metal: inside bend radius under the thickness, hole edges closer than 2x thickness to the
    start of a bend, flanges shorter than 4x thickness (measured from the outside of the bend), holes
    smaller than the thickness (cannot be punched).

Rules of thumb and where they come from (thresholds are in DEFAULT_RULES; override any of them under
the shop-rate config key "dfm"):
  - Hubs (Protolabs Network), "CNC machining design guide" (https://hubs.com/knowledge-base/how-design-parts-cnc-machining,
    read 2026-10-09): wall thickness 0.8 mm recommended / 0.5 mm feasible for metals, 1.5 mm / 1.0 mm
    for plastics; hole depth 4x diameter recommended, 10x typical, 40x feasible; cavity depth 4x its
    width; vertical internal corner radius at least 1/3 of the cavity depth; holes at standard drill
    sizes; smallest hole 2.5 mm recommended.
  - The Fabricator, "Design tips for sheet metal bend relief, small holes, hole distortion near bends,
    and minimum flange widths" (https://www.thefabricator.com/article/bending/design-tips-for-sheet-metal-bend-relief-small-holes-hole-distortion-near-bends-and-minimum-flange-widths,
    read 2026-10-09): inside bend radius at least equal to the thickness for mild steel (6061 and 2024
    aluminum need 4 to 8x); hole edges at least 2x thickness from the start of the bend radius; flange
    width at least 4x thickness; punched holes no smaller than the thickness.
  - Xometry, "10 design tips for sheet metal bending" (https://www.xometry.com/resources/sheet/video-10-design-tips-for-sheet-metal-bending,
    read 2026-10-09): smallest bend radius at least the sheet thickness; flange length from the outside
    of the bend at least 4x thickness; holes at least 2.5x thickness from the bend.
  - Protolabs, "8 mistakes to avoid when designing sheet metal parts" (read 2026-10-09) is more
    conservative: features at least 4x thickness from bend lines.
  - Wevolver, "FDM 3D printing design tips" (read 2026-10-09): minimum wall 0.75 mm supported, 1.0 mm
    unsupported. The FDM limit here is 0.8 mm.
The machining wall limits used here (0.030 in metal, 0.040 in plastic) sit between the Hubs
recommended and feasible values. All of these are rules of thumb: your machines and tooling decide.
Standard drill sizes are the fractional (1/64 in steps to 1 in), number (#1 to #80 shown to #60),
letter (A to Z) and metric (0.5 mm steps, plus common tap drills) twist drill series.
"""
from __future__ import annotations

import copy
import math

from . import cad

IN = 25.4

DEFAULT_RULES = {
    "thin_wall_in": {"metal": 0.030, "plastic": 0.040, "fdm": round(0.8 / IN, 4), "sla": round(0.5 / IN, 4)},
    "hole_depth_ratio_warn": 4.0,
    "hole_depth_ratio_extreme": 10.0,
    "min_hole_in": 0.040,
    "drill_match_in": 0.0015,  # a hole within this of a standard drill counts as standard
    "drill_check_max_in": 1.0,  # bigger holes are bored or interpolated anyway
    "corner_depth_to_tool_dia": 4.0,
    "corner_radius_fraction_of_depth": 1 / 3,
    "sheet_min_bend_radius_t": 1.0,
    "sheet_hole_to_bend_t": 2.0,
    "sheet_min_flange_t": 4.0,
    "max_planar_faces": 800,  # skip the pairwise thin-wall search on very large models
}

_NUMBER = [.228, .221, .213, .209, .2055, .204, .201, .199, .196, .1935, .191, .189, .185, .182, .180, .177, .173, .1695, .166, .161,
           .159, .157, .154, .152, .1495, .147, .144, .1405, .136, .1285, .120, .116, .113, .111, .110, .1065, .104, .1015, .0995, .098,
           .096, .0935, .089, .086, .082, .081, .0785, .076, .073, .070, .067, .0635, .0595, .055, .052, .0465, .043, .042, .041, .040]
_LETTER = [.234, .238, .242, .246, .250, .257, .261, .266, .272, .277, .281, .290, .295, .302, .316, .323, .332, .339, .348, .358,
           .368, .377, .386, .397, .404, .413]


def _drill_table() -> list[tuple[str, float]]:
    out = [(f"#{i}", d) for i, d in enumerate(_NUMBER, 1)]
    out += [(chr(65 + i), d) for i, d in enumerate(_LETTER)]
    for n in range(1, 65):  # 1/64 to 1 in
        g = math.gcd(n, 64)
        out.append((f"{n // g}/{64 // g} in" if n != 64 else "1 in", n / 64))
    mm = {round(0.5 * k, 1) for k in range(2, 51)} | {1.6, 2.05, 2.5, 3.3, 4.2, 5.0, 6.8, 8.5, 10.2}
    out += [(f"{m:g} mm", m / IN) for m in sorted(mm)]
    return out


DRILLS = _drill_table()


def nearest_drill(d_in: float) -> tuple[str, float]:
    return min(DRILLS, key=lambda x: abs(x[1] - d_in))


def rules(config: dict | None = None) -> dict:
    r = copy.deepcopy(DEFAULT_RULES)
    for k, v in ((config or {}).get("dfm") or {}).items():
        if isinstance(v, dict) and isinstance(r.get(k), dict):
            r[k].update(v)
        else:
            r[k] = v
    return r


# ---------------------------------------------------------------- OCP helpers
def _v(p):
    return (p.X(), p.Y(), p.Z())


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _add(a, b, k=1.0):
    return tuple(x + k * y for x, y in zip(a, b))


def _norm(a):
    n = math.sqrt(sum(x * x for x in a)) or 1.0
    return tuple(x / n for x in a)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _in(p_mm):
    return [round(x / IN, 4) for x in p_mm]


class _Model:
    """The loaded shape with face data, a ray caster and a point classifier (all in mm)."""

    def __init__(self, shape):
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

        self.shape = shape
        self.faces = list(cad._faces(shape))
        BRepMesh_IncrementalMesh(shape, 0.2, False, 0.5, True)
        self._ray = IntCurvesFace_ShapeIntersector()
        self._ray.Load(shape, 1e-6)
        self._cls = BRepClass3d_SolidClassifier(shape)
        self.info = [self._face_info(i, f) for i, f in enumerate(self.faces)]
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        lo, hi = box.CornerMin(), box.CornerMax()
        self.size = max(hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z()) or 1.0

    def _face_info(self, i, f) -> dict:
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp, BRepGProp_Face
        from OCP.BRepTools import BRepTools
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCP.GProp import GProp_GProps
        from OCP.gp import gp_Pnt, gp_Vec
        from OCP.TopLoc import TopLoc_Location

        s = BRepAdaptor_Surface(f)
        t = s.GetType()
        gp = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, gp)
        d = {"id": f"f{i}", "i": i, "kind": "plane" if t == GeomAbs_Plane else "cylinder" if t == GeomAbs_Cylinder else "other",
             "area": gp.Mass(), "point": None, "normal": None}
        # a point that is really on the face: the centroid of its largest mesh triangle
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is not None and tri.NbTriangles():
            trsf = loc.Transformation()
            best, bp = -1.0, None
            for k in range(1, tri.NbTriangles() + 1):
                a, b, c = (tri.Node(n).Transformed(trsf) for n in tri.Triangle(k).Get())
                pa, pb, pc = _v(a), _v(b), _v(c)
                ar = math.sqrt(sum(x * x for x in _cross(_sub(pb, pa), _sub(pc, pa))))
                if ar > best:
                    best, bp = ar, tuple((x + y + z) / 3 for x, y, z in zip(pa, pb, pc))
            d["point"] = bp
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(f)
        pnt, nrm = gp_Pnt(), gp_Vec()
        BRepGProp_Face(f).Normal((umin + umax) / 2, (vmin + vmax) / 2, pnt, nrm)
        if nrm.Magnitude() > 1e-12:
            d["normal"] = _norm((nrm.X(), nrm.Y(), nrm.Z()))
        if d["point"] is None:
            d["point"] = _v(pnt)
        if t == GeomAbs_Cylinder:
            c = s.Cylinder()
            ax = c.Axis()
            p0, dd = _v(ax.Location()), (ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
            radial = _sub(_v(pnt), p0)
            along = sum(x * y for x, y in zip(radial, dd))
            radial = _add(radial, dd, -along)
            concave = sum(x * y for x, y in zip(d["normal"] or (0, 0, 0), radial)) < 0
            d.update(r=c.Radius(), axis_p=p0, axis_d=dd, concave=concave, span=umax - umin, v=(vmin, vmax))
        return d

    def free(self, p, direction) -> bool:
        """True when a ray from p along direction leaves the part without touching it."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        self._ray.Perform(gp_Lin(gp_Pnt(*p), gp_Dir(*direction)), 0.0, 1e9)
        return self._ray.NbPnt() == 0

    def inside(self, p) -> bool:
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        self._cls.Perform(gp_Pnt(*p), 1e-6)
        return self._cls.State() == TopAbs_IN


def _finding(rule, severity, title, detail, suggestion="", cost_effect="", points=None, faces=None, count=1) -> dict:
    pts = [p for p in (points or []) if p is not None]
    return {"rule": rule, "severity": severity, "title": title, "detail": detail, "suggestion": suggestion, "cost_effect": cost_effect,
            "count": count, "location": {"point": pts[0] if pts else None, "points": pts[:50], "faces": (faces or [])[:50]}}


# ---------------------------------------------------------------- checks
def _thin_walls(m: _Model, limit_in: float, R: dict) -> list[dict]:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    planes = [f for f in m.info if f["kind"] == "plane" and f["normal"]]
    if len(planes) > R["max_planar_faces"]:
        return [_finding("thin_wall", "info", "Thin walls not checked", f"The model has {len(planes)} flat faces; the wall check was skipped to stay fast.")]
    limit = limit_in * IN
    walls = []
    for a_i, a in enumerate(planes):
        for b in planes[a_i + 1:]:
            if sum(x * y for x, y in zip(a["normal"], b["normal"])) > -0.999:
                continue
            gap = sum(x * y for x, y in zip(_sub(a["point"], b["point"]), a["normal"]))
            if not (1e-4 < gap < limit):
                continue  # gap <= 0 means the faces look at each other across empty space (a slot)
            dss = BRepExtrema_DistShapeShape(m.faces[a["i"]], m.faces[b["i"]])
            if not dss.IsDone() or dss.NbSolution() == 0 or abs(dss.Value() - gap) > 1e-3:
                continue  # the faces do not overlap where they face each other
            # closest points often sit on the overlap's corners; their average is in the middle of it
            mids = [tuple((x + y) / 2 for x, y in zip(_v(dss.PointOnShape1(k)), _v(dss.PointOnShape2(k)))) for k in range(1, dss.NbSolution() + 1)]
            mid = tuple(sum(c) / len(mids) for c in zip(*mids))
            if not m.inside(mid) and not any(m.inside(_add(q, _sub(mid, q), 0.05)) for q in mids):
                continue
            walls.append((gap, mid, [a["id"], b["id"]]))
    if not walls:
        return []
    walls.sort(key=lambda w: w[0])
    thinnest = walls[0][0] / IN
    return [_finding(
        "thin_wall", "warn", f"Thin wall {thinnest:.3f} in",
        f"{len(walls)} wall(s) thinner than {limit_in:.3f} in; the thinnest is {thinnest:.3f} in ({walls[0][0]:.2f} mm). Thin walls chatter, "
        "deflect under the tool and are hard to hold to tolerance.",
        f"Thicken to at least {limit_in:.3f} in, or accept slower finishing passes and a looser tolerance there.",
        "slower finishing passes, possible scrap", points=[_in(w[1]) for w in walls], faces=[f for w in walls for f in w[2]], count=len(walls))]


def _holes(m: _Model, process: str, R: dict, sheet_t: float | None) -> list[dict]:
    from . import inserts

    try:
        holes = inserts.find_holes(m.shape)
    except Exception:  # noqa: BLE001
        return []
    out = []
    groups: dict[tuple, list] = {}
    for h in holes:
        d_in = h["diameter_mm"] / IN
        depth_in = h["depth_mm"] / IN
        center = _in(tuple((a + b) / 2 for a, b in zip(h["start"], h["end"])))
        if process == "sheet_metal":
            if sheet_t and d_in < sheet_t - 1e-4:
                groups.setdefault(("sheet_small", round(d_in, 4)), []).append(center)
            continue
        if process == "3d_print":
            continue
        ratio = depth_in / d_in if d_in else 0
        if ratio > R["hole_depth_ratio_extreme"]:
            groups.setdefault(("deep_extreme", round(d_in, 4), round(depth_in, 3)), []).append(center)
        elif ratio > R["hole_depth_ratio_warn"]:
            groups.setdefault(("deep", round(d_in, 4), round(depth_in, 3)), []).append(center)
        if d_in < R["min_hole_in"]:
            groups.setdefault(("tiny", round(d_in, 4)), []).append(center)
        if d_in <= R["drill_check_max_in"]:
            name, dd = nearest_drill(d_in)
            if abs(dd - d_in) > R["drill_match_in"]:
                groups.setdefault(("odd", round(d_in, 4), name, dd), []).append(center)
    for key, pts in groups.items():
        kind, n = key[0], len(pts)
        each = f"{n} hole(s)" if n > 1 else "1 hole"
        if kind == "deep_extreme":
            d, depth = key[1], key[2]
            out.append(_finding("hole_depth", "warn", f"Very deep hole: {depth / d:.0f}x diameter",
                                f"{each} {d:.4f} in diameter, {depth:.3f} in deep ({depth / d:.1f}x). Past about 10x a standard drill wanders and chips pack.",
                                "Shorten the hole, drill from both sides, or open up the diameter.", "gun drill or EDM, long cycle", pts, count=n))
        elif kind == "deep":
            d, depth = key[1], key[2]
            out.append(_finding("hole_depth", "cost", f"Deep hole: {depth / d:.1f}x diameter",
                                f"{each} {d:.4f} in diameter, {depth:.3f} in deep. Deeper than 4x diameter needs peck drilling.",
                                "Keep depth at 4x diameter or less where the design allows.", "peck drilling, longer cycle", pts, count=n))
        elif kind == "tiny":
            d = key[1]
            out.append(_finding("small_hole", "warn", f"Very small hole: {d:.4f} in",
                                f"{each} under {R['min_hole_in']:.3f} in. Micro drills are slow and break easily.",
                                "Use 0.040 in or larger (0.1 in is easy) unless the function needs it.", "micro tooling, slower cycle", pts, count=n))
        elif kind == "odd":
            d, name, dd = key[1], key[2], key[3]
            out.append(_finding("drill_size", "info", f"Non-standard hole size {d:.4f} in",
                                f"{each} {d:.4f} in is not a standard drill; the nearest is {name} ({dd:.4f} in).",
                                f"Use {name} ({dd:.4f} in) if the fit allows; otherwise it gets reamed, bored or interpolated.",
                                "extra ream or interpolation pass", pts, count=n))
        elif kind == "sheet_small":
            d = key[1]
            out.append(_finding("sheet_small_hole", "info", f"Hole smaller than the thickness ({d:.4f} in)",
                                f"{each} smaller than the {sheet_t:.4f} in sheet. A punch cannot make holes smaller than the material thickness.",
                                "Laser cut or drill it, or enlarge it to at least the thickness.", "laser or drill instead of punch", pts, count=n))
    return out


def _edge_faces(m: "_Model") -> list[tuple]:
    """Every edge with the indexes of the faces that share it: [(edge, [face_i, ...]), ...]."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    if getattr(m, "_edges", None) is not None:
        return m._edges
    buckets: dict[int, list] = {}
    for i, f in enumerate(m.faces):
        ex = TopExp_Explorer(f, TopAbs_EDGE)
        while ex.More():
            e = ex.Current()
            row = next((r for r in buckets.setdefault(hash(e), []) if r[0].IsSame(e)), None)
            if row is None:
                buckets[hash(e)].append((e, [i]))
            elif i not in row[1]:
                row[1].append(i)
            ex.Next()
    m._edges = [r for rows in buckets.values() for r in rows]
    return m._edges


def _sharp_corners(m: _Model, R: dict) -> list[dict]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopoDS import TopoDS

    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    eps = max(0.02, m.size * 1e-4)
    hits = []
    for edge, idx in _edge_faces(m):
        if len(idx) != 2:
            continue
        fa, fb = m.info[idx[0]], m.info[idx[1]]
        if fa["kind"] != "plane" or fb["kind"] != "plane" or not fa["normal"] or not fb["normal"]:
            continue
        n1, n2 = fa["normal"], fb["normal"]
        if abs(sum(x * y for x, y in zip(n1, n2))) > 0.99:
            continue
        c = BRepAdaptor_Curve(to_edge(edge))
        if c.GetType() != GeomAbs_Line:
            continue
        p0, p1 = _v(c.Value(c.FirstParameter())), _v(c.Value(c.LastParameter()))
        length = math.dist(p0, p1)
        if length < 0.25:
            continue
        mid = tuple((a + b) / 2 for a, b in zip(p0, p1))
        if not m.inside(_add(mid, _norm(_sub(n1, n2)), eps)):
            continue  # convex (outside) edge
        void = _add(mid, _norm(_add(n1, n2)), eps)
        if m.free(void, n1) or m.free(void, n2):
            continue  # a flat-bottom tool along one face's normal makes this corner sharp: a floor or a shoulder
        hits.append((length, _in(mid), [fa["id"], fb["id"]]))
    if not hits:
        return []
    deepest = max(h[0] for h in hits) / IN
    r = max(math.ceil(deepest * R["corner_radius_fraction_of_depth"] * 64) / 64, 1 / 32)
    return [_finding("sharp_internal_corner", "warn", f"{len(hits)} sharp internal corner(s)",
                     f"Concave vertical corners with no radius, up to {deepest:.3f} in deep. A rotating end mill always leaves a radius "
                     "equal to its own, so a truly sharp inside corner needs wire or sinker EDM or broaching.",
                     f"Add a corner radius of at least {r:.4f} in (about 1/3 of the depth), slightly larger than a standard end mill radius. "
                     "If a square part must fit, use dog-bone or T-bone relief cuts instead.",
                     "EDM or extra op", [h[1] for h in hits], [f for h in hits for f in h[2]], count=len(hits))]


def _corner_radii(m: _Model, R: dict, thin_dir) -> list[dict]:
    hits = []
    for f in m.info:
        if f["kind"] != "cylinder" or not f.get("concave") or f["span"] >= 2 * math.pi - 0.05:
            continue
        r = f["r"]
        height = abs(f["v"][1] - f["v"][0])
        if r <= 0 or height <= 0:
            continue
        d = f["axis_d"]
        mid = _add(f["axis_p"], d, (f["v"][0] + f["v"][1]) / 2)
        up, down = m.free(mid, d), m.free(mid, tuple(-x for x in d))
        vertical = (up != down) or (up and down and abs(sum(x * y for x, y in zip(d, thin_dir))) > 0.99)
        if not vertical:
            continue
        ratio = height / (2 * r)
        if ratio > R["corner_depth_to_tool_dia"]:
            hits.append((ratio, r, height, _in(mid), f["id"]))
    if not hits:
        return []
    hits.sort(key=lambda h: -h[0])
    ratio, r, height, _, _ = hits[0]
    want = max(height / (2 * R["corner_depth_to_tool_dia"]), height * R["corner_radius_fraction_of_depth"] / 2)
    return [_finding("corner_radius_depth", "cost", "Small corner radius in a deep pocket",
                     f"{len(hits)} internal corner radius(es); the worst is {r / IN:.4f} in at {height / IN:.3f} in deep, "
                     f"{ratio:.1f}x the largest tool that fits ({2 * r / IN:.4f} in diameter).",
                     f"Open the corner radius to {want / IN:.4f} in or more so a stiffer tool can reach, or reduce the pocket depth.",
                     "long-reach small tool, slow passes", [h[3] for h in hits], [h[4] for h in hits], count=len(hits))]


def _obb_axes(shape):
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepBndLib import BRepBndLib

    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, obb, True, True, False)
    axes = [obb.XDirection(), obb.YDirection(), obb.ZDirection()]
    sizes = [obb.XHSize(), obb.YHSize(), obb.ZHSize()]
    dirs = [(a.X(), a.Y(), a.Z()) for a in axes]
    return dirs, dirs[sizes.index(min(sizes))]


def _setups(m: _Model, axes, R: dict) -> list[dict]:
    from . import inserts

    dirs = []
    for a in axes:
        dirs += [a, tuple(-x for x in a)]
    eps = max(0.02, m.size * 1e-4)
    covers = {i: set() for i in range(len(dirs))}
    features = []
    angled, undercut, chamfers = [], [], 0
    for f in m.info:
        if f["kind"] != "plane" or not f["normal"]:
            continue
        n = f["normal"]
        dots = [sum(x * y for x, y in zip(n, d)) for d in dirs]
        floor = [i for i, v in enumerate(dots) if v > 0.999]
        wall = [i for i, v in enumerate(dots) if abs(v) < 0.001]
        if not floor and not wall:
            if any(abs(abs(v) - math.sqrt(0.5)) < 0.03 for v in dots) and f["area"] < 0.02 * m.size ** 2:
                chamfers += 1
            else:
                angled.append(f)
            continue
        start = _add(f["point"], n, eps)
        ok = [i for i in floor + wall if m.free(start, dirs[i])]
        key = len(features)
        features.append(f["id"])
        if not ok:
            undercut.append(f)
        for i in ok:
            covers[i].add(key)
    try:
        holes = inserts.find_holes(m.shape)
    except Exception:  # noqa: BLE001
        holes = []
    angled_holes = 0
    for h in holes:
        options = []
        hd = tuple(h["axis"])
        for i, d in enumerate(dirs):
            v = sum(x * y for x, y in zip(hd, d))
            if (h["open_end"] and v > 0.999) or (h["open_start"] and v < -0.999):
                options.append(i)
        if not options:
            if not any(abs(abs(sum(x * y for x, y in zip(hd, d))) - 1) < 0.001 for d in dirs):
                angled_holes += 1
            continue
        key = len(features)
        features.append(h["id"])
        for i in options:
            covers[i].add(key)
    need = set().union(*covers.values()) if covers else set()
    chosen = []
    while need:
        i = max(covers, key=lambda k: len(covers[k] & need))
        if not covers[i] & need:
            break
        chosen.append(i)
        need -= covers[i]
    out = []
    n = max(len(chosen), 1)
    if n > 2:
        out.append(_finding("setups", "cost", f"{n} setups to reach every face",
                            f"Faces or holes open toward {n} different directions. A 3-axis mill reaches one direction per setup; "
                            "the usual allowance is two (top and bottom).",
                            "Move side holes and features to the top or bottom faces if the design allows, or quote it on a 4th axis.",
                            f"+{n - 2} setup(s)", count=n))
    if undercut:
        out.append(_finding("undercut", "cost", f"{len(undercut)} undercut face(s)",
                            "Faces that no straight tool path from the six main directions can reach (an undercut, T-slot or dovetail).",
                            "Open the feature to a side, or allow a T-slot or dovetail cutter, or split the part.",
                            "special cutter or EDM, extra setup", [_in(f["point"]) for f in undercut], [f["id"] for f in undercut], count=len(undercut)))
    if angled or angled_holes:
        out.append(_finding("angled_features", "cost", f"{len(angled) + angled_holes} angled face(s) or hole(s)",
                            "Features that are not square to the part need a tilted fixture, a 4th axis or 5-axis machining.",
                            "Square them to the part where the design allows, or quote 5-axis time.",
                            "+1 setup or 5-axis", [_in(f["point"]) for f in angled], [f["id"] for f in angled], count=len(angled) + angled_holes))
    if chamfers:
        out.append(_finding("chamfers", "info", f"{chamfers} chamfer(s)", "45 degree faces read as chamfers, cut with a chamfer mill in the same setup.", count=chamfers))
    return out


def _sheet(m: _Model, geometry: dict, material: str, R: dict) -> list[dict]:
    from . import inserts
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    sm = geometry.get("sheet_metal") or {}
    t_in = sm.get("thickness")
    out = []
    if not t_in:
        return [_finding("sheet_not_detected", "info", "No constant sheet thickness found",
                         "The model does not read as formed sheet metal, so the bend checks were skipped.")]
    t = t_in * IN
    to_vertex = getattr(TopoDS, "Vertex_s", None) or TopoDS.Vertex
    cyls = [f for f in m.info if f["kind"] == "cylinder" and f["span"] < 2 * math.pi - 0.05]
    bends = []
    for f in cyls:
        if not f["concave"]:
            continue
        for g in cyls:
            if g["concave"] or abs(g["r"] - f["r"] - t) > max(0.15 * t, 0.1):
                continue
            if cad._same_line(f["axis_p"], f["axis_d"], g["axis_p"], g["axis_d"], 0.01):
                bends.append(f)
                break
    small_r = [b for b in bends if b["r"] < R["sheet_min_bend_radius_t"] * t - 1e-3]
    if small_r:
        r_min = min(b["r"] for b in small_r) / IN
        alu = any(w in (material or "").lower() for w in ("6061", "2024", "7075"))
        out.append(_finding("bend_radius", "warn", f"Bend radius {r_min:.4f} in is under the thickness",
                            f"{len(small_r)} bend(s) with an inside radius smaller than the {t_in:.4f} in thickness. Tight bends crack on the "
                            "outside, and standard press brake tooling may not make them.",
                            f"Use an inside radius of at least {t_in:.4f} in (1x thickness)" + (" ; 6061 and other hard aluminum alloys usually need 4x to 8x." if alu else "."),
                            "special tooling or cracked bends", [_in(_add(b["axis_p"], b["axis_d"], sum(b["v"]) / 2)) for b in small_r],
                            [b["id"] for b in small_r], count=len(small_r)))
    # holes near bends
    try:
        holes = [h for h in inserts.find_holes(m.shape) if h["depth_mm"] <= 1.6 * t]
    except Exception:  # noqa: BLE001
        holes = []
    near = []
    for h in holes:
        hd, hp = tuple(h["axis"]), tuple(h["axis_point"])
        rh = h["diameter_mm"] / 2
        for b in bends:
            bd = b["axis_d"]
            c = _cross(hd, bd)
            cn = math.sqrt(sum(x * x for x in c))
            if cn < 0.95:
                continue
            along = abs(sum(x * y for x, y in zip(_sub(hp, b["axis_p"]), c))) / cn
            edge = along - rh
            if edge < R["sheet_hole_to_bend_t"] * t:
                near.append((edge, _in(tuple((x + y) / 2 for x, y in zip(h["start"], h["end"]))), h["diameter_mm"] / IN))
                break
    if near:
        worst = min(n[0] for n in near) / IN
        out.append(_finding("hole_near_bend", "warn", f"{len(near)} hole(s) too close to a bend",
                            f"Hole edge {worst:.4f} in from the start of the bend; keep at least {R['sheet_hole_to_bend_t']:g}x thickness "
                            f"({R['sheet_hole_to_bend_t'] * t_in:.4f} in) or the hole stretches into an oval when formed.",
                            f"Move the hole at least {R['sheet_hole_to_bend_t'] * t_in:.4f} in from the bend, add a relief slot, or cut it after forming.",
                            "distorted holes, or a post-form drill op", [n[1] for n in near], count=len(near)))
    # flange length: flat run of each planar face next to a bend, plus radius and thickness
    short = []
    edges = _edge_faces(m)
    for b in bends:
        bd = b["axis_d"]
        neighbours = {j for _, idx in edges if b["i"] in idx for j in idx if j != b["i"]}
        for j in neighbours:
            fi = m.info[j]
            if fi["kind"] != "plane" or not fi["normal"] or abs(sum(x * y for x, y in zip(fi["normal"], bd))) > 0.1:
                continue
            u = _norm(_cross(fi["normal"], bd))
            ex = TopExp_Explorer(m.faces[j], TopAbs_VERTEX)
            run = 0.0
            while ex.More():
                p = _v(BRep_Tool.Pnt_s(to_vertex(ex.Current())))
                run = max(run, abs(sum(x * y for x, y in zip(_sub(p, b["axis_p"]), u))))
                ex.Next()
            flange = run + b["r"] + t
            if flange < R["sheet_min_flange_t"] * t - 1e-3:
                short.append((flange, _in(fi["point"]), fi["id"]))
    if short:
        worst = min(s[0] for s in short) / IN
        out.append(_finding("short_flange", "warn", f"Flange {worst:.4f} in is too short to form",
                            f"{len(short)} flange(s) shorter than {R['sheet_min_flange_t']:g}x thickness ({R['sheet_min_flange_t'] * t_in:.4f} in) "
                            "measured from the outside of the bend. The flange cannot sit across the V-die.",
                            f"Lengthen the flange to {R['sheet_min_flange_t'] * t_in:.4f} in or more, or form it oversize and trim.",
                            "special tooling or a trim op", [s[1] for s in short], [s[2] for s in short], count=len(short)))
    return out


# ---------------------------------------------------------------- entry points
def _wall_limit(process: str, material: str, config: dict | None, R: dict) -> tuple[float, str]:
    walls = R["thin_wall_in"]
    if process == "3d_print":
        tech = (((config or {}).get("additive") or {}).get("materials") or {}).get(material, {}).get("tech", "fdm")
        key = "sla" if tech == "sla" else "fdm"
        return walls[key], f"{key.upper()} printing"
    from .flat import material_class
    cls = material_class(material) if material else "ferrous"
    if cls in ("plastic", "composite", "wood"):
        return walls["plastic"], "machined plastic"
    return walls["metal"], "machined metal"


def check(shape, geometry: dict, process: str = "auto", material: str = "", config: dict | None = None) -> dict:
    """Run the checks that apply to `process` on a loaded shape. Returns {process, findings, counts, note}."""
    R = rules(config)
    if process in (None, "", "auto"):
        process = geometry.get("suggested_process") or "cnc_mill"
    valid = ("cnc_mill", "cnc_lathe", "sheet_metal", "3d_print")
    if process not in valid:
        raise cad.CadError(f"process must be auto or one of {list(valid)}")
    m = _Model(shape)
    axes, thin_dir = _obb_axes(shape)
    findings: list[dict] = []
    if process != "sheet_metal":
        limit, label = _wall_limit(process, material, config, R)
        findings += [dict(f, detail=f["detail"] + f" Limit used: {label}.") for f in _thin_walls(m, limit, R)]
    sheet_t = (geometry.get("sheet_metal") or {}).get("thickness")
    findings += _holes(m, process, R, sheet_t)
    if process == "cnc_mill":
        findings += _sharp_corners(m, R)
        findings += _corner_radii(m, R, thin_dir)
        findings += _setups(m, axes, R)
        if (geometry.get("faces") or {}).get("freeform"):
            findings.append(_finding("freeform", "cost", "Contoured 3D surfaces",
                                     f"{geometry['faces']['freeform']} freeform surface(s) need 3D toolpaths with a ball end mill and fine stepovers.",
                                     "Flatten or simplify cosmetic contours if they are not functional.", "longer cycle and CAM time"))
    if process == "sheet_metal":
        findings += _sheet(m, geometry, material, R)
    if (geometry.get("solids") or 1) > 1:
        findings.append(_finding("multiple_bodies", "info", f"{geometry['solids']} bodies in one file",
                                 "These checks treat all bodies together. Split the file to check and quote each body on its own."))
    order = {"warn": 0, "cost": 1, "info": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    for i, f in enumerate(findings, 1):
        f["id"] = f"d{i}"
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ("warn", "cost", "info")}
    return {"process": process, "material": material, "findings": findings, "counts": counts, "note": customer_note(findings, process),
            "rules": R}


def customer_note(findings: list[dict], process: str = "") -> str:
    """Plain text a quoter can paste into the customer quote."""
    if not findings:
        return "Manufacturability review: no issues found for " + (process.replace("_", " ") or "this process") + "."
    lines = ["Manufacturability review" + (f" ({process.replace('_', ' ')})" if process else "") + ":"]
    for f in findings:
        if f["severity"] == "info" and f["rule"] in ("chamfers", "multiple_bodies"):
            continue
        s = f"- {f['title']}. {f['detail']}"
        if f.get("suggestion"):
            s += f" Suggestion: {f['suggestion']}"
        if f.get("cost_effect"):
            s += f" Cost effect if unchanged: {f['cost_effect']}."
        lines.append(s)
    lines.append("These are design suggestions; the quote is based on the model as supplied.")
    return "\n".join(lines)


def check_file(file_id: str, process: str = "auto", material: str = "", config: dict | None = None) -> dict:
    from . import cad_quote

    d = cad_quote.load(file_id)
    shape = cad.load_step(cad_quote.step_path(file_id))
    out = check(shape, d["geometry"], process, material, config)
    out["file_id"] = file_id
    out["filename"] = d["filename"]
    return out
