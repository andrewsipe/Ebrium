"""--match joins names with a comma, and keys without one."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from ebrium.grouping import group_families, parse_matched_groups, resolve_matched_names
from ebrium.models import FontMeasures


class MatchNamesTest(unittest.TestCase):
    def test_filename_form_matches_a_spaced_family_name(self) -> None:
        families = ["Family", "Family Short", "Family Tall"]
        resolved, missed = resolve_matched_names(
            [["Family", "FamilyShort", "FamilyTall"]], families
        )
        self.assertEqual(missed, [])
        self.assertEqual(
            resolved, [["Family", "Family Short", "Family Tall"]]
        )

    def test_an_unknown_name_is_reported(self) -> None:
        resolved, missed = resolve_matched_names(
            [["Family", "NotAFamily"]], ["Family"]
        )
        self.assertEqual(missed, ["NotAFamily"])
        self.assertEqual(resolved, [["Family"]])


def _font(path: str, family: str) -> FontMeasures:
    fm = FontMeasures(path, 1000)
    fm.family_name = family
    return fm


class MatchKeyTest(unittest.TestCase):
    def _groups(self, *flags: str):
        fonts = [
            _font("/fonts/Pancake-Short.ttf", "Pancake"),
            _font("/fonts/Pancake-ExtraTall.ttf", "Pancake"),
            _font("/fonts/Pancake-Variable.ttf", "Pancake Variable"),
            _font("/fonts/AboveTheBeyondSerif.ttf", "Above The Beyond Serif"),
            _font("/fonts/Miniserif-Regular.ttf", "Miniserif"),
            _font("/fonts/FamilyA.ttf", "Family A"),
            _font("/fonts/FamilyB.ttf", "Family B"),
        ]
        args = SimpleNamespace(combine=list(flags), grouping_mode="family")
        return group_families(args, fonts, parse_matched_groups(args))

    def test_a_key_collects_a_shared_root(self) -> None:
        groups = self._groups("Pancake")
        self.assertEqual(len(groups["Pancake"]), 3)
        self.assertNotIn("Pancake Variable", groups)

    def test_a_phrase_does_not_include_a_longer_compound(self) -> None:
        groups = self._groups("Pancake Short")
        names = [font.path for font in groups["Pancake Short"]]
        self.assertEqual(names, ["/fonts/Pancake-Short.ttf"])
        self.assertEqual(
            [font.path for font in groups["Pancake"]],
            ["/fonts/Pancake-ExtraTall.ttf"],
        )
        self.assertIn("Pancake Variable", groups)

    def test_a_word_matches_case_and_skips_a_longer_word(self) -> None:
        groups = self._groups("serif")
        matched = {font.family_name for font in groups["serif"]}
        self.assertEqual(matched, {"Above The Beyond Serif"})
        self.assertIn("Miniserif", groups)

    def test_the_first_flag_keeps_the_file(self) -> None:
        groups = self._groups("Pancake", "Variable")
        variable = "/fonts/Pancake-Variable.ttf"
        self.assertIn(variable, {font.path for font in groups["Pancake"]})
        self.assertNotIn("Variable", groups)

    def test_a_word_matches_inside_a_compound(self) -> None:
        groups = self._groups("Tall")
        paths = {font.path for font in groups["Tall"]}
        self.assertEqual(paths, {"/fonts/Pancake-ExtraTall.ttf"})

    def test_a_comma_still_joins_unrelated_names(self) -> None:
        groups = self._groups("Family A,Family B")
        joined = {font.family_name for font in groups["Family A"]}
        self.assertEqual(joined, {"Family A", "Family B"})


if __name__ == "__main__":
    unittest.main()
