"""Rich-styled --help building blocks shared by FontFixer, ebrium, etc.

Intended home: FontCore/core_cli_help.py (then vendored like the other core_*
modules). Backward compatible with the earlier fontfixer_help_v2.py: same names,
same defaults, so FontFixer only needs its import line changed.

Layout of a help screen produced with RichHelp:

    usage / description        <- argparse
    safety panel               <- safety_panel(...)
    option groups              <- argparse (keep help= strings to one line)
    footer sections            <- handlers_section / examples_section /
                                  notes_section / exit_status_section /
                                  line_section / docs_section

Colors are named ANSI colors so they follow the terminal palette, matching
argparse's own coloring on Python 3.14+. Retheme via the constants below.
"""

from __future__ import annotations  # keeps `X | None` annotations valid on 3.9

import argparse
import re
from typing import Iterable, Mapping, Sequence

from rich.console import Console, Group, RenderableType
from rich.constrain import Constrain
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

HEADING = "bold blue"   # section headings, like argparse's "options:"
FLAG = "bold green"     # flags, handler names
PROG = "bold magenta"   # program name inside example commands
OK, BAD = "green", "red"
INDENT = (0, 0, 0, 2)
PANEL_MAX_WIDTH = 72   # text width inside the safety panel

_FLAG_RE = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")


def _heading(title: str, note: str = "") -> Text:
    return Text(f"{title} ({note}):" if note else f"{title}:", style=HEADING)


def _grid() -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(no_wrap=True)
    grid.add_column()
    return grid


def _section(title: str, body: RenderableType, note: str = "") -> RenderableType:
    return Group(_heading(title, note), Padding(body, INDENT, expand=False))


def _flagged(text: str, style: str = "") -> Text:
    """Text with anything that looks like a --flag or -f highlighted."""
    t = Text(text, style=style)
    t.highlight_regex(_FLAG_RE, style=FLAG)
    return t


# ---------------------------------------------------------------- panel

DEFAULT_PANEL_MESSAGE = "Fixes overwrite your original fonts by default. There is no backup."
DEFAULT_PANEL_ROWS = (
    ("Keep originals", "-o DIR"),
    ("Inspect fonts, fix nothing", "--validate-only"),
    ("List files only", "-n, --dry-run"),
)


def safety_panel(
    message: str = DEFAULT_PANEL_MESSAGE,
    rows: Sequence[tuple[str, str]] = DEFAULT_PANEL_ROWS,
    title: str = "Heads up",
) -> Panel:
    """Boxed notice. `rows` are (what you want, flag) pairs. Built from Text and
    Table objects, never markup strings, so "[-o DIR]" can't be misread as markup."""
    grid = _grid()
    for label, flag in rows:
        grid.add_row(Text(label, style="bold"), Text(flag, style=FLAG))

    body = Table.grid()
    body.add_row(Text(message))
    if rows:
        body.add_row("")
        body.add_row(grid)
    return Panel.fit(
        Constrain(body, PANEL_MAX_WIDTH),  # long messages wrap instead of stretching the box
        title=Text(title, style="bold yellow"),
        title_align="left",
        border_style="yellow",
        padding=(0, 2),
    )


# ------------------------------------------------------------- sections

def choices_section(title: str, choices: Mapping[str, str], note: str = "") -> RenderableType:
    """Table of value -> meaning, for a --flag {a,b,c}-style argument whose
    choices need more room than a one-line option help string allows."""
    grid = _grid()
    for name, desc in choices.items():
        grid.add_row(Text(name, style=FLAG), Text(desc))
    return _section(title, grid, note)


def handlers_section(handlers: Mapping[str, str], note: str = "") -> RenderableType:
    return choices_section("handlers", handlers, note)


def _command(cmd: str) -> Text:
    out = Text()
    for i, tok in enumerate(cmd.split(" ")):
        if i:
            out.append(" ")
        out.append(tok, style=PROG if i == 0 else FLAG if tok.startswith("-") else "")
    return out


def examples_section(examples: Iterable[tuple[str, str]]) -> RenderableType:
    grid = _grid()
    for cmd, desc in examples:
        grid.add_row(_command(cmd), Text(desc, style="dim"))
    return _section("examples", grid)


def notes_section(items: Iterable[str], title: str = "notes") -> RenderableType:
    """Short bullets; --flags inside them are highlighted automatically.
    Bullets wrap with a hanging indent."""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column()
    for item in items:
        grid.add_row(Text("•", style=HEADING), _flagged(item))
    return _section(title, grid)


def exit_status_section(codes: Mapping[str, str]) -> RenderableType:
    grid = _grid()
    for code, desc in codes.items():
        grid.add_row(Text(code, style=OK if code == "0" else BAD), Text(desc))
    return _section("exit status", grid)


def line_section(label: str, text: str) -> RenderableType:
    """One-liner like 'formats: TTF, OTF, ...'."""
    line = Text()
    line.append(f"{label}: ", style=HEADING)
    line.append(text)
    return line


def docs_section(url: str) -> RenderableType:
    line = Text()
    line.append("docs: ", style=HEADING)
    line.append(url, style=f"underline link {url}")  # clickable in most terminals
    return line


# --------------------------------------------------------------- action

class RichHelp(argparse.Action):
    """-h/--help: argparse's own output with `panel` inserted after the
    description, followed by the Rich `footer` sections."""

    def __init__(
        self,
        option_strings,
        dest=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
        help=None,
        console: Console | None = None,
        footer: Sequence[RenderableType] = (),
        panel: RenderableType | None = None,
    ):
        super().__init__(option_strings, dest=dest, default=default, nargs=0, help=help)
        self._console = console
        self._footer = list(footer)
        self._panel = panel

    def __call__(self, parser, namespace, values, option_string=None):
        console = self._console or Console()
        panel = self._panel if self._panel is not None else safety_panel()
        text = parser.format_help()

        # Insert the panel right after the description block. Split on the usage
        # text rather than searching for the description string, so it still works
        # when argparse re-wraps the description (default formatter).
        usage = parser.format_usage()
        head = tail = ""
        if parser.description and text.startswith(usage):
            rest = text[len(usage):].lstrip("\n")
            block, sep, tail = rest.partition("\n\n")
            if sep:
                head = usage + "\n" + block + "\n"

        # console.out prints raw text: no markup parsing, no auto-highlight.
        if head:
            console.out(head, highlight=False, end="")
            console.print()
            console.print(panel)
            console.print()
            console.out(tail.lstrip("\n"), highlight=False, end="")
        else:
            console.print(panel)
            console.print()
            console.out(text, highlight=False, end="")

        for section in self._footer:
            console.print()
            console.print(section)
        parser.exit()
