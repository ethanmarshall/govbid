"""Writes named_asm.step: a small assembly whose bodies carry part names (base plate, two standoffs, a screw),
for the STEP + BOM tests. Run from backend/: python3 tests/fixtures/cad/make_named_asm.py"""
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool

doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())


asm = st.NewShape()
TDataStd_Name.Set_s(asm, TCollection_ExtendedString("Sensor mount"))


def add(shape, name):
    lab = st.AddShape(shape, False)
    TDataStd_Name.Set_s(lab, TCollection_ExtendedString(name))
    st.AddComponent(asm, lab, TopLoc_Location())


add(BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 120.0, 80.0, 8.0).Shape(), "VP-101 base plate")
for x in (20.0, 100.0):
    add(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, 40, 8), gp_Dir(0, 0, 1)), 6.0, 30.0).Shape(), "VP-102 standoff")
add(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(60, 40, 8), gp_Dir(0, 0, 1)), 3.0, 12.0).Shape(), "SHCS M6x12")
w = STEPCAFControl_Writer()
w.SetNameMode(True)
st.UpdateAssemblies()
w.Transfer(doc, STEPControl_AsIs)
out = Path(__file__).with_name("named_asm.step")
assert w.Write(str(out)) == IFSelect_RetDone
print(out)
