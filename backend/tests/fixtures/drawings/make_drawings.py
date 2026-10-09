"""Generate the test drawing PDFs in this folder. Needs reportlab and Pillow (test-time only).

    python3 tests/fixtures/drawings/make_drawings.py

The PDFs are committed, so the tests do not need reportlab. All part numbers, CAGE codes and
company names below are made up.
"""
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
W, H = landscape(letter)


def frame(c):
    c.setLineWidth(1.5)
    c.rect(18, 18, W - 36, H - 36)
    c.setLineWidth(0.6)
    # part outline and a few holes so it looks like a drawing
    c.rect(90, 300, 300, 160)
    for x in (130, 350):
        for y in (330, 430):
            c.circle(x, y, 9)
    c.line(90, 280, 390, 280)


def text_lines(c, x, y, lines, size=7.5, lead=10):
    c.setFont("Helvetica", size)
    for ln in lines:
        c.drawString(x, y, ln)
        y -= lead
    return y


def title_block(c, rows):
    x0, y0 = W - 330, 24
    c.rect(x0, y0, 306, 120)
    text_lines(c, x0 + 6, y0 + 108, rows, size=7.5, lead=11)


def bracket():
    c = canvas.Canvas(str(HERE / "bracket_6061.pdf"), pagesize=landscape(letter))
    frame(c)
    text_lines(c, 100, 470, ["4X 1/4-20 UNC-2B THRU", "2X #10-32 UNF-2B .38 DEEP"])
    text_lines(c, 400, 380, ["Ø.250 ±.002", "3.000 ±.005"])
    text_lines(c, 30, 250, [
        "NOTES: UNLESS OTHERWISE SPECIFIED",
        "1. INTERPRET DRAWING PER ASME Y14.5-2018.",
        "2. REMOVE ALL BURRS AND BREAK SHARP EDGES .005-.015.",
        "3. ALL MACHINED SURFACES 125 Ra MAX.",
        "4. MATERIAL CERTIFICATIONS REQUIRED. MATERIAL SHALL BE TRACEABLE TO THE MILL HEAT LOT.",
        "5. FIRST ARTICLE INSPECTION REQUIRED PER AS9102.",
        "6. MARK PART NUMBER AND REV PER MIL-STD-130, .12 HIGH CHARACTERS.",
        "7. FINISH: ANODIZE PER MIL-PRF-8625, TYPE II, CLASS 2, BLACK.",
        "",
        "DISTRIBUTION STATEMENT D. Distribution authorized to the Department of Defense and U.S. DoD contractors only.",
        "WARNING - This document contains technical data whose export is restricted by the Arms Export Control Act",
        "(Title 22, U.S.C., Sec 2751, et seq.). Violations of these export laws are subject to severe criminal penalties.",
    ])
    text_lines(c, W - 330, 200, ["REV DESCRIPTION DATE APPROVED", "A INITIAL RELEASE 2024-03-01 JD", "B ADDED TAPPED HOLES 2025-01-15 JD"])
    title_block(c, [
        "UNLESS OTHERWISE SPECIFIED DIMENSIONS ARE IN INCHES",
        "TOLERANCES: .XX ±.01  .XXX ±.005  ANGLES ±0.5°",
        "MATERIAL: ALUMINUM ALLOY 6061-T6 PER ASTM B209",
        "TITLE: BRACKET, MOUNTING",
        "SIZE  CAGE CODE  DWG NO  REV",
        "C  1ABC5  12345-001  B",
        "SCALE 1:1  SHEET 1 OF 1",
    ])
    c.save()


def shaft():
    c = canvas.Canvas(str(HERE / "shaft_304.pdf"), pagesize=landscape(letter))
    frame(c)
    text_lines(c, 100, 470, ["Ø.7500 ±.0005", "3/8-24 UNF-2A", "M6x1.0-6H 2 PLACES", "2X HELICOIL INSERT MS21209F1-15 (1/4-20 UNC-2B STI)"])
    text_lines(c, 30, 250, [
        "NOTES:",
        "1. MATL: CRES 304 PER ASTM A276 COND A.",
        "2. HEAT TREAT: NONE. STRESS RELIEVE AFTER ROUGH MACHINING.",
        "3. PASSIVATE PER AMS 2700.",
        "4. SURFACE FINISH 32 Ra ON BEARING DIAMETERS.",
        "5. DO NOT PAINT.",
        "DISTRIBUTION STATEMENT A. Approved for public release; distribution is unlimited.",
    ])
    title_block(c, [
        "PART NO: 8842-17",
        "DWG NO. 8842",
        "CAGE CODE: 3XY77",
        "REV C",
        "TITLE: SHAFT, DRIVE",
        "TOLERANCES UNLESS NOTED .XXX ±.005",
    ])
    c.save()


def weldment():
    c = canvas.Canvas(str(HERE / "frame_weldment.pdf"), pagesize=landscape(letter))
    frame(c)
    text_lines(c, 30, 250, [
        "NOTES:",
        "1. DIMENSIONS ARE IN MILLIMETERS.",
        "2. GENERAL TOLERANCE ±0.1 UNLESS NOTED. ANGLES ±1°.",
        "3. MATERIAL: ASTM A36 STEEL PLATE.",
        "4. WELD PER AWS D1.1. ALL WELDS CONTINUOUS.",
        "5. ZINC PLATE PER ASTM B633 TYPE II SC 2, THEN PRIME AND PAINT PER MIL-DTL-53039 CARC GREEN 383.",
        "6. FIRST ARTICLE TEST (FAT) REQUIRED.",
        "DISTRIBUTION STATEMENT C. Distribution authorized to U.S. Government agencies and their contractors.",
        "EXPORT CONTROLLED: ITAR. This drawing contains technical data controlled under the ITAR.",
    ])
    title_block(c, ["TITLE: FRAME, WELDED", "DRAWING NUMBER: WF-2201", "REV 3", "CAGE 9ZZ01"])
    c.save()


def scanned():
    """A raster-only page: no text layer, like a scanned print."""
    img = Image.new("L", (1100, 850), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 1080, 830], outline=0, width=4)
    d.rectangle([150, 200, 650, 450], outline=0, width=3)
    for x in (200, 600):
        for y in (250, 400):
            d.ellipse([x - 15, y - 15, x + 15, y + 15], outline=0, width=2)
    d.rectangle([700, 680, 1070, 820], outline=0, width=2)
    img.save(HERE / "_scan.png")
    c = canvas.Canvas(str(HERE / "scanned.pdf"), pagesize=landscape(letter))
    c.drawImage(ImageReader(str(HERE / "_scan.png")), 0, 0, W, H)
    c.save()
    (HERE / "_scan.png").unlink()


def plate_holes():
    """Milled plate with hole callouts and dimension text but no stated overall size."""
    c = canvas.Canvas(str(HERE / "plate_holes.pdf"), pagesize=landscape(letter))
    frame(c)
    text_lines(c, 100, 500, ["4X Ø.201 THRU", "2X 1/4-20 UNC-2B .50 DEEP", "Ø.250 THRU 4 PLCS"])
    text_lines(c, 400, 420, ["6.000", "4.000 ±.010", ".750", "1.250 TYP"])
    text_lines(c, 30, 250, [
        "NOTES:",
        "1. MATERIAL: 6061-T6 ALUMINUM PLATE PER AMS-QQ-A-250/11.",
        "2. BREAK SHARP EDGES .010 MAX.",
        "3. CHEM FILM PER MIL-DTL-5541 TYPE II CLASS 3.",
        "DISTRIBUTION STATEMENT A. Approved for public release; distribution is unlimited.",
    ])
    title_block(c, [
        "UNLESS OTHERWISE SPECIFIED DIMENSIONS ARE IN INCHES",
        "TOLERANCES: .XX ±.01  .XXX ±.005",
        "TITLE: PLATE, ADAPTER",
        "PART NO: 77310-2",
        "REV A",
    ])
    c.save()


def sheet_cover():
    """Formed sheet metal cover with an explicit overall size, bend notes and a thickness."""
    c = canvas.Canvas(str(HERE / "sheet_cover.pdf"), pagesize=landscape(letter))
    frame(c)
    text_lines(c, 100, 500, ["BEND UP 90° R.06", "BEND UP 90° R.06", "6X Ø.191 THRU", "OVERALL SIZE: 8.00 X 3.00 X 1.50"])
    text_lines(c, 30, 250, [
        "NOTES:",
        "1. MATERIAL: .063 THK 5052-H32 ALUMINUM SHEET PER ASTM B209.",
        "2. INSIDE BEND RADIUS .06 UNLESS NOTED.",
        "3. POWDER COAT BLACK.",
        "DISTRIBUTION STATEMENT A. Approved for public release; distribution is unlimited.",
    ])
    title_block(c, ["TITLE: COVER, ELECTRONICS", "PART NO: 55120-1", "REV B", "TOLERANCES .XX ±.03"])
    c.save()


if __name__ == "__main__":
    bracket()
    shaft()
    weldment()
    scanned()
    plate_holes()
    sheet_cover()
    print("wrote", sorted(p.name for p in HERE.glob("*.pdf")))
