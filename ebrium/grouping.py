"""Family grouping."""

from __future__ import annotations

import re

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console
from FontCore.core_font_sorter import FontSorter, FontInfo

console = get_console()


def _compact_name(name: str) -> str:
    """Family name with spaces and punctuation removed, for filename forms."""
    return re.sub(r"[^0-9a-z]+", "", name.casefold())


def resolve_matched_names(
    groups: list[list[str]], family_names: list[str] | set[str]
) -> tuple[list[list[str]], list[str]]:
    """Map --match tokens onto the family names in the run.

    ``FamilyShort`` matches the family ``Family Short``. A token that
    matches more than one family is left unmatched.
    """
    buckets: dict[str, list[str]] = {}
    names = list(family_names)
    for name in names:
        buckets.setdefault(_compact_name(name), []).append(name)

    resolved: list[list[str]] = []
    missed: list[str] = []
    for group in groups:
        found: list[str] = []
        for token in group:
            hits = buckets.get(_compact_name(token), [])
            if len(hits) == 1:
                if hits[0] not in found:
                    found.append(hits[0])
            elif token in names and token not in found:
                found.append(token)
            else:
                missed.append(token)
        resolved.append(found)
    return resolved, missed


def parse_matched_groups(args) -> list[list[str]]:
    """Family names from --match. Each flag is one group that shares a line box."""
    matched: list[list[str]] = []
    for group_str in getattr(args, "combine", None) or []:
        names = [name.strip() for name in group_str.split(",") if name.strip()]
        if len(names) < 2:
            cs.StatusIndicator("warning").add_message(
                f'--match needs at least two family names in one flag, skipping "{group_str}". '
                "Each --match is its own pair: -m A -m B does not match A with B."
            ).emit(console)
            continue
        matched.append(names)
    return matched


def _announce_matches(groups_before_keys, groups, forced_groups) -> None:
    """Say which family names actually landed in one group."""
    if not forced_groups:
        return
    present = set(groups_before_keys)
    lines = []
    for names in forced_groups:
        found = [name for name in names if name in present]
        if len(found) < 2:
            continue
        target = next((name for name in found if name in groups), found[0])
        others = [name for name in found if name != target]
        lines.append(f"Matched [field]{target}[/field] with {', '.join(others)}")
    if not lines:
        return
    cs.emit("", console=console)
    for line in lines:
        cs.StatusIndicator("info").add_message(line).emit(console)


def group_families(args, measures, forced_groups):
    """Group fonts by family name.

    ``--no-cluster`` uses the same groups. ``--match`` joins family names
    that should share one line box.
    """
    font_infos = [
        FontInfo(path=fm.path, family_name=fm.family_name) for fm in measures
    ]
    sorter = FontSorter(font_infos)
    before = sorter.group_by_family()
    resolved, missed = resolve_matched_names(forced_groups or [], before.keys())
    for token in missed:
        cs.StatusIndicator("warning").add_message(
            f'--match "{token}" did not match a family name in this run.'
        ).emit(console)
    groups = sorter.apply_forced_groups(before, resolved)

    if getattr(args, "grouping_mode", "family") == "conservative":
        label = f"Found {cs.fmt_count(len(groups))} family group(s) (--no-cluster, no clustering)"
    else:
        label = f"Found {cs.fmt_count(len(groups))} family group(s)"
    cs.StatusIndicator("info").add_message(label).emit(console)
    _announce_matches(before, groups, resolved)

    path_to_measure = {fm.path: fm for fm in measures}
    return {
        group_name: [path_to_measure[fi.path] for fi in infos]
        for group_name, infos in groups.items()
    }
