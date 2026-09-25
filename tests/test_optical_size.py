"""Optical-size names split a peer set; one size stays one box."""

from __future__ import annotations

import unittest

from ebrium.models import FontMeasures
from ebrium.optical_size import (
    expand_optical_size_groups,
    optical_size_label,
    split_optical_size_groups,
)


def _fm(path: str, family: str) -> FontMeasures:
    fm = FontMeasures(path, 1000)
    fm.family_name = family
    return fm


class OpticalSizeTest(unittest.TestCase):
    def test_mixed_sizes_unpin(self) -> None:
        group = [
            _fm("/tmp/SourceSerif4-Regular.otf", "Source Serif 4"),
            _fm("/tmp/SourceSerif4Caption-Regular.otf", "Source Serif 4 Caption"),
            _fm("/tmp/SourceSerif4Display-Regular.otf", "Source Serif 4 Display"),
            _fm("/tmp/SourceSerif4Subhead-Regular.otf", "Source Serif 4 Subhead"),
            _fm(
                "/tmp/SourceSerif4SmallText-Regular.otf",
                "Source Serif 4 Small Text",
            ),
        ]
        buckets = dict(split_optical_size_groups(group))
        self.assertEqual(
            set(buckets),
            {"Text", "Caption", "Display", "Subhead", "Small Text"},
        )
        self.assertEqual(len(buckets["Text"]), 1)
        self.assertEqual(len(buckets["Caption"]), 1)

    def test_single_family_stays_pinned(self) -> None:
        group = [
            _fm("/tmp/Rig-BoldFace.ttf", "Rig"),
            _fm("/tmp/Rig-LightShadow.ttf", "Rig"),
        ]
        self.assertEqual(split_optical_size_groups(group), [("default", group)])

    def test_display_alone_is_not_a_split(self) -> None:
        group = [
            _fm("/tmp/Poster-Regular.otf", "Poster Display"),
            _fm("/tmp/Poster-Bold.otf", "Poster Display"),
        ]
        self.assertEqual(optical_size_label(group[0]), "Display")
        self.assertEqual(split_optical_size_groups(group), [("default", group)])

    def test_small_text_is_not_also_text(self) -> None:
        fm = _fm("/tmp/SourceSerif4SmallText-Regular.otf", "Source Serif 4 Small Text")
        self.assertEqual(optical_size_label(fm), "Small Text")

    def test_expand_names_match_the_planned_boxes(self) -> None:
        group = [
            _fm("/tmp/SourceSerif4-Regular.otf", "Source Serif 4"),
            _fm("/tmp/SourceSerif4Caption-Regular.otf", "Source Serif 4 Caption"),
        ]
        expanded = expand_optical_size_groups({"Source Serif 4": group})
        self.assertEqual(set(expanded), {"Source Serif 4 · Text", "Source Serif 4 · Caption"})
        self.assertEqual(len(expanded["Source Serif 4 · Text"]), 1)
        self.assertEqual(len(expanded["Source Serif 4 · Caption"]), 1)

    def test_matched_family_names_stay_one_box(self) -> None:
        group = [
            _fm("/tmp/FamilyA-Caption.otf", "Family A"),
            _fm("/tmp/FamilyB-Display.otf", "Family B"),
        ]
        expanded = expand_optical_size_groups(
            {"Family A": group}, [["Family A", "Family B"]]
        )
        self.assertEqual(list(expanded), ["Family A"])
        self.assertEqual(len(expanded["Family A"]), 2)


if __name__ == "__main__":
    unittest.main()
