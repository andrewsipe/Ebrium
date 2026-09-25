"""Family grouping is the only path. --no-cluster is the outline-extremes plan."""

from __future__ import annotations

import unittest

from ebrium.cli_parser import build_parser, finalize_args


class ParserTest(unittest.TestCase):
    def test_default_is_family(self) -> None:
        args = build_parser().parse_args(["fonts/"])
        finalize_args(args)
        self.assertEqual(args.grouping_mode, "family")
        self.assertEqual(args.plan_mode, "family")

    def test_no_cluster_uses_outline_extremes(self) -> None:
        args = build_parser().parse_args(["--no-cluster", "fonts/"])
        finalize_args(args)
        self.assertEqual(args.grouping_mode, "conservative")
        self.assertEqual(args.plan_mode, "conservative")

    def test_span_and_line_gap_defaults(self) -> None:
        args = build_parser().parse_args(["fonts/"])
        self.assertEqual(args.span, 130)
        self.assertEqual(args.line_gap, 0)
        custom = build_parser().parse_args(["--span", "120", "--line-gap", "5"])
        self.assertEqual(custom.span, 120)
        self.assertEqual(custom.line_gap, 5)
        options = {
            opt
            for action in build_parser()._actions
            for opt in action.option_strings
        }
        self.assertNotIn("--scope", options)
        self.assertIn("--no-cluster", options)
        self.assertIn("--match", options)
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--scope", "superfamily"])

    def test_match_pairs_family_names(self) -> None:
        args = build_parser().parse_args(["--match", "Family A,Family B", "fonts/"])
        finalize_args(args)
        self.assertEqual(args.combine, ["Family A,Family B"])
        self.assertEqual(args.grouping_mode, "family")
        hidden = build_parser().parse_args(["--merge", "Family A,Family B"])
        self.assertEqual(hidden.combine, ["Family A,Family B"])
        help_text = build_parser().format_help()
        self.assertIn("--match", help_text)
        self.assertNotIn("--merge", help_text)


if __name__ == "__main__":
    unittest.main()
