"""Family grouping."""


import FontCore.core_console_styles as cs
from FontCore.core_console_styles import get_console
from FontCore.core_font_sorter import FontSorter, FontInfo

console = get_console()


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
    groups = sorter.apply_forced_groups(before, forced_groups or [])

    if getattr(args, "grouping_mode", "family") == "conservative":
        label = f"Found {cs.fmt_count(len(groups))} family group(s) (--no-cluster, no clustering)"
    else:
        label = f"Found {cs.fmt_count(len(groups))} family group(s)"
    cs.StatusIndicator("info").add_message(label).emit(console)
    _announce_matches(before, groups, forced_groups)

    path_to_measure = {fm.path: fm for fm in measures}
    return {
        group_name: [path_to_measure[fi.path] for fi in infos]
        for group_name, infos in groups.items()
    }
