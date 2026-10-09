"""Generate the extrusion build test fixtures (PDF drawings, CSV and XLSX BOMs) in this folder.

    python3 tests/fixtures/extrusion/make_fixtures.py

Needs reportlab and openpyxl. The files are committed, so tests do not need to run this.
Part numbers, company names and drawing numbers are made up.
"""
import csv
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
W, H = landscape(letter)


def row(c, y, cells, xs, size=7.5):
    c.setFont("Helvetica", size)
    for x, text in zip(xs, cells):
        c.drawString(x, y, str(text))


def border(c):
    c.setLineWidth(1.2)
    c.rect(18, 18, W - 36, H - 36)
    c.setLineWidth(0.5)
    c.rect(60, 330, 260, 180)  # the frame sketch
    c.rect(75, 345, 230, 150)


def title_block(c, lines):
    c.rect(W - 330, 24, 306, 90)
    y = 100
    for ln in lines:
        row(c, y, [ln], [W - 324])
        y -= 11


def frame_bom():
    """Fractional 15 series test stand: SolidWorks style BOM (ITEM, PART NUMBER, DESCRIPTION, QTY) plus a cut list."""
    c = canvas.Canvas(str(HERE / "frame_bom.pdf"), pagesize=landscape(letter))
    border(c)
    xs = [360, 390, 460, 640]
    y = 560
    row(c, y, ["BILL OF MATERIALS"], [360], 8)
    y -= 12
    row(c, y, ["ITEM", "PART NUMBER", "DESCRIPTION", "QTY"], xs)
    bom = [
        ("1", "1515", '1.5" X 1.5" T-SLOT PROFILE', "8"),
        ("2", "HW-101", "DROP-IN T-NUT, 5/16-18, 15 SERIES", "32"),
        ("3", "HW-201", "4-HOLE CORNER BRACKET, 15 SERIES", "8"),
        ("4", "HW-301", "ANCHOR FASTENER ASSEMBLY", "4"),
        ("5", "PANEL-001", "PANEL, POLYCARB 1/4 x 24 x 36", "2"),
        ("6", "HW-401", "LEVELING FOOT, 5/16-18", "4"),
        ("7", "XYZ-999", "CUSTOM WIRE TRAY", "1"),
    ]
    for r in bom:
        y -= 11
        row(c, y, r, xs)
    y -= 24
    row(c, y, ["CUT LIST"], [360], 8)
    y -= 12
    xs2 = [360, 400, 460, 530, 570]
    row(c, y, ["MARK", "PART NUMBER", "LENGTH", "QTY", "MACHINING"], xs2)
    cuts = [
        ("A", "1515", "24.000", "4", "END TAP BOTH ENDS"),
        ("B", "1515", "36.000", "4", "2X ACCESS HOLE @ 7 1/4 IN, CBORE"),
    ]
    for r in cuts:
        y -= 11
        row(c, y, r, xs2)
    row(c, 250, ["NOTES:"], [40], 8)
    row(c, 238, ["1. ALL HARDWARE PER BOM."], [40])
    row(c, 227, ["2. BREAK ALL SHARP EDGES."], [40])
    title_block(c, ["TITLE: TEST STAND FRAME", "DWG NO TSF-1001", "REV A", "SCALE 1:10   SHEET 1 OF 1"])
    c.showPage()
    c.save()


def metric_bom():
    """Metric 40 series cart: ITEM QTY PART DESCRIPTION LENGTH order, bare mm lengths, miters."""
    c = canvas.Canvas(str(HERE / "metric_cart.pdf"), pagesize=landscape(letter))
    border(c)
    row(c, 540, ["DIMENSIONS ARE IN MILLIMETERS"], [360], 8)
    xs = [360, 390, 420, 480, 600, 660]
    y = 520
    row(c, y, ["ITEM", "QTY", "PART NO", "DESCRIPTION", "LENGTH", "MACHINING"], xs)
    rows = [
        ("1", "4", "40-4040", "PROFILE 40X40", "610", "45° MITER BOTH ENDS"),
        ("2", "2", "40-4080", "PROFILE 40X80", "1000", "2X END TAP"),
        ("3", "8", "HW-501", "GUSSETED CORNER BRACKET, M8", ""),
        ("4", "4", "HW-502", "LOCKING CASTER, M8", ""),
    ]
    for r in rows:
        y -= 11
        row(c, y, r, xs)
    title_block(c, ["TITLE: TRAINER CART", "DWG NO TC-2002", "REV B"])
    c.showPage()
    c.save()


def itar_scan():
    """A drawing with an export-control warning and no readable BOM (the BOM is an image in real life)."""
    c = canvas.Canvas(str(HERE / "itar_frame.pdf"), pagesize=landscape(letter))
    border(c)
    row(c, 60, ["WARNING - THIS DOCUMENT CONTAINS TECHNICAL DATA WHOSE EXPORT IS RESTRICTED BY THE ARMS EXPORT CONTROL ACT"], [40], 7)
    row(c, 48, ["(TITLE 22, U.S.C., SEC 2751, ET SEQ.) ITAR CONTROLLED. DISTRIBUTION STATEMENT D."], [40], 7)
    title_block(c, ["TITLE: ENCLOSURE FRAME", "DWG NO EF-3003", "REV A"])
    c.showPage()
    c.save()


BOM_CSV = [
    ["Item", "Qty", "Part Number", "Description", "Cut Length", "Machining", "Notes"],
    ["1", "4", "1010", "1 x 1 profile", '18"', "END TAP BOTH ENDS", ""],
    ["2", "2", "1020", "1 x 2 profile", "2 ft", "", ""],
    ["3", "16", "", "Slide-in T-nut 1/4-20", "", "", ""],
    ["4", "8", "", "Corner bracket", "", "", "10 series"],
    ["5", "1", "", "Acrylic panel 1/8 x 12 x 18", "", "", ""],
    ["6", "1", "", "Mystery widget", "", "", ""],
]
METRIC_CSV = [
    ["Qty", "Part", "Length (mm)", "Notes"],
    ["2", "30-3030", "500", ""],
    ["2", "30-3030", "250", "CBORE"],
]


def tables():
    with open(HERE / "bom.csv", "w", newline="") as f:
        csv.writer(f).writerows(BOM_CSV)
    with open(HERE / "bom_metric.csv", "w", newline="") as f:
        csv.writer(f).writerows(METRIC_CSV)
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Shop BOM for trainer frame"])
    ws.append([])
    for r in BOM_CSV:
        ws.append([int(x) if x.isdigit() and i in (0, 1) else x for i, x in enumerate(r)])
    wb.save(HERE / "bom.xlsx")


if __name__ == "__main__":
    frame_bom()
    metric_bom()
    itar_scan()
    tables()
    print("wrote fixtures to", HERE)
