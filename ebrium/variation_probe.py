"""Read-only variable-font report for the line box and the Win clipping box.

Samples the default instance and each axis pole (other axes left at their
defaults). Does not modify fonts. ``--output`` writes a tab-separated report.
Two questions:

- Typo line box (MVAR hasc / hdsc / hlgp): if it already moves, leave it.
- Win clipping box (usWinAscent / usWinDescent): if hcla / hcld are flat and a
  pole's ink sticks out past both the Win box and the default instance's ink,
  that is the only adjustment worth considering later.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TextIO
from collections.abc import Mapping, Sequence

from fontTools.misc.fixedTools import floatToFixedToFloat
from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.varLib.mvar import MVAR_ENTRIES
from fontTools.varLib.models import normalizeLocation, piecewiseLinearMap
from fontTools.varLib.varStore import NO_VARIATION_INDEX, VarStoreInstancer

# Typo line box. A non-zero range means the design already moves it.
LINE_BOX_TAGS = ("hasc", "hdsc", "hlgp")
# Win clipping box. A non-zero range means clipping is already adjusted.
CLIP_TAGS = ("hcla", "hcld")
# Measured heights. They follow the outlines; they are not a line-box edit.
MEASURE_TAGS = ("xhgt", "cpht")


def normalized_variation_location(
    varfont: TTFont, location_user: Mapping[str, float]
) -> dict[str, float]:
    """Normalize user-space coordinates (−1..1-ish) applying avar then F2Dot14 quantization."""
    fvar = varfont["fvar"]
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fvar.axes}
    loc = normalizeLocation(dict(location_user), axes)
    if "avar" in varfont:
        maps = varfont["avar"].segments
        loc = {k: piecewiseLinearMap(v, maps[k]) for k, v in loc.items()}
    return {k: floatToFixedToFloat(v, 14) for k, v in loc.items()}


def _ascii_tag(tag: object) -> str:
    if isinstance(tag, bytes):
        return tag.decode("latin-1")
    return str(tag)


def axis_pole_user_locations(varfont: TTFont) -> list[tuple[str, dict[str, float]]]:
    """Default + each axis pinned to min or max while others stay at fvar defaults."""
    fvar = varfont["fvar"]
    defaults = {a.axisTag: float(a.defaultValue) for a in fvar.axes}
    out: list[tuple[str, dict[str, float]]] = [
        ("default (axis default values)", dict(defaults))
    ]
    for a in fvar.axes:
        t = a.axisTag
        lo = dict(defaults)
        lo[t] = float(a.minValue)
        out.append((f"{t}=min · others default", lo))
        hi = dict(defaults)
        hi[t] = float(a.maxValue)
        out.append((f"{t}=max · others default", hi))
    return out


def mvar_delta_map(varfont: TTFont, loc_norm: dict[str, float]) -> dict[str, int]:
    """Rounded MVAR deltas at a normalized location (0 at defaults)."""
    mvar_tbl = varfont["MVAR"].table
    inst = VarStoreInstancer(mvar_tbl.VarStore, varfont["fvar"].axes, loc_norm)
    out: dict[str, int] = {}
    for rec in mvar_tbl.ValueRecord:
        tag = _ascii_tag(rec.ValueTag)
        vidx = rec.VarIdx
        if vidx == NO_VARIATION_INDEX:
            d = 0
        else:
            d = otRound(inst[vidx])
        out[tag] = int(d)
    return out


def mvar_aggregate_ranges(
    varfont: TTFont, samples: Sequence[tuple[str, dict[str, float]]]
) -> tuple[dict[str, tuple[int, int]], dict[str, str]]:
    """Per tag: (min_delta, max_delta) across samples; unknown tags tracked separately."""
    per_tag_vals: dict[str, list[int]] = {}
    unknown_tags: dict[str, str] = {}

    for _label, user_loc in samples:
        ln = normalized_variation_location(varfont, user_loc)
        snap = mvar_delta_map(varfont, ln)
        for tag, d in snap.items():
            per_tag_vals.setdefault(tag, []).append(int(d))
            if tag not in MVAR_ENTRIES:
                unknown_tags.setdefault(tag, "no OpenType registry mapping in FontTools")

    ranges: dict[str, tuple[int, int]] = {}
    for tag, vals in per_tag_vals.items():
        ranges[tag] = (min(vals), max(vals))
    return ranges, unknown_tags


def _moving(ranges: Mapping[str, tuple[int, int]], tags: Sequence[str]) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    for tag in tags:
        span = ranges.get(tag)
        if span is None or (span[0] == 0 and span[1] == 0):
            continue
        found.append((tag, span[0], span[1]))
    return found


def _span_text(moving: Sequence[tuple[str, int, int]]) -> str:
    return ", ".join(f"{tag} {lo:+d} to {hi:+d}" for tag, lo, hi in moving)


def _cmap_names(font: TTFont) -> list[str]:
    cmap = font.getBestCmap() or {}
    names = [name for name in cmap.values() if isinstance(name, str)]
    if names:
        return names
    return [name for name in font.getGlyphOrder() if name and name != ".notdef"]


def instance_y_bounds(
    font: TTFont, user_location: Mapping[str, float]
) -> Optional[tuple[int, int]]:
    """Cmap glyph ink at one user-space location: (yMin, yMax)."""
    try:
        glyph_set = font.getGlyphSet(location=dict(user_location))
    except Exception:
        return None
    from fontTools.pens.boundsPen import BoundsPen

    min_y: Optional[int] = None
    max_y: Optional[int] = None
    for name in _cmap_names(font):
        if name not in glyph_set:
            continue
        pen = BoundsPen(glyph_set)
        try:
            glyph_set[name].draw(pen)
        except Exception:
            continue
        if pen.bounds is None:
            continue
        _, y0, _, y1 = pen.bounds
        y0_i = int(otRound(y0))
        y1_i = int(otRound(y1))
        if min_y is None or y0_i < min_y:
            min_y = y0_i
        if max_y is None or y1_i > max_y:
            max_y = y1_i
    if min_y is None or max_y is None:
        return None
    return min_y, max_y


@dataclass
class PoleOverflow:
    label: str
    above: int
    below: int
    y_min: int
    y_max: int


@dataclass
class Survey:
    """One font, classified for the collection tally."""

    clipping: str
    line_box: str
    axes_line: str = ""
    line_box_text: str = ""
    clipping_text: str = ""
    upm: int = 0
    overflows: list[PoleOverflow] = field(default_factory=list)
    overflow_lines: list[str] = field(default_factory=list)
    verbose_lines: list[str] = field(default_factory=list)
    axes: list[tuple[str, float, float, float]] = field(default_factory=list)
    default_top: Optional[int] = None
    default_bottom: Optional[int] = None
    win_above: Optional[int] = None
    win_below: Optional[int] = None
    mvar_records: Optional[int] = None


def _past_default(
    pole: tuple[int, int],
    default: tuple[int, int],
    win_asc: int,
    win_desc: int,
) -> tuple[int, int]:
    """How far a pole sticks out past both the Win box and the default ink."""
    dmin, dmax = default
    pmin, pmax = pole
    above = pmax - max(win_asc, dmax)
    below = (-pmin) - max(win_desc, -dmin)
    return above, below


def _units_phrase(above: int, below: int) -> str:
    parts: list[str] = []
    if above > 0:
        parts.append(f"{above} above")
    if below > 0:
        parts.append(f"{below} below")
    return " and ".join(parts)


def survey_font(font: TTFont) -> Survey:
    """Classify a variable font. Static fonts (no fvar) get clipping 'static'."""
    if "fvar" not in font:
        return Survey(
            clipping="static",
            line_box="n/a",
            clipping_text="no fvar — static font",
        )

    fvar = font["fvar"]
    axes = [
        (a.axisTag, float(a.minValue), float(a.defaultValue), float(a.maxValue))
        for a in fvar.axes
    ]
    axes_line = ", ".join(
        f"{tag} {lo:g}…{default:g}…{hi:g}" for tag, lo, default, hi in axes
    )
    samples = axis_pole_user_locations(font)
    ranges: dict[str, tuple[int, int]] = {}
    unknown: dict[str, str] = {}
    if "MVAR" in font:
        ranges, unknown = mvar_aggregate_ranges(font, samples)

    line_moving = _moving(ranges, LINE_BOX_TAGS)
    if line_moving:
        opsz_hit = False
        for label, user_loc in samples:
            if not label.startswith("opsz="):
                continue
            snap = mvar_delta_map(font, normalized_variation_location(font, user_loc))
            if any(snap.get(tag, 0) != 0 for tag in LINE_BOX_TAGS):
                opsz_hit = True
                break
        where = "moves on an optical-size pole" if opsz_hit else "moves"
        line_box = "moves"
        line_box_text = f"{where} — {_span_text(line_moving)}; leave it"
    else:
        line_box = "flat"
        line_box_text = "flat"

    clip_moving = _moving(ranges, CLIP_TAGS)
    verbose_lines: list[str] = []
    mvar_records = (
        len(font["MVAR"].table.ValueRecord) if "MVAR" in font else None
    )
    measure_moving = _moving(ranges, MEASURE_TAGS)
    if measure_moving:
        verbose_lines.append(f"measured tags: {_span_text(measure_moving)}")
    if unknown:
        verbose_lines.append(f"unknown MVAR tags: {len(unknown)}")

    os2 = font["OS/2"] if "OS/2" in font else None
    if os2 is None:
        return Survey(
            clipping="unmeasured",
            line_box=line_box,
            axes_line=axes_line,
            line_box_text=line_box_text,
            clipping_text="no OS/2 table, so Win ascent and descent cannot be compared",
            verbose_lines=verbose_lines,
        )

    win_asc = int(getattr(os2, "usWinAscent", 0) or 0)
    win_desc = int(getattr(os2, "usWinDescent", 0) or 0)
    upm = int(font["head"].unitsPerEm)
    default_bounds = instance_y_bounds(font, samples[0][1])
    if default_bounds is None:
        return Survey(
            clipping="unmeasured",
            line_box=line_box,
            axes_line=axes_line,
            line_box_text=line_box_text,
            clipping_text="could not measure the default instance",
            verbose_lines=verbose_lines,
        )

    overflows: list[PoleOverflow] = []
    for label, user_loc in samples[1:]:
        bounds = instance_y_bounds(font, user_loc)
        if bounds is None:
            continue
        above, below = _past_default(bounds, default_bounds, win_asc, win_desc)
        if above > 0 or below > 0:
            overflows.append(
                PoleOverflow(label, above, below, bounds[0], bounds[1])
            )

    dmin, dmax = default_bounds
    default_above = dmax - win_asc
    default_below = (-dmin) - win_desc

    if clip_moving:
        clipping = "already-varies"
        clipping_text = f"already varies — {_span_text(clip_moving)}; leave it"
    elif overflows:
        clipping = "variable-overflow"
        clipping_text = f"variable overflow at {len(overflows)} pole(s)"
    else:
        clipping = "no-variable-overflow"
        if default_above > 0 or default_below > 0:
            clipping_text = (
                "no variable overflow — default ink exceeds Win by "
                f"{_units_phrase(max(default_above, 0), max(default_below, 0))}; "
                "poles do not go further"
            )
        else:
            clipping_text = "no variable overflow"

    kept_overflows = [] if clip_moving else list(overflows)
    overflow_lines = [
        _pole_sentence(
            item,
            upm=upm,
            win_above=win_asc,
            win_below=win_desc,
            default_top=dmax,
            default_bottom=dmin,
        )
        for item in kept_overflows
    ]
    if clip_moving and overflows:
        verbose_lines.append(
            "Some slider ends stick out, and the clipping box is already set to change with them."
        )
    for label, user_loc in samples:
        if "MVAR" not in font:
            break
        snap = mvar_delta_map(font, normalized_variation_location(font, user_loc))
        nonzero = [f"{tag}={value:+d}" for tag, value in sorted(snap.items()) if value != 0]
        if nonzero:
            verbose_lines.append(f"{label}: {', '.join(nonzero)}")

    return Survey(
        clipping=clipping,
        line_box=line_box,
        axes_line=axes_line,
        line_box_text=line_box_text,
        clipping_text=clipping_text,
        upm=upm,
        overflows=kept_overflows if clipping == "variable-overflow" else [],
        overflow_lines=overflow_lines,
        verbose_lines=verbose_lines,
        axes=axes,
        default_top=dmax,
        default_bottom=dmin,
        win_above=win_asc,
        win_below=win_desc,
        mvar_records=mvar_records,
    )


_POLE_NAMES = {
    ("wght", "max"): "heaviest weight",
    ("wght", "min"): "lightest weight",
    ("wdth", "max"): "widest",
    ("wdth", "min"): "narrowest",
    ("opsz", "max"): "largest optical size",
    ("opsz", "min"): "smallest optical size",
    ("slnt", "max"): "most slant",
    ("slnt", "min"): "least slant",
    ("ital", "max"): "italic end",
    ("ital", "min"): "roman end",
}


def _pole_sentence(
    item: PoleOverflow,
    *,
    upm: int,
    win_above: int,
    win_below: int,
    default_top: int,
    default_bottom: int,
) -> str:
    """What one slider end does to the outlines, in designer terms."""
    where = _pole_name(item.label)
    parts = [
        f"At the {where}, the outlines reach {item.y_max} above the baseline "
        f"and {abs(item.y_min)} below it."
    ]
    if item.above > 0:
        parts.append(
            f"{item.above} units stick out above the clipping box, "
            f"which stops at {win_above}."
        )
    if item.below > 0:
        parts.append(
            f"{item.below} units stick out below the clipping box, "
            f"which stops at {win_below}."
        )
    parts.append(
        f"The default style, before any slider is moved, reaches {default_top} above "
        f"and {abs(default_bottom)} below, so this only shows up at that end of the slider."
    )
    pct = _hang_percent(item, upm)
    parts.append(f"The em is {upm} units, so the hang is {_percent_text(pct)} of the em.")
    return " ".join(parts)


def _axis_sentence(tag: str, lo: float, default: float, hi: float) -> str:
    titles = {
        "wght": "Weight",
        "wdth": "Width",
        "opsz": "Optical size",
        "slnt": "Slant",
        "ital": "Italic",
    }
    title = titles.get(tag, tag)
    if lo == default == hi:
        return f"{title} is fixed at {lo:g}."
    if lo == default:
        return f"{title} runs from {lo:g}, which is the default, to {hi:g}."
    if hi == default:
        return f"{title} runs from {lo:g} to {hi:g}, which is the default."
    return f"{title} runs from {lo:g} to {hi:g}. The default style sits at {default:g}."


def explain_survey(survey: Survey) -> list[str]:
    """Sentences for -vv. Each number says what it measures."""
    lines: list[str] = []
    if survey.clipping == "static":
        lines.append("This file has no sliders. There is nothing variable to check.")
        return lines
    if survey.axes:
        lines.append("Sliders: " + " ".join(_axis_sentence(*axis) for axis in survey.axes))
    if survey.line_box == "moves":
        lines.append(
            "Line spacing already changes as the sliders move, so that change was left as designed."
        )
    elif survey.line_box == "flat":
        lines.append("Line spacing stays the same wherever the sliders sit.")
    if survey.mvar_records is None:
        lines.append(
            "The font does not store a separate clipping box or line spacing for other slider positions. "
            "Every position uses the default style's boxes."
        )
    elif survey.clipping == "already-varies":
        lines.append(
            "The clipping box is already set to grow or shrink as the sliders move, so it was left alone."
        )
    else:
        lines.append(
            "The font stores other metric adjustments, and none of them move the clipping box."
        )
    if survey.default_top is not None and survey.win_above is not None:
        lines.append(
            f"At the default style, the outlines reach {survey.default_top} above the baseline "
            f"and {abs(survey.default_bottom or 0)} below it. "
            f"The clipping box, which is what keeps letters from being chopped, stops at "
            f"{survey.win_above} above and {survey.win_below} below."
        )
    if survey.overflow_lines:
        lines.extend(survey.overflow_lines)
    elif survey.clipping == "no-variable-overflow":
        lines.append("The ends of the sliders still fit inside that clipping box.")
    lines.extend(survey.verbose_lines)
    return lines


def _pole_name(label: str) -> str:
    head = label.split("·")[0].strip()
    tag, _, end = head.partition("=")
    end = end.strip()
    return _POLE_NAMES.get((tag, end), f"{tag} {end}".strip())


def _hang_percent(item: PoleOverflow, upm: int) -> float:
    if upm <= 0:
        return 0.0
    return max(item.above, item.below) / upm * 100.0


def _percent_text(pct: float) -> str:
    if pct >= 10:
        return f"{pct:.0f}%"
    return f"{pct:.1f}%"


def _of_em(units: int, upm: int) -> str:
    if upm <= 0:
        return f"{units} units"
    return _percent_text(abs(units) / upm * 100.0)


def metrics_brief(survey: Survey) -> str:
    """One line of the measurements a type designer can use. No call to action."""
    if survey.clipping == "static":
        return "Not a variable font."
    if survey.clipping == "error":
        return survey.clipping_text or "Could not read the font."
    if survey.clipping == "unmeasured" or survey.default_top is None or survey.win_above is None:
        return survey.clipping_text or "Could not measure the font."
    if survey.line_box == "moves":
        spacing = "Line spacing already changes across the sliders."
    else:
        spacing = "Line spacing stays the same across the sliders."
    outlines = (
        f"Outlines at the default style reach {_of_em(survey.default_top, survey.upm)} of the em "
        f"above the baseline and {_of_em(survey.default_bottom or 0, survey.upm)} below."
    )
    box = (
        f"Clipping box stops at {_of_em(survey.win_above, survey.upm)} above "
        f"and {_of_em(survey.win_below or 0, survey.upm)} below."
    )
    if survey.overflows:
        worst = max(survey.overflows, key=lambda item: max(item.above, item.below))
        ends = (
            f"At the {_pole_name(worst.label)}, outlines pass that box by "
            f"{_percent_text(_hang_percent(worst, survey.upm))} of the em."
        )
    else:
        ends = "Slider ends stay inside the clipping box."
    return f"Em {survey.upm}. {spacing} {outlines} {box} {ends}"


REPORT_COLUMNS = (
    "path",
    "em",
    "sliders",
    "line_spacing",
    "outlines",
    "clipping_box",
    "slider_ends",
)


def load_survey(path: str) -> Survey:
    """Open one font and classify it. Does not print."""
    try:
        font = TTFont(str(path))
    except Exception as e:
        return Survey(clipping="error", line_box="n/a", clipping_text=str(e))
    try:
        return survey_font(font)
    except Exception as e:
        return Survey(clipping="error", line_box="n/a", clipping_text=str(e))
    finally:
        font.close()


def report_row(path: str, survey: Survey) -> list[str]:
    sliders = " ".join(_axis_sentence(*axis) for axis in survey.axes)
    if survey.line_box == "moves":
        spacing = "changes with the sliders"
    elif survey.line_box == "flat":
        spacing = "stays the same"
    else:
        spacing = ""
    if survey.default_top is None or survey.win_above is None:
        outlines = ""
        box = ""
        ends = survey.clipping_text
    else:
        outlines = (
            f"{_of_em(survey.default_top, survey.upm)} above, "
            f"{_of_em(survey.default_bottom or 0, survey.upm)} below"
        )
        box = (
            f"{_of_em(survey.win_above, survey.upm)} above, "
            f"{_of_em(survey.win_below or 0, survey.upm)} below"
        )
        if survey.overflows:
            worst = max(survey.overflows, key=lambda item: max(item.above, item.below))
            ends = (
                f"{_pole_name(worst.label)} passes the box by "
                f"{_percent_text(_hang_percent(worst, survey.upm))} of the em"
            )
        else:
            ends = "stay inside the box"
    return [path, str(survey.upm or ""), sliders, spacing, outlines, box, ends]


def probe_root(source_paths: Sequence[str]) -> Path:
    """Directory a relative report belongs in: the folder that was probed."""
    if not source_paths:
        return Path.cwd()
    roots: list[Path] = []
    for raw in source_paths:
        path = Path(raw).expanduser().resolve()
        roots.append(path if path.is_dir() else path.parent)
    if len(roots) == 1:
        return roots[0]
    try:
        return Path(os.path.commonpath([str(root) for root in roots]))
    except ValueError:
        return roots[0]


def report_destination(output: str, source_paths: Sequence[str]) -> str:
    """Absolute report path. Relative names sit at the top of the probed directory."""
    path = Path(output).expanduser()
    if path.is_absolute():
        return str(path)
    return str(probe_root(source_paths) / path)


def open_report(path: str) -> tuple[TextIO, csv.writer]:
    """Create a tab-separated report and write the header. Caller closes the file."""
    handle = open(path, "w", newline="", encoding="utf-8")
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(REPORT_COLUMNS)
    handle.flush()
    return handle, writer
