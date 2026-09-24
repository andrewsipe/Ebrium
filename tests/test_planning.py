"""One real TTF through measure → plan → write.

The numbers are the default individual plan for this geometry (UPM 1000):

- cap 700, x-height 480, ascenders 750, descender -180, bbox -180..750
- typo ascender starts at cap + 25% UPM = 950 (the 750 ascenders do not override)
- centering descender is -(950 - 700) = -250, which is already deeper than -180
- x/cap ≈ 0.686 keeps the letter-height floor at 130% and adds a small
  x-height bump, so the span floor is 1315
- span 1200 is short by 115; the 60/40 split yields typo 1019 / -296
- Win follows the bbox, then is raised to cover typo: 1019 / 296
- line gaps are 0; USE_TYPO_METRICS is set; outlines and UPM stay put

A second font is the same outlines plus an fvar axis and sentinel MVAR/HVAR
bytes. family/individual/superfamily rewrite the default instance only.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.tables._f_v_a_r import Axis, table__f_v_a_r

from ebrium.application import apply_metrics
from ebrium.config import MetricsConfig
from ebrium.measurements import measure_fonts
from ebrium.planning import build_plans

MVAR_SENTINEL = b"EBRIUM-MVAR-FIXTURE"
HVAR_SENTINEL = b"EBRIUM-HVAR-FIXTURE"


def _box(x0: int, y0: int, x1: int, y1: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def _write_fixture(path: Path, *, variable: bool) -> None:
    glyph_order = [".notdef", "H", "x", "p", "b", "h"]
    glyphs = {
        ".notdef": _box(0, 0, 400, 700),
        "H": _box(50, 0, 550, 700),
        "x": _box(50, 0, 450, 480),
        "p": _box(50, -180, 450, 480),
        "b": _box(50, 0, 450, 750),
        "h": _box(50, 0, 450, 750),
    }
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({0x48: "H", 0x78: "x", 0x70: "p", 0x62: "b", 0x68: "h"})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 50) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200, lineGap=200)
    fb.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        sTypoLineGap=200,
        usWinAscent=800,
        usWinDescent=200,
        sxHeight=0,
        sCapHeight=0,
        fsSelection=0,
        version=4,
    )
    fb.setupNameTable({"familyName": "Fixture Sans", "styleName": "Regular"})
    fb.setupPost()
    fb.save(str(path))
    if not variable:
        return

    font = TTFont(str(path))
    fvar = table__f_v_a_r()
    axis = Axis()
    axis.axisTag = "wght"
    axis.minValue = 400
    axis.defaultValue = 400
    axis.maxValue = 700
    axis.axisNameID = 256
    fvar.axes = [axis]
    fvar.instances = []
    font["fvar"] = fvar
    font["name"].setName("Weight", 256, 3, 1, 0x409)
    for tag, payload in (("MVAR", MVAR_SENTINEL), ("HVAR", HVAR_SENTINEL)):
        raw = DefaultTable(tag)
        raw.data = payload
        font[tag] = raw
    font.save(str(path))
    font.close()


def _plan_and_apply(path: Path):
    measures = measure_fonts([str(path)])
    fm = measures[0]
    build_plans(
        {fm.family_name: measures},
        MetricsConfig(),
        grouping_mode="individual",
    )
    apply_metrics(str(path), fm, dry_run=False)
    return fm


class PlanningFixtureTest(unittest.TestCase):
    def test_individual_run_writes_default_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "FixtureSans-Regular.ttf"
            _write_fixture(path, variable=False)
            fm = _plan_and_apply(path)

            self.assertEqual(
                (fm.target_typo_asc, fm.target_typo_desc),
                (1019, -296),
            )
            self.assertEqual((fm.target_win_asc, fm.target_win_desc), (1019, 296))

            font = TTFont(str(path))
            os2 = font["OS/2"]
            hhea = font["hhea"]
            self.assertEqual(font["head"].unitsPerEm, 1000)
            self.assertEqual(font["glyf"]["H"].yMax, 700)
            self.assertEqual(
                (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap),
                (1019, -296, 0),
            )
            self.assertEqual((os2.usWinAscent, os2.usWinDescent), (1019, 296))
            self.assertEqual((hhea.ascent, hhea.descent, hhea.lineGap), (1019, -296, 0))
            self.assertTrue(os2.fsSelection & (1 << 7))
            self.assertEqual(os2.sCapHeight, 700)
            self.assertEqual(os2.sxHeight, 480)
            font.close()

    def test_variable_font_keeps_mvar_and_hvar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "FixtureSans-Variable.ttf"
            _write_fixture(path, variable=True)
            _plan_and_apply(path)

            font = TTFont(str(path), lazy=True)
            self.assertEqual(font.reader["MVAR"], MVAR_SENTINEL)
            self.assertEqual(font.reader["HVAR"], HVAR_SENTINEL)
            font.close()

            font = TTFont(str(path))
            os2 = font["OS/2"]
            axis = font["fvar"].axes[0]
            self.assertEqual(
                (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap),
                (1019, -296, 0),
            )
            self.assertEqual(font["glyf"]["H"].yMax, 700)
            self.assertEqual(
                (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue),
                ("wght", 400, 400, 700),
            )
            font.close()


if __name__ == "__main__":
    unittest.main()
