"""Generate the DXF fixtures for tests/test_flat.py (needs ezdxf).

    python3 tests/fixtures/flat/make_flat_fixtures.py

plate_holes_slot.dxf  inches. 6 x 4 plate (closed LWPOLYLINE), four 0.25 holes, one 0.5 hole, and an
                      obround slot drawn as 2 LINEs + 2 ARCs (0.75 between centers, 0.25 wide).
                      Also a TEXT, a DIMENSION and a line on layer NOTES (all ignored) and a bend line.
bulge_part.dxf        inches. A 4 x 2 rectangle with one end a half circle (LWPOLYLINE bulge 1), an
                      ELLIPSE cutout (0.5 x 0.25 semi-axes) and a block with a 0.2 circle inserted twice.
open_contour.dxf      inches. A closed 2 x 2 square, an open L of two lines, and the square's bottom edge
                      drawn a second time as a LINE (duplicate).
mm_parts.dxf          millimeters ($INSUNITS 4). Two identical 100 x 50 plates with a 10 mm hole, and a
                      separate 30 mm disk.
"""
from pathlib import Path

import ezdxf

HERE = Path(__file__).parent


def plate():
    doc = ezdxf.new(units=1)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (6, 0), (6, 4), (0, 4)], close=True)
    for x, y in ((0.5, 0.5), (5.5, 0.5), (5.5, 3.5), (0.5, 3.5)):
        msp.add_circle((x, y), 0.125)
    msp.add_circle((3, 2), 0.25)
    # obround slot centered at (3, 3.2), centers 0.75 apart, width 0.25
    cx1, cx2, cy, r = 2.625, 3.375, 3.2, 0.125
    msp.add_line((cx1, cy - r), (cx2, cy - r))
    msp.add_arc((cx2, cy), r, -90, 90)
    msp.add_line((cx2, cy + r), (cx1, cy + r))
    msp.add_arc((cx1, cy), r, 90, 270)
    msp.add_text("PART 1", dxfattribs={"height": 0.2}).set_placement((0.2, 4.3))
    dim = msp.add_linear_dim(base=(0, -0.5), p1=(0, 0), p2=(6, 0), dxfattribs={"layer": "DIMS"})
    dim.render()
    msp.add_line((0, -1), (6, -1), dxfattribs={"layer": "NOTES"})
    msp.add_line((1, 0), (1, 4), dxfattribs={"layer": "BEND"})
    doc.saveas(HERE / "plate_holes_slot.dxf")


def bulge():
    doc = ezdxf.new(units=1)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0, 0), (4, 0, 1), (4, 2, 0), (0, 2, 0)], format="xyb", close=True)
    msp.add_ellipse((1.5, 1.0), major_axis=(0.5, 0, 0), ratio=0.5)
    blk = doc.blocks.new("HOLE")
    blk.add_circle((0, 0), 0.1)
    msp.add_blockref("HOLE", (3, 0.5))
    msp.add_blockref("HOLE", (3, 1.5))
    doc.saveas(HERE / "bulge_part.dxf")


def open_contour():
    doc = ezdxf.new(units=1)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True)
    msp.add_line((0, 0), (2, 0))  # duplicate of the bottom edge
    msp.add_line((4, 0), (6, 0))
    msp.add_line((6, 0), (6, 2))  # open L
    doc.saveas(HERE / "open_contour.dxf")


def mm_parts():
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for ox in (0, 120):
        msp.add_lwpolyline([(ox, 0), (ox + 100, 0), (ox + 100, 50), (ox, 50)], close=True)
        msp.add_circle((ox + 50, 25), 5)
    msp.add_circle((300, 25), 15)
    doc.saveas(HERE / "mm_parts.dxf")


if __name__ == "__main__":
    plate()
    bulge()
    open_contour()
    mm_parts()
    print("wrote DXF fixtures")
