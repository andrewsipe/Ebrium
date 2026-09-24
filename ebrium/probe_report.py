"""Read-only metrics tables for probe.

One table per family group: measured geometry, the metrics stored on disk,
and how far grouping would pull each font. Variable fonts sit in that table
at their default instance. Slider facts are printed under the group.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, TextIO, Tuple

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console
from fontTools.ttLib import TTFont

from . import config
from . import grouping
from . import measurements
from . import planning
from .models import FontMeasures
from .variation_probe import (
    Survey,
    _axis_sentence,
    _hang_percent,
    _percent_text,
    _pole_name,
    explain_survey,
    report_destination,
    survey_font,
)

MetricsConfig = config.MetricsConfig


@dataclass
class StoredMetrics:
    typo_asc: int
    typo_desc: int
    typo_gap: int
    win_asc: int
    win_desc: int
    hhea_asc: int
    hhea_desc: int
    hhea_gap: int
    use_typo: bool


@dataclass
class ProbeRow:
    measure: FontMeasures
    stored: Optional[StoredMetrics]
    survey: Optional[Survey]
    pull_units: Optional[int]
    pull_percent: Optional[float]
    is_driver: bool


def read_stored_metrics(path: str) -> Optional[StoredMetrics]:
    try:
        font = TTFont(path)
    except Exception:
        return None
    try:
        os2 = font["OS/2"] if "OS/2" in font else None
        hhea = font["hhea"] if "hhea" in font else None
        if os2 is None:
            return None
        selection = int(getattr(os2, "fsSelection", 0) or 0)
        return StoredMetrics(
            typo_asc=int(getattr(os2, "sTypoAscender", 0) or 0),
            typo_desc=int(getattr(os2, "sTypoDescender", 0) or 0),
            typo_gap=int(getattr(os2, "sTypoLineGap", 0) or 0),
            win_asc=int(getattr(os2, "usWinAscent", 0) or 0),
            win_desc=int(getattr(os2, "usWinDescent", 0) or 0),
            hhea_asc=int(getattr(hhea, "ascent", 0) or 0) if hhea else 0,
            hhea_desc=int(getattr(hhea, "descent", 0) or 0) if hhea else 0,
            hhea_gap=int(getattr(hhea, "lineGap", 0) or 0) if hhea else 0,
            use_typo=bool(selection & (1 << 7)),
        )
    finally:
        font.close()


def _driver(group: Sequence[FontMeasures]) -> FontMeasures:
    def key(fm: FontMeasures) -> float:
        if fm.upm <= 0 or not fm.ascender_max:
            return 0.0
        return fm.ascender_max / fm.upm

    return max(group, key=key)


def order_group(group: Sequence[FontMeasures], cfg: MetricsConfig) -> List[ProbeRow]:
    """Driver first, then the rest from the smallest pull to the largest."""
    stored = {fm.path: read_stored_metrics(fm.path) for fm in group}
    surveys = {}
    for fm in group:
        try:
            font = TTFont(fm.path)
        except Exception:
            surveys[fm.path] = None
            continue
        try:
            surveys[fm.path] = survey_font(font) if "fvar" in font else None
        finally:
            font.close()

    if len(group) < 2:
        fm = group[0]
        return [
            ProbeRow(fm, stored[fm.path], surveys[fm.path], None, None, is_driver=True)
        ]

    family_asc = planning.compute_family_normalized_ascender(list(group), cfg)
    driver = _driver(group)
    ranked: List[ProbeRow] = []
    for fm in group:
        solo = planning.compute_family_normalized_ascender([fm], cfg)
        family_value = int(round(family_asc * fm.upm))
        solo_value = int(round(solo * fm.upm))
        diff_units = family_value - solo_value
        diff_percent = ((family_asc - solo) / solo * 100.0) if solo > 0 else 0.0
        ranked.append(
            ProbeRow(
                fm,
                stored[fm.path],
                surveys[fm.path],
                diff_units,
                diff_percent,
                is_driver=fm.path == driver.path,
            )
        )
    ranked.sort(key=lambda row: (0 if row.is_driver else 1, abs(row.pull_percent or 0.0)))
    return ranked


def _dash(value: object) -> str:
    if value is None:
        return "—"
    return str(value)


def _use_typo(stored: Optional[StoredMetrics]) -> str:
    if stored is None:
        return "—"
    return "set" if stored.use_typo else "clear"


def _pull_amount(row: ProbeRow) -> str:
    if row.pull_units is None:
        return "—"
    sign = "+" if row.pull_units > 0 else ""
    return f"{sign}{row.pull_units}u ({row.pull_percent:+.1f}%)"


def _stored_num(stored: Optional[StoredMetrics], name: str) -> str:
    if stored is None:
        return "—"
    return str(getattr(stored, name))


def slider_lines(survey: Optional[Survey]) -> List[str]:
    if survey is None or survey.clipping == "static":
        return []
    lines = [" ".join(_axis_sentence(*axis) for axis in survey.axes)]
    if survey.line_box == "moves":
        lines.append("Line spacing changes with the sliders.")
    else:
        lines.append("Line spacing stays the same.")
    if survey.overflows:
        worst = max(survey.overflows, key=lambda item: max(item.above, item.below))
        lines.append(
            f"{_pole_name(worst.label).capitalize()} passes the clipping box by "
            f"{_percent_text(_hang_percent(worst, survey.upm))} of the em."
        )
    else:
        lines.append("Slider ends stay inside the clipping box.")
    return lines


def slider_note(survey: Optional[Survey]) -> str:
    return " ".join(slider_lines(survey))


def collect_groups(files: Sequence[str], args) -> Dict[str, List[ProbeRow]]:
    measures = measurements.measure_fonts(list(files))
    if not measures:
        return {}
    forced_groups = []
    for group_str in getattr(args, "combine", None) or []:
        families = [name.strip() for name in group_str.split(",") if name.strip()]
        if len(families) >= 2:
            forced_groups.append(families)
    families = grouping.group_families(args, measures, forced_groups)
    cfg = MetricsConfig()
    return {name: order_group(group, cfg) for name, group in families.items()}


REPORT_COLUMNS = (
    "group",
    "file",
    "driver",
    "upm",
    "cap",
    "x_height",
    "hhea_asc",
    "hhea_desc",
    "hhea_gap",
    "typo_asc",
    "typo_desc",
    "typo_gap",
    "win_asc",
    "win_desc",
    "use_typo",
    "pull",
    "sliders",
)

SCAN_HEADERS = ("File", "UPM", "Cap", "xHt", "Pull")
METRIC_HEADERS = ("File", "hhea A/D/L", "sTypo A/D/L", "usWin A/D", "UseTypo")
FULL_HEADERS = (
    "File",
    "UPM",
    "Cap",
    "xHt",
    "hheaA",
    "hheaD",
    "hheaLG",
    "sTypoA",
    "sTypoD",
    "sTypoLG",
    "WinA",
    "WinD",
    "UseTypo",
    "Pull",
)
DRIVER_STYLE = "bold magenta2"


def _file_label(row: ProbeRow) -> str:
    name = Path(row.measure.path).name
    if row.is_driver:
        return f"[{DRIVER_STYLE}]{name}[/{DRIVER_STYLE}]"
    return name


def _triple(stored: Optional[StoredMetrics], asc: str, desc: str, gap: str) -> str:
    if stored is None:
        return "—"
    return f"{getattr(stored, asc)}/{getattr(stored, desc)}/{getattr(stored, gap)}"


def _pair(stored: Optional[StoredMetrics], asc: str, desc: str) -> str:
    if stored is None:
        return "—"
    return f"{getattr(stored, asc)}/{getattr(stored, desc)}"


def scan_cells(row: ProbeRow) -> List[str]:
    fm = row.measure
    return [
        _file_label(row),
        str(fm.upm),
        _dash(fm.cap_height),
        _dash(fm.x_height),
        _pull_amount(row),
    ]


def metric_cells(row: ProbeRow) -> List[str]:
    stored = row.stored
    return [
        _file_label(row),
        _triple(stored, "hhea_asc", "hhea_desc", "hhea_gap"),
        _triple(stored, "typo_asc", "typo_desc", "typo_gap"),
        _pair(stored, "win_asc", "win_desc"),
        _use_typo(stored),
    ]


def full_cells(row: ProbeRow) -> List[str]:
    fm = row.measure
    stored = row.stored
    return [
        _file_label(row),
        str(fm.upm),
        _dash(fm.cap_height),
        _dash(fm.x_height),
        _stored_num(stored, "hhea_asc"),
        _stored_num(stored, "hhea_desc"),
        _stored_num(stored, "hhea_gap"),
        _stored_num(stored, "typo_asc"),
        _stored_num(stored, "typo_desc"),
        _stored_num(stored, "typo_gap"),
        _stored_num(stored, "win_asc"),
        _stored_num(stored, "win_desc"),
        _use_typo(stored),
        _pull_amount(row),
    ]


def row_values(group: str, row: ProbeRow) -> List[str]:
    fm = row.measure
    stored = row.stored
    return [
        group,
        Path(fm.path).name,
        "yes" if row.is_driver else "",
        str(fm.upm),
        _dash(fm.cap_height),
        _dash(fm.x_height),
        _stored_num(stored, "hhea_asc"),
        _stored_num(stored, "hhea_desc"),
        _stored_num(stored, "hhea_gap"),
        _stored_num(stored, "typo_asc"),
        _stored_num(stored, "typo_desc"),
        _stored_num(stored, "typo_gap"),
        _stored_num(stored, "win_asc"),
        _stored_num(stored, "win_desc"),
        _use_typo(stored),
        _pull_amount(row),
        slider_note(row.survey),
    ]


def _print_one_table(title: str, headers: Sequence[str], rows: List[List[str]]) -> None:
    console = get_console()
    table = cs.create_table(title=title)
    if table is None:
        cs.emit(title, console=console)
        cs.emit("  " + "  ".join(headers), console=console)
        for cells in rows:
            cs.emit("  " + "  ".join(cells), console=console)
        return
    table.expand = True
    table.add_column(headers[0], overflow="fold", max_width=36)
    for header in headers[1:]:
        table.add_column(header, justify="right", no_wrap=True)
    for cells in rows:
        table.add_row(*cells)
    console.print(table)


def _print_table(group: str, rows: List[ProbeRow], *, verbose: int) -> None:
    console = get_console()
    driver = next((row for row in rows if row.is_driver), rows[0])
    title = f"{group} — {len(rows)} font(s) — driver {Path(driver.measure.path).name}"
    if verbose >= 2:
        _print_one_table(title, FULL_HEADERS, [full_cells(row) for row in rows])
    else:
        _print_one_table(title, SCAN_HEADERS, [scan_cells(row) for row in rows])
        if verbose >= 1:
            cs.emit("", console=console)
            _print_one_table(
                f"{group} — hhea, typo, Win",
                METRIC_HEADERS,
                [metric_cells(row) for row in rows],
            )
    variable_rows = [row for row in rows if slider_lines(row.survey)]
    if variable_rows:
        cs.emit("", console=console)
        cs.emit("[bold]Sliders[/bold]", console=console)
        for row in variable_rows:
            cs.emit("", console=console)
            cs.emit(f"  [bold]{Path(row.measure.path).name}[/bold]", console=console)
            for line in slider_lines(row.survey):
                cs.emit(f"    {line}", console=console)


def present(
    groups: Dict[str, List[ProbeRow]],
    *,
    quiet: bool,
    output: Optional[str],
    source_paths: Sequence[str],
    verbose: int = 0,
) -> None:
    console = get_console()
    handle: Optional[TextIO] = None
    writer = None
    if output:
        output = report_destination(output, source_paths)
        handle = open(output, "w", newline="", encoding="utf-8")
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(REPORT_COLUMNS)
    try:
        if not quiet:
            for name in sorted(groups):
                _print_table(name, groups[name], verbose=verbose)
                cs.emit("", console=console)
        if writer is not None and handle is not None:
            for name, rows in groups.items():
                for row in rows:
                    writer.writerow(row_values(name, row))
            handle.flush()
    finally:
        if handle is not None:
            handle.close()
    count = sum(len(rows) for rows in groups.values())
    message = f"Probe: {count} font(s), {len(groups)} group(s)."
    if output:
        message += f" Report: {output}."
    cs.StatusIndicator("info").add_message(message).emit(console)
