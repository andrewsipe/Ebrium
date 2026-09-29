"""A real change is reported, and a stopped measurement keeps what finished."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fontTools.ttLib import TTFont

from ebrium.application import ApplyStatus, apply_metrics
from ebrium.config import MetricsConfig
from ebrium.measurements import MeasurementInterrupted, _read_ttfont, measure_fonts
from ebrium.models import FontMeasures
from ebrium.planning import analyze_family_impact, build_plans
from ebrium.validation import report_changes
from tests.test_planning import _write_fixture


def _bare(name: str, cap: int) -> FontMeasures:
    fm = FontMeasures(f"/tmp/{name}.ttf", 1000)
    fm.family_name = "Mixed"
    fm.cap_height = cap
    fm.cap_optical = cap
    fm.x_height = 480
    fm.descender_min = -200
    fm.max_y = cap + 100
    fm.min_y = -200
    return fm


class FamilyCloseTest(unittest.TestCase):
    def test_unlike_styles_still_finish_the_family(self) -> None:
        group = [_bare("A", 400), _bare("B", 900)]
        plans, _cache = build_plans(
            {"Mixed": group}, MetricsConfig(), emit_review_report=False
        )
        self.assertIn("Mixed", plans)
        self.assertEqual([fm.target_line_gap for fm in group], [0, 0])
        self.assertEqual(group[0].target_typo_asc, group[1].target_typo_asc)
        self.assertEqual(group[0].target_typo_desc, group[1].target_typo_desc)
        for fm in group:
            self.assertGreaterEqual(fm.target_win_asc, fm.target_typo_asc)
            self.assertGreaterEqual(fm.target_win_desc, abs(fm.target_typo_desc))

    def test_a_script_does_not_deepen_the_shared_box(self) -> None:
        text_a = _bare("TextA", 700)
        text_b = _bare("TextB", 1100)
        script = _bare("Script", 400)
        script.is_script = True
        script.descender_min = -900
        script.min_y = -900
        group = [text_a, text_b, script]
        _plans, cache = build_plans(
            {"Mixed": group}, MetricsConfig(), emit_review_report=False
        )
        self.assertEqual(text_a.target_typo_asc, text_b.target_typo_asc)
        self.assertEqual(text_a.target_typo_desc, text_b.target_typo_desc)
        self.assertEqual(script.target_typo_desc, text_a.target_typo_desc)
        self.assertGreater(text_a.target_typo_desc, -900)
        self.assertCountEqual(cache["Mixed"]["main_cluster"], [text_a.path, text_b.path])
        self.assertIn(script.path, cache["Mixed"]["script"])
        self.assertTrue(cache["Mixed"]["no_core"])
        first_asc = text_a.target_typo_asc
        build_plans(
            {"Mixed": group},
            MetricsConfig(),
            cached_clusters=cache,
            emit_review_report=False,
        )
        self.assertEqual(text_a.target_typo_asc, first_asc)
        self.assertEqual(text_b.target_typo_asc, first_asc)
        self.assertEqual(script.target_typo_desc, text_a.target_typo_desc)

    def test_span_zero_keeps_the_file_span_and_still_sets_the_gap(self) -> None:
        group = [_bare("A", 400), _bare("B", 900)]
        build_plans(
            {"Mixed": group},
            MetricsConfig(target_span=0, line_gap=0.05),
            emit_review_report=False,
        )
        for fm in group:
            self.assertIsNone(fm.target_typo_asc)
            self.assertIsNone(fm.target_typo_desc)
            self.assertEqual(fm.target_line_gap, 50)


class ReportGateTest(unittest.TestCase):
    def test_a_small_percent_still_counts_when_a_font_changes(self) -> None:
        fm = FontMeasures("/tmp/A.ttf", 1000)
        fm.family_name = "Family"
        fm.target_typo_asc = 1000
        fm.target_typo_desc = -300
        args = SimpleNamespace(verbose=0)
        with patch(
            "ebrium.validation.analyze_family_impact",
            return_value=(0.05, 0.0, 20, True),
        ):
            needed = report_changes(
                {"Family": [fm]}, {"Family": (0.0, 0.0, 0.0)}, args, []
            )
        self.assertTrue(needed)

    def test_an_unchanged_family_is_quiet(self) -> None:
        fm = FontMeasures("/tmp/A.ttf", 1000)
        fm.family_name = "Family"
        fm.target_typo_asc = 1000
        fm.target_typo_desc = -300
        args = SimpleNamespace(verbose=0)
        with patch(
            "ebrium.validation.analyze_family_impact",
            return_value=(0.0, 0.0, 20, False),
        ):
            needed = report_changes(
                {"Family": [fm]}, {"Family": (0.0, 0.0, 0.0)}, args, []
            )
        self.assertFalse(needed)


class ZeroMetricTest(unittest.TestCase):
    def test_a_planned_zero_counts_as_a_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "A.ttf"
            _write_fixture(path, variable=False)
            fm = FontMeasures(str(path), 1000)
            fm.target_typo_asc = 800
            fm.target_typo_desc = -200
            fm.target_win_asc = 800
            fm.target_win_desc = 0
            fm.target_line_gap = 200
            _largest, _span, count, changed = analyze_family_impact([fm])
            self.assertEqual(count, 1)
            self.assertTrue(changed)

    def test_a_glyph_height_disagreement_counts_on_its_own(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "A.ttf"
            _write_fixture(path, variable=False)
            font = TTFont(str(path))
            font["OS/2"].sxHeight = 111
            font["OS/2"].sCapHeight = 222
            font.save(str(path))
            font.close()

            fm = FontMeasures(str(path), 1000)
            fm.target_typo_asc = 800
            fm.target_typo_desc = -200
            fm.target_win_asc = 800
            fm.target_win_desc = 200
            fm.target_line_gap = 200
            fm.x_height = 480
            fm.cap_height = 700
            _largest, _span, _count, changed = analyze_family_impact([fm])
            self.assertTrue(changed)

            fm.x_height = 111
            fm.cap_height = 222
            _largest, _span, _count, changed = analyze_family_impact([fm])
            self.assertFalse(changed)

            font = TTFont(str(path))
            font["OS/2"].version = 1
            font.save(str(path))
            font.close()
            fm.x_height = 480
            fm.cap_height = 700
            _largest, _span, _count, changed = analyze_family_impact([fm])
            self.assertFalse(changed)


class InterruptedMeasureTest(unittest.TestCase):
    def test_a_stopped_run_keeps_fonts_already_measured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "A.ttf"
            second = Path(tmp) / "B.ttf"
            _write_fixture(first, variable=False)
            _write_fixture(second, variable=False)
            real = _read_ttfont
            seen = {"n": 0}

            def stop_on_second(path):
                seen["n"] += 1
                if seen["n"] > 1:
                    raise KeyboardInterrupt
                return real(path)

            with patch("ebrium.measurements._read_ttfont", stop_on_second):
                with self.assertRaises(MeasurementInterrupted) as caught:
                    measure_fonts([str(first), str(second)])
            self.assertEqual(len(caught.exception.measures), 1)
            self.assertEqual(caught.exception.measures[0].path, str(first))


class ApplyStatusTest(unittest.TestCase):
    def test_a_name_containing_error_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "error-note.ttf"
            _write_fixture(path, variable=False)
            fm = FontMeasures(str(path), 1000)
            status, _msg = apply_metrics(str(path), fm, dry_run=True)
            self.assertIs(status, ApplyStatus.UNCHANGED)

            missing = FontMeasures(str(Path(tmp) / "missing-error.ttf"), 1000)
            missing.target_typo_asc = 1000
            missing.target_typo_desc = -300
            missing.target_win_asc = 1000
            missing.target_win_desc = 300
            status, _msg = apply_metrics(missing.path, missing, dry_run=True)
            self.assertIs(status, ApplyStatus.ERROR)

    def test_only_use_typo_metrics_still_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ready.ttf"
            _write_fixture(path, variable=False)
            fm = FontMeasures(str(path), 1000)
            fm.target_typo_asc = 800
            fm.target_typo_desc = -200
            fm.target_win_asc = 800
            fm.target_win_desc = 200
            fm.target_line_gap = 200
            status, _msg = apply_metrics(str(path), fm, dry_run=False)
            self.assertIs(status, ApplyStatus.UPDATED)
            font = TTFont(str(path))
            self.assertTrue(font["OS/2"].fsSelection & (1 << 7))
            font.close()

    def test_an_old_os2_is_left_alone_and_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.ttf"
            _write_fixture(path, variable=False)
            font = TTFont(str(path))
            font["OS/2"].version = 3
            font.save(str(path))
            font.close()
            fm = FontMeasures(str(path), 1000)
            fm.target_typo_asc = 1000
            fm.target_typo_desc = -300
            fm.target_win_asc = 1000
            fm.target_win_desc = 300
            fm.target_line_gap = 0
            status, msg = apply_metrics(str(path), fm, dry_run=False)
            self.assertIs(status, ApplyStatus.UPDATED)
            self.assertIn("Use Typo Metrics is not set", msg)
            font = TTFont(str(path))
            os2 = font["OS/2"]
            self.assertEqual(os2.version, 3)
            self.assertFalse(os2.fsSelection & (1 << 7))
            font.close()

    def test_ttx_and_symlink_keep_the_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ready.ttf"
            _write_fixture(path, variable=False)
            path.chmod(0o640)
            link = Path(tmp) / "link.ttf"
            link.symlink_to(path)
            ttx = Path(tmp) / "ready.ttx"
            source = TTFont(str(path))
            source.saveXML(str(ttx))
            source.close()

            for target in (link, ttx):
                fm = FontMeasures(str(target), 1000)
                fm.target_typo_asc = 1000
                fm.target_typo_desc = -300
                fm.target_win_asc = 1000
                fm.target_win_desc = 300
                fm.target_line_gap = 0
                fm.x_height = 480
                fm.cap_height = 700
                status, _msg = apply_metrics(str(target), fm, dry_run=False)
                self.assertIs(status, ApplyStatus.UPDATED, target.name)
                self.assertFalse(Path(str(target) + ".ebrium-tmp").exists())
                self.assertFalse((path.parent / (path.name + ".ebrium-tmp")).exists())

            self.assertTrue(link.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            written = TTFont(str(path))
            self.assertEqual(written["OS/2"].sTypoAscender, 1000)
            written.close()
            xml = ttx.read_text()
            self.assertIn("sTypoAscender", xml)
            self.assertIn('value="1000"', xml)


if __name__ == "__main__":
    unittest.main()
