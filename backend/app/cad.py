"""Read STEP files and measure what drives manufacturing cost.

Uses OpenCascade (the `cadquery-ocp` package) to load the solid and report, in inches:
  - oriented bounding box, volume, surface area, face counts by surface type
  - holes (concave cylinders, merged when split into halves) with diameter and axis
  - turned diameters (convex cylinders) and whether the part looks like a lathe part
  - sheet-metal signs: constant thickness, bends (coaxial inner/outer cylinder pairs),
    flat-pattern area and cut length estimated from volume and area
  - a triangle mesh for the 3D viewer
The process guess is a starting point; the quote page lets you override it.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

MM_PER_IN = 25.4


class CadError(ValueError):
    pass


def _ocp():
    try:
        import OCP  # noqa: F401
    except ImportError as exc:  # pragma: no cover - only when the package is missing
        raise CadError("STEP support needs the 'cadquery-ocp' package: pip install cadquery-ocp") from exc


def load_step(path: Path):
    _ocp()
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Reader

    Interface_Static.SetCVal_s("xstep.cad.unit", "MM")  # OCCT works in mm; we convert to inches
    r = STEPControl_Reader()
    if r.ReadFile(str(path)) != IFSelect_RetDone:
        raise CadError("Could not read the STEP file. Export it again as STEP AP203 or AP214.")
    r.TransferRoots()
    shape = r.OneShape()
    if shape is None or shape.IsNull():
        raise CadError("The STEP file has no geometry.")
    return shape


def _faces(shape):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face  # OCP 7 uses Face_s, OCP 8 uses Face
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        yield to_face(ex.Current())
        ex.Next()


def _count(shape, kind) -> int:
    from OCP.TopExp import TopExp_Explorer

    n, ex = 0, TopExp_Explorer(shape, kind)
    while ex.More():
        n += 1
        ex.Next()
    return n


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _parallel(a, b, tol=1e-3):
    return abs(abs(_dot(a, b)) - 1) < tol


def _same_line(p1, d1, p2, d2, tol):
    """Two axes are the same line: parallel and the offset between them lies along the axis."""
    if not _parallel(d1, d2):
        return False
    v = [b - a for a, b in zip(p1, p2)]
    along = _dot(v, d1)
    perp = [vi - along * di for vi, di in zip(v, d1)]
    return math.sqrt(_dot(perp, perp)) < tol


def analyze(shape) -> dict:
    """Measure a solid. All lengths in inches, areas in in², volumes in in³."""
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp, BRepGProp_Face
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopAbs import TopAbs_SOLID

    k = 1 / MM_PER_IN
    vp, sp = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    BRepGProp.SurfaceProperties_s(shape, sp)
    volume = abs(vp.Mass()) * k ** 3
    area = sp.Mass() * k ** 2
    if volume <= 0:
        raise CadError("No closed solid found. Export the part as a solid body, not surfaces.")

    obb = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, obb, True, True, False)
    dims = sorted((2 * obb.XHSize() * k, 2 * obb.YHSize() * k, 2 * obb.ZHSize() * k), reverse=True)
    axes = [obb.XDirection(), obb.YDirection(), obb.ZDirection()]
    sizes = [obb.XHSize(), obb.YHSize(), obb.ZHSize()]
    thin_axis = axes[sizes.index(min(sizes))]
    thin_dir = (thin_axis.X(), thin_axis.Y(), thin_axis.Z())

    counts = {"plane": 0, "cylinder": 0, "cone": 0, "sphere": 0, "torus": 0, "freeform": 0}
    cyls = []  # (radius_in, axis_point_mm, axis_dir, concave, span_rad, area_in2)
    planes = []  # (normal, point_mm, area_in2)
    cyl_area = 0.0
    for f in _faces(shape):
        s = BRepAdaptor_Surface(f)
        t = s.GetType()
        if t == GeomAbs_Plane:
            counts["plane"] += 1
            pl = s.Plane()
            n = pl.Axis().Direction()
            o = pl.Location()
            fp = GProp_GProps()
            BRepGProp.SurfaceProperties_s(f, fp)
            planes.append(((n.X(), n.Y(), n.Z()), (o.X(), o.Y(), o.Z()), fp.Mass() * k ** 2))
        elif t == GeomAbs_Cylinder:
            counts["cylinder"] += 1
            c = s.Cylinder()
            ax = c.Axis()
            p0 = (ax.Location().X(), ax.Location().Y(), ax.Location().Z())
            d = (ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z())
            u = (s.FirstUParameter() + s.LastUParameter()) / 2
            v = (s.FirstVParameter() + s.LastVParameter()) / 2
            pnt, nrm = gp_Pnt(), gp_Vec()
            BRepGProp_Face(f).Normal(u, v, pnt, nrm)  # outward normal, face orientation applied
            radial = gp_Vec(pnt.X() - p0[0], pnt.Y() - p0[1], pnt.Z() - p0[2])
            along = radial.Dot(gp_Vec(*d))
            radial = radial - gp_Vec(*d).Multiplied(along)
            concave = nrm.Dot(radial) < 0  # normal points at the axis: a hole
            fp = GProp_GProps()
            BRepGProp.SurfaceProperties_s(f, fp)
            fa = fp.Mass() * k ** 2
            cyl_area += fa
            cyls.append((c.Radius() * k, p0, d, concave, s.LastUParameter() - s.FirstUParameter(), fa))
        elif t == GeomAbs_Cone:
            counts["cone"] += 1
        elif t == GeomAbs_Sphere:
            counts["sphere"] += 1
        elif t == GeomAbs_Torus:
            counts["torus"] += 1
        else:
            counts["freeform"] += 1

    tol_mm = 0.01
    # Merge cylinder faces that belong to the same feature (same axis line and radius)
    groups: list[dict] = []
    for r, p, d, concave, span, fa in cyls:
        for g in groups:
            if g["concave"] == concave and abs(g["r"] - r) < 1e-3 and _same_line(g["p"], g["d"], p, d, tol_mm):
                g["span"] += span
                g["area"] += fa
                break
        else:
            groups.append({"r": r, "p": p, "d": d, "concave": concave, "span": span, "area": fa})

    # Sheet metal thickness: distance from the largest flat face to the nearest parallel flat face.
    # Falls back to 2V/A, which reads low on small parts because edge faces add area.
    t_est = 2 * volume / area if area else 0
    if planes:
        big_n, big_o, big_a = max(planes, key=lambda x: x[2])
        gaps = []
        for n, o, a in planes:
            if _parallel(n, big_n) and a > 0.05 * big_a:
                d = abs(_dot([oi - bi for oi, bi in zip(o, big_o)], big_n)) * k
                if d > 1e-4:
                    gaps.append(d)
        if gaps and min(gaps) < 2.5 * t_est + 0.01:
            t_est = min(gaps)
    bends = []
    for g in groups:
        if g["concave"] and g["span"] < 2 * math.pi - 0.05:
            for h in groups:
                if (not h["concave"]) and abs(h["r"] - g["r"] - t_est) < max(0.15 * t_est, 0.004) and _same_line(g["p"], g["d"], h["p"], h["d"], tol_mm):
                    bends.append({"inner_radius": round(g["r"], 4), "angle_deg": round(math.degrees(g["span"]), 1)})
                    break
    bend_radii = {b["inner_radius"] for b in bends}
    if bends:  # outer radius minus inner radius is the exact thickness
        for g in groups:
            for h in groups:
                if g["concave"] and not h["concave"] and round(g["r"], 4) in bend_radii and _same_line(g["p"], g["d"], h["p"], h["d"], tol_mm):
                    t_est = h["r"] - g["r"]
                    break

    holes = []
    for g in groups:
        if g["concave"] and g["span"] >= 2 * math.pi - 0.05 and g["r"] not in bend_radii:
            depth = g["area"] / (2 * math.pi * g["r"]) if g["r"] else 0
            holes.append({"diameter": round(2 * g["r"], 4), "depth": round(depth, 4), "axis": [round(x, 4) for x in g["d"]]})
    holes.sort(key=lambda h: h["diameter"])

    convex = [g for g in groups if not g["concave"] and g["span"] >= 2 * math.pi - 0.05]
    turned = None
    if convex:
        main = max(convex, key=lambda g: g["area"])
        coax = [g for g in groups if _same_line(main["p"], main["d"], g["p"], g["d"], tol_mm) and not g["concave"]]
        coax_area = sum(g["area"] for g in coax)
        if coax_area > 0.4 * area:
            diams = sorted({round(2 * g["r"], 3) for g in coax}, reverse=True)
            axis_len = max(dims)  # turned parts are longest along the axis
            turned = {"max_diameter": diams[0], "diameters": diams, "length": round(axis_len, 4), "axis": [round(x, 4) for x in main["d"]]}

    min_dim = dims[2]
    thin_ratio = t_est / min_dim if min_dim else 0
    is_sheet = t_est <= 0.26 and (bends or (min_dim <= t_est * 1.15 and dims[1] > 6 * t_est))
    sheet = None
    if is_sheet:
        flat_area = volume / t_est
        cut_length = max((area - 2 * flat_area) / t_est, 0)
        sheet = {
            "thickness": round(t_est, 4),
            "bends": len(bends),
            "bend_details": bends,
            "flat_area": round(flat_area, 3),
            "cut_length": round(cut_length, 2),
            "holes_through_thickness": sum(1 for h in holes if h["depth"] <= 1.5 * t_est),
        }

    if sheet:
        process = "sheet_metal"
    elif turned:
        process = "cnc_lathe"
    else:
        process = "cnc_mill"

    # Setup estimate for milling: two sides plus one per extra axis with holes
    hole_axes = []
    for h in holes:
        if not any(_parallel(h["axis"], a, 0.05) for a in hole_axes):
            hole_axes.append(h["axis"])
    side_axes = [a for a in hole_axes if not _parallel(a, thin_dir, 0.05)]
    setups = min(2 + len(side_axes), 5)

    return {
        "units": "in",
        "bounding_box": {"length": round(dims[0], 4), "width": round(dims[1], 4), "height": round(dims[2], 4)},
        "volume": round(volume, 4),
        "surface_area": round(area, 3),
        "solids": _count(shape, TopAbs_SOLID),
        "faces": counts,
        "face_total": sum(counts.values()),
        "holes": holes,
        "turned": turned,
        "sheet_metal": sheet,
        "estimated_setups": setups,
        "suggested_process": process,
        "fill_ratio": round(volume / (dims[0] * dims[1] * dims[2]), 3) if all(dims) else None,
        "thin_ratio": round(thin_ratio, 3),
    }


def mesh(shape, max_triangles: int = 150_000) -> dict:
    """Triangulate for the browser viewer. Positions in inches, flat arrays."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    lo, hi = box.CornerMin(), box.CornerMax()
    diag = math.dist((lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())) or 1
    BRepMesh_IncrementalMesh(shape, diag * 0.002, False, 0.35, True)

    k = 1 / MM_PER_IN
    pos: list[float] = []
    idx: list[int] = []
    for f in _faces(shape):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        base = len(pos) // 3
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(trsf)
            pos.extend((p.X() * k, p.Y() * k, p.Z() * k))
        rev = f.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            idx.extend((base + a - 1, base + c - 1, base + b - 1) if rev else (base + a - 1, base + b - 1, base + c - 1))
        if len(idx) // 3 > max_triangles:
            break
    return {"positions": [round(v, 4) for v in pos], "indices": idx, "triangles": len(idx) // 3}


def file_id_for(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:24]


def analyze_file(path: Path, with_mesh: bool = True) -> dict:
    shape = load_step(path)
    out = {"geometry": analyze(shape)}
    if with_mesh:
        out["mesh"] = mesh(shape)
    return out
