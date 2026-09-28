"""--match accepts the family name as written in the filename."""

from __future__ import annotations

import unittest

from ebrium.grouping import resolve_matched_names


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


if __name__ == "__main__":
    unittest.main()
