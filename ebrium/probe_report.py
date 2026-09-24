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
from FontCore.core_logging_config import Verbosity
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
    nc_units: Optional[int] = None
    nc_percent: Optional[float] = None


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


def _clear_targets(group: Sequence[FontMeasures]) -> None:
    for fm in group:
        fm.target_typo_asc = None
        fm.target_typo_desc = None
        fm.target_win_asc = None
        fm.target_win_desc = None


def _planned_ascenders(group: Sequence[FontMeasures], cfg: MetricsConfig, mode: str) -> Dict[str, Optional[int]]:
    _clear_targets(group)
    planning.build_plans(
        {mode: list(group)},
        cfg,
        verbosity=Verbosity.QUIET,
        grouping_mode=mode,
    )
    return {fm.path: fm.target_typo_asc for fm in group}


def _pull_from(planned: Optional[int], solo: Optional[int]) -> Tuple[Optional[int], Optional[float]]:
    if planned is None or solo is None:
        return None, None
    units = planned - solo
    percent = (units / solo * 100.0) if solo else 0.0
    return units, percent


def order_group(
    group: Sequence[FontMeasures],
    cfg: MetricsConfig,
    *,
    no_cluster: bool,
) -> List[ProbeRow]:
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
            ProbeRow(fm, stored[fm.path], surveys[fm.path], None, None, True)
        ]

    solo = {}
    for fm in group:
        solo[fm.path] = _planned_ascenders([fm], cfg, "individual").get(fm.path)
    mode = "superfamily" if not no_cluster else "family"
    clustered = _planned_ascenders(group, cfg, mode)
    flat = _planned_ascenders(group, cfg, "conservative") if no_cluster else {}
    driver = _driver(group)
    ranked: List[ProbeRow] = []
    for fm in group:
        units, percent = _pull_from(clustered.get(fm.path), solo.get(fm.path))
        nc_units, nc_percent = _pull_from(flat.get(fm.path), solo.get(fm.path))
        ranked.append(
            ProbeRow(
                fm,
                stored[fm.path],
                surveys[fm.path],
                units,
                percent,
                fm.path == driver.path,
                nc_units if no_cluster else None,
                nc_percent if no_cluster else None,
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


def _fmt_pull(units: Optional[int], percent: Optional[float], *, verbose: int) -> str:
    if units is None or percent is None:
        return "—"
    if verbose < 1:
        if abs(percent) < 0.05:
            return "0%"
        arrow = "↑" if percent > 0 else "↓"
        return f"{abs(percent):.1f}% {arrow}"
    sign = "+" if units > 0 else ""
    return f"{sign}{units}u ({percent:+.1f}%)"


def _pull_amount(row: ProbeRow, *, verbose: int) -> str:
    return _fmt_pull(row.pull_units, row.pull_percent, verbose=verbose)


def _nc_amount(row: ProbeRow, *, verbose: int) -> str:
    return _fmt_pull(row.nc_units, row.nc_percent, verbose=verbose)


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
    no_cluster = getattr(args, "grouping_mode", "family") != "superfamily"
    return {
        name: order_group(group, cfg, no_cluster=no_cluster)
        for name, group in families.items()
    }


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
    "pull_no_cluster",
    "sliders",
)

SCAN_HEADERS = ("File", "Cap height", "x-height", "Shift")
SCAN_HEADERS_TECH = ("File", "UPM", "Cap", "xHt", "Pull")
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


def scan_cells(row: ProbeRow, *, verbose: int, no_cluster: bool) -> List[str]:
    fm = row.measure
    name = _file_label(row)
    shift = _pull_amount(row, verbose=verbose)
    if verbose < 1:
        cells = [name, _dash(fm.cap_height), _dash(fm.x_height), shift]
    else:
        cells = [name, str(fm.upm), _dash(fm.cap_height), _dash(fm.x_height), shift]
    if no_cluster:
        cells.append(_nc_amount(row, verbose=verbose))
    return cells


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
        _pull_amount(row, verbose=1),
        _nc_amount(row, verbose=1),
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
        _pull_amount(row, verbose=1),
        _nc_amount(row, verbose=1),
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
    noun = "font" if verbose >= 1 else "style"
    noun += "" if len(rows) == 1 else "s"
    if verbose >= 1:
        title = f"{group} — {len(rows)} {noun} — driver {Path(driver.measure.path).name}"
    else:
        title = f"{group} — {len(rows)} {noun} — spacing set by {Path(driver.measure.path).name}"
    no_cluster = any(row.nc_units is not None for row in rows)
    if verbose >= 2:
        headers = list(FULL_HEADERS)
        cells = [full_cells(row) for row in rows]
        if no_cluster:
            headers.append("No cluster")
        else:
            cells = [row_cells[:-1] for row_cells in cells]
        _print_one_table(title, headers, cells)
    else:
        headers = list(SCAN_HEADERS_TECH if verbose >= 1 else SCAN_HEADERS)
        if no_cluster:
            headers.append("No cluster")
        _print_one_table(
            title,
            headers,
            [scan_cells(row, verbose=verbose, no_cluster=no_cluster) for row in rows],
        )
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
