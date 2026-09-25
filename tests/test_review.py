"""Layered sets share one box. Review notes don't change the plan."""

from __future__ import annotations

import unittest

from ebrium.config import MetricsConfig
from ebrium.models import FontMeasures
from ebrium.review import is_layered_set, review_notes, stamp_layered_metrics


def _fm(
    name: str,
    *,
    cap: int = 700,
    x: int = 480,
    typo_asc: int = 1000,
    typo_desc: int = -300,
    ymax: int = 1100,
    ymin: int = -250,
    color: bool = False,
) -> FontMeasures:
    fm = FontMeasures(f"/tmp/{name}.ttf", 1000)
    fm.family_name = "Stack"
    fm.cap_optical = cap
    fm.cap_height = cap
    fm.x_height = x
    fm.accented_cap_max = cap + 80
    fm.max_y = ymax
    fm.min_y = ymin
    fm.target_typo_asc = typo_asc
    fm.target_typo_desc = typo_desc
    fm.target_win_asc = ymax
    fm.target_win_desc = abs(ymin)
    fm.is_color_font = color
    return fm


class ReviewTest(unittest.TestCase):
    def test_color_files_share_one_box(self) -> None:
        base = _fm("Stack-Base", color=True, typo_asc=900, ymax=1000, ymin=-200)
        shade = _fm("Stack-Shade", color=True, typo_asc=1100, ymax=1400, ymin=-500)
        self.assertTrue(stamp_layered_metrics([base, shade], MetricsConfig()))
        self.assertEqual(base.target_typo_asc, shade.target_typo_asc)
        self.assertEqual(base.target_typo_desc, shade.target_typo_desc)
        self.assertEqual(base.target_win_asc, shade.target_win_asc)
        self.assertGreaterEqual(base.target_win_asc, 1400)
        self.assertGreaterEqual(base.target_win_desc, 500)

    def test_named_layers_count_without_color_tables(self) -> None:
        group = [_fm("Font-Layer1"), _fm("Font-Layer2")]
        self.assertTrue(is_layered_set(group))

    def test_one_color_file_is_not_a_stack(self) -> None:
        group = [_fm("Text-Regular"), _fm("Text-Color", color=True)]
        self.assertFalse(is_layered_set(group))

    def test_spread_and_low_x_are_notes_only(self) -> None:
        regular = _fm("Text-Regular", cap=700, x=400)
        bold = _fm("Text-Bold", cap=760, x=430)
        notes = review_notes([regular, bold])
        self.assertTrue(any(note.startswith("Cross-weight spread: cap height") for note in notes))
        self.assertTrue(any(note.startswith("x-height/cap-height") for note in notes))

    def test_quiet_when_inside_the_band(self) -> None:
        regular = _fm("Text-Regular", cap=700, x=480)
        bold = _fm("Text-Bold", cap=706, x=484)
        self.assertEqual(review_notes([regular, bold]), [])


if __name__ == "__main__":
    unittest.main()
