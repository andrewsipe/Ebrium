"""Layered-set stamping and the end-of-run review.

Layered/color stacks are a mechanical fix: every file in the set gets one
shared typo box and one shared Win box so the layers stay aligned.

The review does not change the plan. It lists facts the core run already
measured: missing accent samples, a span that had to exceed the floor,
cross-weight spread, and an x-height/cap-height ratio outside the usual band.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from collections.abc import Sequence

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console

from .config import MetricsConfig
from .models import FontMeasures

console = get_console()

# Cross-weight: a few percent of UPM. Low x/cap: outside a typical Latin text band.
CROSS_WEIGHT_SPREAD = 0.03
X_CAP_LOW = 0.65
X_CAP_HIGH = 0.78

_LAYER_TOKENS = frozenset({"layer", "layers", "color"})
_COLOR_TABLES = ("COLR", "SVG ", "CBDT", "sbix")


def font_has_color_table(font) -> bool:
    return any(tag in font for tag in _COLOR_TABLES)


def _tokens(fm: FontMeasures) -> list[str]:
    stem = Path(fm.path).stem
    blob = f"{fm.family_name} {stem}"
    parts = re.split(r"[-_ ]+", blob)
    tokens: list[str] = []
    for part in parts:
        tokens.extend(
            re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", part)
        )
    return [t.lower() for t in tokens if t]


def _named_layer(fm: FontMeasures) -> bool:
    return bool(_LAYER_TOKENS.intersection(_tokens(fm)))


def is_layered_set(group: Sequence[FontMeasures]) -> bool:
    """True when every file in a multi-file group is a color font or a named layer."""
    if len(group) < 2:
        return False
    if all(fm.is_color_font for fm in group):
        return True
    return all(_named_layer(fm) for fm in group)


def stamp_layered_metrics(group: Sequence[FontMeasures], config: MetricsConfig) -> bool:
    """Give every layer the same typo and Win, covering the union of outlines.

    Returns True when the group was a layered set and was stamped.
    """
    if not is_layered_set(group):
        return False

    usable = [fm for fm in group if fm.upm > 0 and fm.target_typo_asc is not None]
    if len(usable) < 2:
        return False

    asc_n = max(fm.target_typo_asc / fm.upm for fm in usable)
    desc_n = min((fm.target_typo_desc or 0) / fm.upm for fm in usable)
    ymaxs = [fm.max_y / fm.upm for fm in usable if fm.max_y is not None]
    ymins = [fm.min_y / fm.upm for fm in usable if fm.min_y is not None]
    ymax_n = max(ymaxs) if ymaxs else asc_n
    ymin_n = min(ymins) if ymins else desc_n

    for fm in group:
        if fm.upm <= 0:
            continue
        fm.target_typo_asc = int(round(asc_n * fm.upm))
        fm.target_typo_desc = int(round(desc_n * fm.upm))
        fm.target_win_asc = int(round(max(ymax_n * fm.upm * (1.0 + config.win_buffer), 0)))
        fm.target_win_desc = int(round(abs(ymin_n * fm.upm) * (1.0 + config.win_buffer)))
        fm.is_layered = True
        from .planning import finalize_metrics

        finalize_metrics(fm)
    return True


def _core_fonts(group: Sequence[FontMeasures]) -> list[FontMeasures]:
    core = [
        fm
        for fm in group
        if not fm.is_decorative_outlier and not fm.is_script
    ]
    return core or list(group)


def _spread(values: list[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    return max(values) - min(values)


def _peel_notes(group: Sequence[FontMeasures], config: MetricsConfig) -> list[str]:
    """How much a peel changed the shared line box, as a percent of the em."""
    from .planning import planned_typo_norm

    core = [
        fm
        for fm in group
        if not fm.is_decorative_outlier and not fm.is_script and fm.upm > 0
    ]
    peeled = [fm for fm in group if fm.is_decorative_outlier or fm.is_script]
    if not core or not peeled:
        return []
    actual = planned_typo_norm(core, config)
    if actual is None:
        return []
    actual_span = actual[0] + abs(actual[1])
    notes: list[str] = []
    for fm in peeled:
        stayed = planned_typo_norm([*core, fm], config)
        if stayed is None:
            continue
        delta = abs((stayed[0] + abs(stayed[1])) - actual_span)
        if fm.is_script:
            kind = "script"
        elif fm.is_unicase:
            kind = "unicase"
        else:
            kind = "decorative"
        notes.append(
            f"{Path(fm.path).name} left the shared box as {kind}. "
            f"Keeping it in would have changed the line box by {delta * 100:.1f}% of the em."
        )
    return notes


def review_notes(
    group: Sequence[FontMeasures], config: Optional[MetricsConfig] = None
) -> list[str]:
    """Facts to surface. Empty when nothing in this group needs a look."""
    config = config or MetricsConfig()
    notes: list[str] = []
    if any(fm.is_layered for fm in group):
        notes.append(
            f"Layered set: one shared typo and Win across {len(group)} file(s)"
        )

    core = _core_fonts(group)
    if any(fm.accented_cap_missing for fm in core):
        notes.append(
            "No accented-capital sample — re-check when extended Latin is added"
        )
    if any(fm.span_exceeded_target for fm in group):
        notes.append(
            "Typo span exceeds the letter-height floor to clear measured outlines"
        )

    caps = [fm.cap_optical / fm.upm for fm in core if fm.cap_optical and fm.upm > 0]
    xs = [fm.x_height / fm.upm for fm in core if fm.x_height and fm.upm > 0]
    accents = [
        fm.accented_cap_max / fm.upm
        for fm in core
        if fm.accented_cap_max and fm.upm > 0
    ]
    for label, values in (
        ("cap height", caps),
        ("x-height", xs),
        ("accented-cap height", accents),
    ):
        spread = _spread(values)
        if spread is not None and spread > CROSS_WEIGHT_SPREAD:
            notes.append(
                f"Cross-weight spread: {label} varies {spread * 100:.1f}% of UPM "
                f"across core styles (threshold {CROSS_WEIGHT_SPREAD * 100:.0f}%)"
            )

    ratios = [
        fm.x_height / fm.cap_optical
        for fm in core
        if fm.x_height and fm.cap_optical and fm.cap_optical > 0
    ]
    if ratios:
        ratios.sort()
        mid = ratios[len(ratios) // 2]
        if mid < X_CAP_LOW or mid > X_CAP_HIGH:
            notes.append(
                f"x-height/cap-height is {mid:.2f}, outside {X_CAP_LOW:.2f}–{X_CAP_HIGH:.2f}. "
                "Cap-centering may not suit this file; consider x-height or a midpoint"
            )
    notes.extend(_peel_notes(group, config))
    return notes


def emit_review(notes_by_family: dict[str, list[str]]) -> None:
    """Print the accumulated review once, after planning."""
    flagged = {fam: notes for fam, notes in notes_by_family.items() if notes}
    if not flagged:
        return
    cs.emit("", console=console)
    for fam, notes in flagged.items():
        indicator = cs.StatusIndicator("info").add_message(
            f"[field]Review:[/field] '{fam}'"
        )
        for note in notes:
            indicator.add_item(note, indent_level=1)
        indicator.emit(console)
