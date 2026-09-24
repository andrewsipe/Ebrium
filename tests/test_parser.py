"""Flag names the help shows, and the old spellings that stay hidden."""

from __future__ import annotations

import argparse
import unittest

from ebrium.cli_parser import build_parser, finalize_args


def _subcommand(name: str) -> argparse.ArgumentParser:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "mode")
    return subparsers.choices[name]


def _by_option(parser: argparse.ArgumentParser) -> dict:
    found = {}
    for action in parser._actions:
        for option in action.option_strings:
            found[option] = action
    return found


class ParserTest(unittest.TestCase):
    def test_family_shows_new_flags_and_hides_old_spellings(self) -> None:
        options = _by_option(_subcommand("family"))
        self.assertIsNot(options["--no-cluster"].help, argparse.SUPPRESS)
        self.assertIs(options["--safe-max"].help, argparse.SUPPRESS)
        self.assertEqual(options["--safe-max"].dest, "no_cluster")
        self.assertIsNot(options["--merge"].help, argparse.SUPPRESS)
        self.assertIs(options["--combine"].help, argparse.SUPPRESS)
        self.assertEqual(options["--merge"].dest, "combine")
        self.assertEqual(options["--combine"].dest, "combine")

    def test_old_spellings_still_set_the_same_mode(self) -> None:
        args = build_parser().parse_args(
            ["family", "--safe-max", "-m", "A,B", "-c", "C,D", "-m", "E"]
        )
        finalize_args(args)
        self.assertEqual(args.grouping_mode, "conservative")
        self.assertEqual(args.combine, ["A,B", "C,D", "E"])

        visible = build_parser().parse_args(["family", "--no-cluster", "--merge", "A,B"])
        finalize_args(visible)
        self.assertEqual(visible.grouping_mode, "conservative")
        self.assertEqual(visible.combine, ["A,B"])

    def test_individual_rejects_family_only_flags(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            build_parser().parse_args(["individual", "--no-cluster"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()