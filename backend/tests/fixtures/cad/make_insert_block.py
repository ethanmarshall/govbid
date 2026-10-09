"""Generate insert_block.step for the heat-set insert tests (needs cadquery-ocp).

    python3 tests/fixtures/cad/make_insert_block.py

A 40 x 30 x 12 mm block with: two M3 tap-drill (2.5 mm) blind holes 8 mm deep from the top,
one #6-32 tap-drill (#36, 0.1065 in = 2.705 mm) through hole, and one 5.6 mm through hole that
matches no thread in the insert table.
"""
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

HERE = Path(__file__).parent
HOLES = [  # (x, y, diameter, z_bottom)  top face is z = 12
    (8, 8, 2.5, 4.0),
    (8, 22, 2.5, 4.0),
    (20, 15, 2.705, -1.0),
    (32, 15, 5.6, -1.0),
]


def build():
    shape = BRepPrimAPI_MakeBox(40, 30, 12).Shape()
    for x, y, d, zb in HOLES:
        cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, zb), gp_Dir(0, 0, 1)), d / 2, 14 - zb).Shape()
        shape = BRepAlgoAPI_Cut(shape, cyl).Shape()
    return shape


if __name__ == "__main__":
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    w = STEPControl_Writer()
    w.Transfer(build(), STEPControl_AsIs)
    w.Write(str(HERE / "insert_block.step"))
    print("wrote insert_block.step")
