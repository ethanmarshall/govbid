"""Generate the STEP fixtures for tests/test_dfm.py and tests/test_assembly.py (needs cadquery-ocp).

    python3 tests/fixtures/cad/make_dfm_fixtures.py

thin_wall.step   60 x 40 x 20 mm block with an open-top pocket 15 mm deep whose side wall at x = 60 is
                 0.5 mm thick (0.020 in). The pocket's four vertical corners are sharp.
deep_hole.step   20 x 20 x 60 mm block with: a 3 mm hole 50 mm deep from the top (16.7 x D), a 0.8 mm
                 hole 5 mm deep, a 0.270 in through hole (not a standard drill), a 0.201 in (#7 drill)
                 hole 10 mm deep, and 4 mm holes 8 mm deep into the y = 0 and x = 20 side faces (three setups).
bad_bend.step    sheet-metal L bracket 1.5 mm thick, 20 mm wide: inside bend radius 0.5 mm (less than the
                 thickness), a 30 mm flange with a 3 mm hole whose edge is 1.5 mm from the bend and a
                 4 mm hole far from it, and a 3 mm short flange.
weldment.step    three plates as separate solids: a 100 x 50 x 6 mm base and two identical 100 x 6 x 40 mm
                 uprights standing on it (two fillet-weld joints, each 100 mm long).
"""
import math
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.Interface import Interface_Static
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

HERE = Path(__file__).parent
IN = 25.4


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def cyl(p, d, r, h, angle=None):
    ax = gp_Ax2(gp_Pnt(*p), gp_Dir(*d))
    return (BRepPrimAPI_MakeCylinder(ax, r, h, angle) if angle else BRepPrimAPI_MakeCylinder(ax, r, h)).Shape()


def cut(a, b):
    return BRepAlgoAPI_Cut(a, b).Shape()


def unify(s):
    u = ShapeUpgrade_UnifySameDomain(s, True, True, True)
    u.Build()
    return u.Shape()


def write(shape, name):
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    w.Write(str(HERE / name))


def thin_wall():
    s = box(0, 0, 0, 60, 40, 20)
    s = cut(s, box(5, 5, 5, 54.5, 30, 20))  # pocket x 5..59.5, wall 59.5..60 = 0.5 mm
    return s


def deep_hole():
    s = box(0, 0, 0, 20, 20, 60)
    s = cut(s, cyl((5, 5, 10), (0, 0, 1), 1.5, 51))          # 3 mm x 50 deep (top at z=60)
    s = cut(s, cyl((15, 5, 55), (0, 0, 1), 0.4, 6))          # 0.8 mm x 5 deep
    s = cut(s, cyl((5, 15, -1), (0, 0, 1), 0.27 * IN / 2, 62))   # 0.270 in through
    s = cut(s, cyl((15, 15, 50), (0, 0, 1), 0.201 * IN / 2, 11))  # #7 drill, 10 deep
    s = cut(s, cyl((10, -1, 30), (0, 1, 0), 2.0, 9))          # side hole 4 mm x 8 deep
    s = cut(s, cyl((21, 10, 15), (-1, 0, 0), 2.0, 9))         # second side hole, on the x = 20 face
    return s


def bad_bend():
    t, r, w = 1.5, 0.5, 20.0
    # MakeCylinder sweeps from the Ax2 X direction; X = -Z puts the quarter ring in the x<0, z<0 quadrant
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0), gp_Dir(0, 0, -1))
    outer = BRepPrimAPI_MakeCylinder(ax, r + t, w, math.pi / 2).Shape()
    inner = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0), gp_Dir(0, 0, -1)), r, w, math.pi / 2).Shape()
    ring = cut(outer, inner)
    a = box(0, 0, -(r + t), 30, w, t)          # flange A along +x
    b = box(-(r + t), 0, 0, t, w, 3.0)         # short flange B up +z
    s = BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(ring, a).Shape(), b).Shape()
    s = cut(s, cyl((3.0, 10, -5), (0, 0, 1), 1.5, 10))   # hole edge 1.5 mm from the bend tangent
    s = cut(s, cyl((22.0, 10, -5), (0, 0, 1), 2.0, 10))  # far hole
    return unify(s)


def weldment():
    comp = TopoDS_Compound()
    bld = BRep_Builder()
    bld.MakeCompound(comp)
    for s in (box(0, 0, 0, 100, 50, 6), box(0, 5, 6, 100, 6, 40), box(0, 39, 6, 100, 6, 40)):
        bld.Add(comp, s)
    return comp


if __name__ == "__main__":
    write(thin_wall(), "thin_wall.step")
    write(deep_hole(), "deep_hole.step")
    write(bad_bend(), "bad_bend.step")
    write(weldment(), "weldment.step")
    print("wrote DFM and assembly fixtures")
