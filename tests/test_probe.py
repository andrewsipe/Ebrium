"""Probe classifies a flat Win box against axis-pole ink."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._f_v_a_r import Axis, table__f_v_a_r
from fontTools.ttLib.tables._g_v_a_r import table__g_v_a_r

from types import SimpleNamespace

from ebrium.probe_report import collect_groups, present
from ebrium.variation_probe import (
    CLIP_TAGS,
    _moving,
    metrics_brief,
    report_destination,
    survey_font,
)


def _box(x0: int, y0: int, x1: int, y1: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def _write_variable(path: Path, *, win_ascent: int, raise_top: int) -> None:
    order = [".notdef", "H"]
    glyphs = {".notdef": _box(0, 0, 100, 100), "H": _box(50, 0, 550, 700)}
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x48: "H"})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 50) for name in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2(
        usWinAscent=win_ascent,
        usWinDescent=200,
        sTypoAscender=800,
        sTypoDescender=-200,
        sTypoLineGap=0,
        version=4,
    )
    fb.setupNameTable({"familyName": "Probe", "styleName": "Regular"})
    fb.setupPost()
    fb.save(str(path))

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
    if raise_top:
        coords, _, _ = font["glyf"]["H"].getCoordinates(font["glyf"])
        deltas = [(0, raise_top) if y >= 700 else (0, 0) for _x, y in coords]
        deltas.extend([(0, 0)] * 4)
        gvar = table__g_v_a_r()
        gvar.variations = {"H": [TupleVariation({"wght": (0, 1, 1)}, deltas)]}
        font["gvar"] = gvar
    font.save(str(path))
    font.close()


class ProbeSurveyTest(unittest.TestCase):
    def test_pole_past_default_ink_is_variable_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overflow.ttf"
            _write_variable(path, win_ascent=700, raise_top=200)
            survey = survey_font(TTFont(str(path)))
        self.assertEqual(survey.clipping, "variable-overflow")
        self.assertEqual(survey.line_box, "flat")
        self.assertIn("heaviest weight", survey.overflow_lines[0])
        self.assertIn("200 units stick out", survey.overflow_lines[0])
        self.assertIn("pass that box by 20% of the em", metrics_brief(survey))
        self.assertIn("Em 1000", metrics_brief(survey))

    def test_pole_inside_win_is_not_an_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "covered.ttf"
            _write_variable(path, win_ascent=900, raise_top=200)
            survey = survey_font(TTFont(str(path)))
        self.assertEqual(survey.clipping, "no-variable-overflow")
        self.assertEqual(survey.clipping_text, "no variable overflow")
        self.assertEqual(survey.overflow_lines, [])
        self.assertIn("stay inside the clipping box", metrics_brief(survey))

    def test_default_ink_past_win_without_a_taller_pole(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "default-only.ttf"
            _write_variable(path, win_ascent=500, raise_top=0)
            survey = survey_font(TTFont(str(path)))
        self.assertEqual(survey.clipping, "no-variable-overflow")
        self.assertIn("default ink exceeds Win by 200 above", survey.clipping_text)

    def test_quiet_run_writes_a_row_per_font(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "overflow.ttf"
            report_path = Path(tmp) / "probe.tsv"
            _write_variable(font_path, win_ascent=700, raise_top=200)
            present(
                collect_groups([str(font_path)], SimpleNamespace(
                    grouping_mode="family", combine=None, ignore_term=None, exclude=None, verbose=0,
                )),
                quiet=True,
                output=str(report_path),
                source_paths=[str(font_path)],
            )
            with report_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["upm"], "1000")
        self.assertEqual(rows[0]["driver"], "yes")
        self.assertIn("hhea_gap", rows[0])
        self.assertIn("20% of the em", rows[0]["sliders"])

    def test_a_pass_is_left_out_of_the_baseline_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "covered.ttf"
            report_path = Path(tmp) / "probe.tsv"
            _write_variable(font_path, win_ascent=900, raise_top=200)
            present(
                collect_groups([str(font_path)], SimpleNamespace(
                    grouping_mode="family", combine=None, ignore_term=None, exclude=None, verbose=0,
                )),
                quiet=True,
                output=str(report_path),
                source_paths=[str(font_path)],
            )
            with report_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(len(rows), 1)
        self.assertIn("stay inside the clipping box", rows[0]["sliders"])

    def test_relative_report_is_saved_in_the_probed_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_dir = Path(tmp) / "collection"
            font_dir.mkdir()
            font_path = font_dir / "overflow.ttf"
            _write_variable(font_path, win_ascent=700, raise_top=200)
            placed = Path(report_destination("probe.tsv", [str(font_dir)]))
            self.assertEqual(placed.resolve(), (font_dir / "probe.tsv").resolve())
            present(
                collect_groups([str(font_path)], SimpleNamespace(
                    grouping_mode="family", combine=None, ignore_term=None, exclude=None, verbose=0,
                )),
                quiet=True,
                output="probe.tsv",
                source_paths=[str(font_dir)],
            )
            self.assertTrue(placed.is_file())

    def test_family_rejects_report_flag(self) -> None:
        from ebrium.cli_parser import build_parser

        with self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["family", "--report"])
        self.assertEqual(raised.exception.code, 2)

    def test_clipping_tag_range_counts_as_already_varied(self) -> None:
        moving = _moving({"hcla": (0, 40), "hcld": (0, 0)}, CLIP_TAGS)
        self.assertEqual(moving, [("hcla", 0, 40)])
        self.assertEqual(_moving({"hasc": (0, 0)}, ("hasc",)), [])


if __name__ == "__main__":
    unittest.main()
