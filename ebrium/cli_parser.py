"""ebrium argument parser (drop-in for the body of cli.parse_args()).

Same flags, dests and defaults as before; only the presentation changed:
  * one-line help strings; interaction rules moved to a "notes" footer
  * grouping mode is a real mutually exclusive group containing --safe-max
    (replaces the mode._group_actions.append(...) workaround)
  * --top-margin / --use-ttx / --no-auto-adjust moved into sensible groups
  * hand-written usage line (the generated one wrapped to 7 lines)
  * prog is pinned so `python -m ebrium` doesn't print "__main__.py"
  * --version added; -h/--version/-v grouped at the bottom

In cli.py:

    from .cli_parser import build_parser

    def parse_args() -> argparse.Namespace:
        return build_parser().parse_args()
"""

from __future__ import annotations

import argparse

from FontCore.core_cli_help import (
    RichHelp,
    docs_section,
    examples_section,
    exit_status_section,
    line_section,
    notes_section,
    safety_panel,
)
from FontCore.core_console_styles import get_console

from . import __version__

DESCRIPTION = (
    "Normalize vertical metrics across a font family without changing "
    "unitsPerEm or glyph outlines."
)

PANEL = safety_panel(
    message=(
        "Fonts are modified in place: no backup and no output directory. "
        "You are asked to confirm before anything is written."
    ),
    rows=[
        ("Preview only", "-n, --dry-run"),
        ("Family vs per-font analysis", "--report  (implies -n)"),
    ],
)

EXAMPLES = [
    ("ebrium fonts/ -r", "normalize a tree (asks before writing)"),
    ("ebrium fonts/ -r -n", "preview the changes"),
    ("ebrium fonts/ -r --report", "family vs per-font analysis (implies -n)"),
    ("ebrium fonts/ -r -y", "skip the confirmation prompt"),
    ("ebrium fonts/ --ignore-prefix Adobe", "ignore a vendor prefix when grouping"),
    ('ebrium fonts/ --combine "A,B" --force-baseline', "merge two families, then unify the line box"),
    ("ebrium fonts/ --assume-script '*Swash*'", "override script detection by filename"),
]

NOTES = [
    "Every run, even with -n or --report, writes .metrics_checkpoint.json to the current "
    "directory. It caches measurements and clusters, and resets when the options or the "
    "font set change.",
    "--combine, --ignore-prefix and --exclude are ignored with --individual; "
    "--exclude only applies to --superfamily.",
    "--safe-hhea takes precedence over --force-baseline, which is also ignored with --individual.",
    "--force-baseline-main-cluster and --force-baseline-from only work together with "
    "--force-baseline; --force-baseline-from wins if both are given.",
    "--force-baseline skips single-font families (e.g. a lone 'Name Variable'); "
    "pair them with --combine.",
    "--probe-variation-metrics ignores -n, --report and the --force-baseline options; "
    "add -v for per-pole deltas.",
]

EXIT_CODES = {
    "0": "done (including nothing to change, previews, reports and probes)",
    "1": "no font files found",
    "2": "no measurable fonts (also used for invalid arguments)",
    "3": "aborted at the confirmation prompt",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebrium",
        usage="%(prog)s [options] [PATH ...]",
        description=DESCRIPTION,
        add_help=False,  # -h is registered below so it can live in "general"
    )

    # Groups display in creation order; create them in the order you want to read them.
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview and confirmation")
    g_space = p.add_argument_group("vertical spacing (% of UPM)")
    g_mode = p.add_argument_group("grouping mode (choose one)")
    g_mod = p.add_argument_group("grouping modifiers (repeatable)")
    g_box = p.add_argument_group("line box (typo / hhea)")
    g_det = p.add_argument_group("detection overrides (filename globs, repeatable)")
    g_gen = p.add_argument_group("general")

    # ---- general
    g_gen.add_argument(
        "-h", "--help", action=RichHelp, help="show this help message and exit",
        console=get_console(), panel=PANEL,
        footer=[
            examples_section(EXAMPLES),
            notes_section(NOTES),
            exit_status_section(EXIT_CODES),
            line_section("formats", "TTF, OTF, WOFF, WOFF2 (.ttx with --use-ttx)"),
            docs_section("https://github.com/andrewsipe/ebrium"),
        ],
    )
    g_gen.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    g_gen.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="verbose output; -vv for debug output",
    )

    # ---- input
    g_in.add_argument(
        "paths", nargs="*", metavar="PATH",
        help="font files or directories (default: current directory)",
    )
    g_in.add_argument("-r", "--recursive", action="store_true", help="recurse into directories")
    g_in.add_argument("--use-ttx", action="store_true", help="also process .ttx files")

    # ---- preview and confirmation
    g_run.add_argument("-n", "--dry-run", action="store_true", help="preview changes without writing")
    g_run.add_argument("-y", "--yes", action="store_true", help="skip the 'Proceed? [y/N]' prompt")
    g_run.add_argument(
        "--report", action="store_true",
        help="detailed family vs per-font analysis (implies --dry-run)",
    )
    g_run.add_argument(
        "--probe-variation-metrics", action="store_true",
        help="read-only MVAR/HVAR coverage report; does not measure or write fonts",
    )

    # ---- vertical spacing
    g_space.add_argument(
        "--letter-height", type=float, default=130, metavar="PERCENT",
        help="target height of the letter span (default: 130)",
    )
    g_space.add_argument(
        "--top-margin", type=float, default=25, metavar="PERCENT",
        help="extra space above capitals (default: 25)",
    )
    g_space.add_argument(
        "--max-adjustment", type=float, default=None, metavar="PERCENT",
        help="cap how far family extremes may pull a font (default: no cap); "
        "fonts over the cap are calculated individually",
    )
    g_space.add_argument(
        "--no-auto-adjust", action="store_true",
        help="use exactly --letter-height (skip the x-height adjustment)",
    )

    # ---- grouping mode: one real mutually exclusive group, all four flags
    mode = g_mode.add_mutually_exclusive_group()
    mode.add_argument(
        "--family", dest="grouping_mode", action="store_const", const="family",
        help="group by family name; cluster within each family (default)",
    )
    mode.add_argument(
        "--superfamily", dest="grouping_mode", action="store_const", const="superfamily",
        help="merge families sharing a name prefix; cluster across the superfamily",
    )
    mode.add_argument(
        "--individual", dest="grouping_mode", action="store_const", const="individual",
        help="normalize each font on its own; no grouping or clustering",
    )
    mode.add_argument(
        "--safe-max", dest="grouping_mode", action="store_const", const="conservative",
        help="per family, use bbox extremes for every font; no clustering (prevents clipping)",
    )
    p.set_defaults(grouping_mode="family")

    # ---- grouping modifiers
    g_mod.add_argument(
        "--combine", action="append", metavar="FAMILIES",
        help='force-merge families, e.g. --combine "Font A,Font B"',
    )
    g_mod.add_argument(
        "--ignore-prefix", action="append", metavar="TOKEN",
        help="ignore a leading token when matching family names (e.g. Adobe, LT)",
    )
    g_mod.add_argument(
        "--exclude", action="append", metavar="FAMILY",
        help="keep FAMILY out of superfamily merges (--superfamily only)",
    )

    # ---- line box
    g_box.add_argument(
        "--force-baseline", action="store_true",
        help="unify the typo/hhea line box across each family, using its largest-span style "
        "(macOS/UI centering follows typo/hhea)",
    )
    g_box.add_argument(
        "--force-baseline-main-cluster", action="store_true",
        help="with --force-baseline: pick the reference from the largest optical cluster only",
    )
    g_box.add_argument(
        "--force-baseline-from", default=None, metavar="PATH_OR_GLOB",
        help="with --force-baseline: pin the reference font (path, filename, or filename glob)",
    )
    g_box.add_argument(
        "--safe-hhea", action="store_true",
        help="average existing typo/hhea values across each family and apply them "
        "uniformly (Win uses max ranges)",
    )

    # ---- detection overrides
    g_det.add_argument(
        "--assume-script", action="append", metavar="PATTERN",
        help="treat matching fonts as script (e.g. '*Script*', '*Swash*')",
    )
    g_det.add_argument(
        "--assume-decorative", action="append", metavar="PATTERN",
        help="treat matching fonts as decorative (e.g. '*Rough*', '*Inline*')",
    )
    g_det.add_argument(
        "--assume-unicase", action="append", metavar="PATTERN",
        help="treat matching fonts as unicase (e.g. '*Unicase*')",
    )
    g_det.add_argument(
        "--assume-uniwidth", action="append", metavar="PATTERN",
        help="treat matching fonts as uniwidth; one match flags the whole family",
    )
    g_det.add_argument(
        "--exclude-measuring", action="append", metavar="PATTERN",
        help="measure matching fonts but leave them out of family calculations",
    )

    # ---- hidden expert thresholds (unchanged)
    p.add_argument("--decorative-threshold", type=float, default=1.4, help=argparse.SUPPRESS)
    p.add_argument("--unicase-threshold", type=float, default=0.05, help=argparse.SUPPRESS)
    p.add_argument("--max-span-ratio", type=float, default=1.5, help=argparse.SUPPRESS)
    return p
