"""Writes vendor_asm.step: a base plate with two copies of a bought three-piece unit whose bodies carry only the
sub-assembly instance name ("Slide Unit <1>"), the way Onshape exports vendor CAD. For the make-or-buy tests.
Run from backend/: python3 tests/fixtures/cad/make_vendor_asm.py"""
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
TDataStd_Name.Set_s(asm, TCollection_ExtendedString("Fixture"))


def add(shape, name):
    lab = st.AddShape(shape, False)
    TDataStd_Name.Set_s(lab, TCollection_ExtendedString(name))
    st.AddComponent(asm, lab, TopLoc_Location())


add(BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 150.0, 100.0, 10.0).Shape(), "Base Plate")
for i, x in ((1, 20.0), (2, 90.0)):
    n = f"Slide Unit <{i}>"
    add(BRepPrimAPI_MakeBox(gp_Pnt(x, 30, 10), 40.0, 20.0, 12.0).Shape(), n)          # carriage
    add(BRepPrimAPI_MakeBox(gp_Pnt(x + 5, 32, 22), 30.0, 16.0, 4.0).Shape(), n)      # cap
    add(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x + 20, 40, 26), gp_Dir(0, 0, 1)), 4.0, 15.0).Shape(), n)  # knob
st.UpdateAssemblies()
w = STEPCAFControl_Writer()
w.SetNameMode(True)
w.Transfer(doc, STEPControl_AsIs)
out = Path(__file__).with_name("vendor_asm.step")
assert w.Write(str(out)) == IFSelect_RetDone
print(out)
