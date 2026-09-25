"""ebrium argument parser.

One command writes a centered line box per family. ``ebrium probe`` reads
metrics and does not write. ``finalize_args`` sets ``grouping_mode`` and
``plan_mode`` from ``--no-cluster``.
"""

from __future__ import annotations

import argparse
from typing import Any

from FontCore.core_cli_help import (
    RichHelp,
    choices_section,
    docs_section,
    examples_section,
    exit_status_section,
    line_section,
    notes_section,
    safety_panel,
)
from FontCore.core_console_styles import get_console

from . import __version__

PROG = "ebrium"
DOCS_URL = "https://www.andrewsipe.com/Ebrium/"
FORMATS_LINE = "TTF, OTF, WOFF, WOFF2 (.ttx with --use-ttx)"

EXIT_CODES = {
    "0": "done (including nothing to change, previews and reports)",
    "1": "no font files found",
    "2": "no measurable fonts (also used for invalid arguments)",
    "3": "aborted at the confirmation prompt",
}

PROBE_EXIT_CODES = {
    "0": "done",
    "1": "no font files found",
    "2": "invalid arguments",
}

CHECKPOINT_NOTE = (
    "Every run, even with -n, writes .metrics_checkpoint.json to the current "
    "directory. It caches measurements and clusters, and resets when the options "
    "or the font set change."
)

PANEL_ROWS_BASIC = [("Preview only", "-n, --dry-run")]
PANEL_MESSAGE = (
    "Fonts are modified in place: no backup and no output directory. "
    "You are asked to confirm before anything is written."
)


# Shared flag builders. Group parameters are Any because argparse's group class is private.

def _add_input_args(g: Any) -> None:
    g.add_argument(
        "paths", nargs="*", metavar="PATH",
        help="font files or directories (default: current directory)",
    )
    g.add_argument("-r", "--recursive", action="store_true", help="recurse into directories")
    g.add_argument("--use-ttx", action="store_true", help="also process .ttx files")


def _add_preview_args(g: Any) -> None:
    g.add_argument("-n", "--dry-run", action="store_true", help="preview changes without writing")
    g.add_argument("-y", "--yes", action="store_true", help="skip the 'Proceed? [y/N]' prompt")


def _add_general_args(g: Any, verbose_help: str) -> None:
    g.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    g.add_argument("-v", "--verbose", action="count", default=0, help=verbose_help)


def _add_help(
    g: Any,
    *,
    panel,
    footer,
    inline=None,
) -> None:
    g.add_argument(
        "-h", "--help", action=RichHelp, help="show this help message and exit",
        console=get_console(), panel=panel, inline=inline or {}, footer=footer,
    )


# ---------------------------------------------------------------- probe

def build_probe_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebrium probe",
        usage="%(prog)s [options] [PATH ...]",
        allow_abbrev=False,
        description="Read-only metrics for every font. Groups by family, shows the "
        "driver and each font's pull, and lists slider facts for variable fonts. "
        "Does not modify fonts.",
        add_help=False,
    )
    g_in = p.add_argument_group("input")
    g_out = p.add_argument_group("report")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium probe fonts/ -r", "metrics tables, grouped by family"),
        ("ebrium probe fonts/ -r -q -o probe.tsv", "write the same rows to a spreadsheet"),
    ]

    _add_help(
        g_gen,
        panel=False,  # fonts are not modified; no safety wording needed
        footer=[
            examples_section(examples),
            exit_status_section(PROBE_EXIT_CODES),
            line_section("formats", FORMATS_LINE),
            docs_section(DOCS_URL),
        ],
    )
    g_out.add_argument(
        "-o", "--output", metavar="FILE",
        help="write a tab-separated metrics sheet as the run goes (kept if you stop early). "
        "A relative FILE is saved at the top of the directory you probed, not the "
        "shell's current directory",
    )
    g_out.add_argument(
        "-m", "--match",
        action="append",
        dest="combine",
        metavar="NAMES",
        help='pair families whose names do not already group, so the report shows one group: '
        '--match "Family A,Family B". Repeat for another pair',
    )
    p.add_argument("--merge", action="append", dest="combine", help=argparse.SUPPRESS)
    g_out.add_argument(
        "-q", "--quiet", action="store_true",
        help="terminal shows the current filename and a progress bar, then the tally; "
        "per-font lines go to --output only",
    )
    _add_general_args(
        g_gen, "-v adds the compact hhea, typo, and Win table; -vv uses one table with each value in its own column"
    )
    _add_input_args(g_in)
    return p

# ---------------------------------------------------------------- top level

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        usage="%(prog)s [options] [PATH ...]\n       %(prog)s probe [options] [PATH ...]",
        allow_abbrev=False,
        description=(
            "Give each family one centered line box. Outlines do not move. "
            "Effect cuts inherit that box. Optical sizes each keep their own. "
            "ebrium probe reads those metrics and does not write."
        ),
        add_help=False,
    )
    g_in = p.add_argument_group("input")
    g_run = p.add_argument_group("preview")
    g_plan = p.add_argument_group("plan")
    g_gen = p.add_argument_group("general")

    examples = [
        ("ebrium fonts/ -r -n", "preview"),
        ("ebrium fonts/ --span 120", "tighter line box"),
        ("ebrium fonts/ --line-gap 5", "a little space between lines"),
        ('ebrium fonts/ --match "Family A,Family B"', "one box for two family names"),
    ]
    notes = [
        "The plan is cap height, centered, at least 130% of the em. "
        "A taller accent or a deeper descender can raise one side.",
        "Shadow, Extrude, Fine, and similar effect cuts inherit the family's box. "
        "Caption, Display, Subhead, and Small Text each get their own.",
        "--no-cluster skips that plan. The family shares one box set to its outline extremes, so nothing clips.",
        '--match "Family A,Family B" pairs families whose names do not already group, so they share one line box. '
        "Repeat the flag for another pair. Each flag is its own pair.",
        "--span is the letter-span floor, as a percent of the em (default 130). "
        "120 is tighter, 150 is looser. A measured accent can still raise it.",
        "--line-gap adds space between lines, as a percent of the em (default 0). "
        "0 means the box itself is the line spacing. 5 is slightly looser.",
        CHECKPOINT_NOTE,
    ]
    _add_help(
        g_gen,
        panel=safety_panel(message=PANEL_MESSAGE, rows=PANEL_ROWS_BASIC),
        footer=[
            choices_section("commands", {
                PROG: "write the centered line box",
                f"{PROG} probe": "read metrics and write nothing",
            }),
            examples_section(examples),
            notes_section(notes),
            exit_status_section(EXIT_CODES),
            docs_section(DOCS_URL),
        ],
    )
    _add_input_args(g_in)
    _add_preview_args(g_run)
    g_plan.add_argument(
        "--span",
        type=float,
        default=130,
        metavar="PERCENT",
        help="letter-span floor as a percent of the em (default: 130). "
        "Tighter 120, looser 150. A measured accent may still raise it",
    )
    g_plan.add_argument(
        "--line-gap",
        type=float,
        default=0,
        metavar="PERCENT",
        help="extra space between lines as a percent of the em (default: 0). "
        "5 is slightly looser",
    )
    g_plan.add_argument(
        "--no-cluster",
        action="store_true",
        help="one shared box from the family's outline extremes, so nothing clips. "
        "Skips the centered plan. Formerly --safe-max",
    )
    g_plan.add_argument(
        "-m", "--match",
        action="append",
        dest="combine",
        metavar="NAMES",
        help='families in one flag share a line box, even when the names differ: '
        '--match "Family A,Family B". Repeat for another pair. '
        "Each flag is its own pair: -m A -m B does not match A with B",
    )
    # Old spelling. Same destination, hidden from help.
    p.add_argument("--merge", action="append", dest="combine", help=argparse.SUPPRESS)
    _add_general_args(g_gen, "verbose output; -vv for debug output")
    return p


def finalize_args(args: argparse.Namespace) -> None:
    """Grouping is always by family. --no-cluster switches the plan to outline extremes."""
    if getattr(args, "mode", None) == "probe":
        args.plan_mode = None
        args.grouping_mode = "family"
    else:
        args.mode = None
        if getattr(args, "no_cluster", False):
            args.grouping_mode = "conservative"
            args.plan_mode = "conservative"
        else:
            args.grouping_mode = "family"
            args.plan_mode = "family"

    if not hasattr(args, "combine"):
        args.combine = None
