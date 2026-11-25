"""A run ends with one sentence, and a warning chip when a font could not be written."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from ebrium.application import process_all
from ebrium.models import FontMeasures


def _missing(tmp: str) -> FontMeasures:
    fm = FontMeasures(str(Path(tmp) / "gone.ttf"), 1000)
    fm.target_typo_asc, fm.target_typo_desc = 1000, -300
    fm.target_win_asc, fm.target_win_desc = 1000, 300
    return fm


class ClosingLineTest(unittest.TestCase):
    def _run(self, measures, dry_run=False):
        buf = io.StringIO()
        with patch("ebrium.application.console", Console(file=buf, width=100, force_terminal=False)):
            counts = process_all(measures, dry_run=dry_run)
        return counts, " ".join(buf.getvalue().split())

    def test_nothing_to_do_says_no_problems(self) -> None:
        counts, text = self._run([])
        self.assertEqual(counts, (0, 0, 0))
        self.assertIn("Updated 0, unchanged 0, no problems.", text)
        self.assertIn("SUCCESS", text)

    def test_unwritable_font_is_a_problem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            counts, text = self._run([_missing(tmp)])
        self.assertEqual(counts, (0, 0, 1))
        self.assertIn("1 problem.", text)
        self.assertIn("WARNING", text)

    def test_preview_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _counts, text = self._run([_missing(tmp)], dry_run=True)
        self.assertIn("Would update 0, unchanged 0, 1 problem.", text)
