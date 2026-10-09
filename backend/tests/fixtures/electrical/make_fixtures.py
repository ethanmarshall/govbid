"""Generate the electrical quoter test fixtures (wire lists, connector lists, panel BOM, plate list, drawing PDFs).

    python3 tests/fixtures/electrical/make_fixtures.py

Needs reportlab and openpyxl. The files are committed, so tests do not need to run this.
Part numbers, drawing numbers and company names are made up except mil-spec part numbers used as examples.
"""
import csv
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
W, H = landscape(letter)

WIRES = [
    # Wire ID, From, To, Gauge AWG, Color, Length (in), Wire spec, Shield/twist
    ("W1", "P1-1", "J2-A", "22", "WHT", "36", "M22759/16-22-9", ""),
    ("W2", "P1-2", "J2-B", "22", "BLK", "36", "M22759/16-22-0", ""),
    ("W3", "P1-3", "J2-C", "20", "RED", "48", "M22759/16-20-2", ""),
    ("W4", "P1-4", "TB1-1", "22", "GRN", "24", "M22759/16", "SHIELDED TWISTED PAIR"),
    ("W5", "P1-5", "J2-D", "18", "ORN", "36", "M22759/16", ""),
    ("W6", "P1-3", "P9-1", "22", "BLU", "12", "UL1007", ""),
]
BOM = [
    # Ref, Part number, Description, Qty, Backshell, Contacts
    ("P1", "D38999/26WB35PN", "PLUG, SIZE 22D CONTACTS", "1", "M85049/38S11W", "M39029/58-360"),
    ("J2", "MS3116F12-10S", "PLUG, SIZE 20 CONTACTS", "1", "", "M39029/56-351"),
    ("", "MS3367-1-9", "CABLE TIE", "6", "", ""),
]


def wires_csv():
    with open(HERE / "harness_wires.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Wire ID", "From", "To", "Gauge AWG", "Color", "Length (in)", "Wire spec", "Shield/twist"])
        w.writerows(WIRES)


def bom_csv():
    with open(HERE / "harness_bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Ref", "Part number", "Description", "Qty", "Backshell", "Contacts"])
        w.writerows(BOM)


def harness_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "Wire list"
    ws.append(["Harness HX-200 wire list"])
    ws.append([])
    ws.append(["Wire ID", "From Conn", "From Pin", "To Conn", "To Pin", "AWG", "Color", "Length (ft)", "Wire type"])
    ws.append(["101", "P1", "1", "P2", "1", 20, "WHT", 2, "M16878/4"])
    ws.append(["102", "P1", "2", "P2", "2", 20, "BLK", 2.5, "M16878/4"])
    ws2 = wb.create_sheet("Connectors")
    ws2.append(["Ref", "MPN", "Manufacturer", "Description", "Qty", "Unit price"])
    ws2.append(["P1", "1-480700-0", "TE", "CONNECTOR HOUSING 2 POS", 1, 0.42])
    ws2.append(["P2", "1-480698-0", "TE", "CONNECTOR HOUSING 2 POS", 1, 0.40])
    wb.save(HERE / "harness.xlsx")


def row(c, y, cells, xs, size=7.5):
    c.setFont("Helvetica", size)
    for x, text in zip(xs, cells):
        c.drawString(x, y, str(text))


def harness_pdf():
    c = canvas.Canvas(str(HERE / "harness_drawing.pdf"), pagesize=landscape(letter))
    c.rect(18, 18, W - 36, H - 36)
    y = 560
    row(c, y, ["WIRE LIST"], [40], 8)
    y -= 12
    xs = [40, 90, 150, 210, 260, 300, 350, 440]
    row(c, y, ["WIRE ID", "FROM", "TO", "AWG", "COLOR", "LENGTH", "WIRE SPEC", "SHIELD"], xs)
    for r in WIRES:
        y -= 11
        row(c, y, r, xs)
    y -= 26
    row(c, y, ["CONNECTOR LIST"], [40], 8)
    y -= 12
    xs2 = [40, 90, 210, 360, 400, 500]
    row(c, y, ["REF", "PART NUMBER", "DESCRIPTION", "QTY", "BACKSHELL", "CONTACTS"], xs2)
    for r in BOM:
        y -= 11
        row(c, y, r, xs2)
    row(c, 250, ["NOTES:"], [40], 8)
    row(c, 238, ["1. BUILD PER IPC/WHMA-A-620 CLASS 3."], [40])
    row(c, 227, ["2. MARK WIRES WITH WIRE ID AT BOTH ENDS."], [40])
    c.rect(W - 330, 24, 306, 90)
    yy = 100
    for ln in ["TITLE: CONTROL HARNESS", "DWG NO HX-100", "REV B", "SCALE NONE   SHEET 1 OF 1"]:
        row(c, yy, [ln], [W - 324])
        yy -= 11
    c.showPage()
    c.save()


def panel_csv():
    rows = [
        ("Ref", "Part number", "Description", "Qty", "Length (m)"),
        ("", "N4-2016", "ENCLOSURE, NEMA 4, 20 X 16 X 8", "1", ""),
        ("", "BP-2016", "BACK PANEL 20 X 16", "1", ""),
        ("", "DR-35", "DIN RAIL 35MM", "2", "0.5"),
        ("", "WD-23", "WIRE DUCT 2 X 3", "3", "0.5"),
        ("CB1", "CB-1P-10", "CIRCUIT BREAKER 1P 10A", "2", ""),
        ("TB1", "TB-4", "TERMINAL BLOCK 4MM", "20", ""),
        ("CR1", "RLY-24", "RELAY 24VDC DPDT", "4", ""),
        ("PS1", "PS-24-5", "POWER SUPPLY 24VDC 5A", "1", ""),
        ("PB1", "PB-22", "PUSH BUTTON 22MM GREEN", "2", ""),
        ("", "XYZ-1", "WIDGET", "1", ""),
    ]
    with open(HERE / "panel_bom.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)


def labels_csv():
    rows = [
        ("Item", "Type", "Size", "Text", "Color", "Holes", "Adhesive", "Qty", "IUID"),
        ("1", "Engraved phenolic", "1 x 3", "MAIN POWER", "WHITE/BLACK", "2", "", "2", ""),
        ("2", "Stainless steel", "2 x 4", "", "", "4", "", "1", "YES"),
        ("3", "Printed polyester", "50 x 25 mm", "CAUTION HOT", "", "0", "YES", "10", ""),
    ]
    with open(HERE / "labels.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)


if __name__ == "__main__":
    wires_csv()
    bom_csv()
    harness_xlsx()
    harness_pdf()
    panel_csv()
    labels_csv()
