"""The write path knows about variable fonts: the Win box covers every axis pole, and a line box the design already varies is left alone."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fontTools.ttLib import TTFont

from ebrium.variation_probe import survey_font
from tests.test_probe import _write_variable

ROOT = Path(__file__).resolve().parents[1]


def _run(path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ebrium", "-y", str(path.parent)],
        capture_output=True, text=True, cwd=ROOT, timeout=300, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stdout[-500:] + result.stderr[-500:]


class PoleAwareWriteTest(unittest.TestCase):
    def test_the_win_box_still_covers_a_taller_pole_after_the_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Probe-Variable.ttf"
            _write_variable(path, win_ascent=1010, raise_top=310)  # the heavy pole reaches 1010, just above the 1000 the plan centres on
            _run(path)
            after = TTFont(str(path))
            self.assertGreaterEqual(after["OS/2"].usWinAscent, 1010)
            self.assertEqual(survey_font(after).clipping, "no-variable-overflow")

    def test_a_font_that_already_clips_at_a_pole_is_raised_to_cover_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Probe-Variable.ttf"
            _write_variable(path, win_ascent=700, raise_top=310)  # overflows before Ebrium touches it
            _run(path)
            self.assertEqual(survey_font(TTFont(str(path))).clipping, "no-variable-overflow")

    def test_a_static_font_is_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Probe-Regular.ttf"
            _write_variable(path, win_ascent=900, raise_top=0)
            font = TTFont(str(path))
            for tag in ("fvar", "gvar"):
                if tag in font:
                    del font[tag]
            font.save(str(path))
            _run(path)
            self.assertNotIn("fvar", TTFont(str(path)))

    def test_a_line_box_the_design_already_varies_is_left_alone(self) -> None:
        from ebrium import application, variation_probe
        from ebrium.models import FontMeasures

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Probe-Variable.ttf"
            _write_variable(path, win_ascent=900, raise_top=0)
            before = TTFont(str(path))
            old = (before["OS/2"].sTypoAscender, before["OS/2"].sTypoDescender, before["hhea"].ascent, before["hhea"].descent)
            fm = FontMeasures(str(path), 1000)
            fm.target_typo_asc, fm.target_typo_desc, fm.target_win_asc, fm.target_win_desc = 1100, -300, 1100, 300
            fm.line_box_moves = True
            application.apply_metrics(str(path), fm, dry_run=False)
            after = TTFont(str(path))
            self.assertEqual(old, (after["OS/2"].sTypoAscender, after["OS/2"].sTypoDescender, after["hhea"].ascent, after["hhea"].descent))
            self.assertGreaterEqual(after["OS/2"].usWinAscent, 900)  # clipping safety still applies


if __name__ == "__main__":
    unittest.main()
