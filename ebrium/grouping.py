"""Family grouping."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import FontCore.core_console_styles as cs
from FontCore.core_console_styles import _escape_markup, get_console
from FontCore.core_font_sorter import FontSorter, FontInfo

console = get_console()

_CAMEL_BOUNDARY = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


@dataclass(frozen=True)
class MatchSpec:
    """One --match flag.

    A comma is an exact list of family names. Anything else is a key matched
    against the family name and the filename.
    """

    raw: str
    names: tuple[str, ...] = ()

    @property
    def is_key(self) -> bool:
        return not self.names


def _compact_name(name: str) -> str:
    """Family name with spaces and punctuation removed, for filename forms."""
    return re.sub(r"[^0-9a-z]+", "", name.casefold())


def _words(text: str) -> list[str]:
    """Words in a family name or filename. ExtraTall is Extra and Tall."""
    spaced = _CAMEL_BOUNDARY.sub(" ", text)
    return [part.casefold() for part in re.split(r"[^0-9A-Za-z]+", spaced) if part]


def _contains_words(text: str, key_words: list[str]) -> bool:
    words = _words(text)
    count = len(key_words)
    if count == 0 or len(words) < count:
        return False
    if count == 1:
        return key_words[0] in words
    return any(words[index : index + count] == key_words for index in range(len(words) - count + 1))


def _file_matches_key(family_name: str, path: str, key: str) -> bool:
    key_words = _words(key)
    stem = Path(path).stem
    return _contains_words(family_name or "", key_words) or _contains_words(stem, key_words)


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


def parse_matched_groups(args) -> list[MatchSpec]:
    """One spec per --match, in the order they were written.

    A comma joins family names. No comma means the text is a key.
    """
    specs: list[MatchSpec] = []
    for group_str in getattr(args, "combine", None) or []:
        text = group_str.strip()
        if not text:
            continue
        if "," in text:
            names = tuple(name.strip() for name in text.split(",") if name.strip())
            if len(names) < 2:
                cs.StatusIndicator("warning").add_message(
                    f'--match needs at least two family names when using a comma, skipping "{text}".'
                ).emit(console)
                continue
            specs.append(MatchSpec(text, names))
        else:
            specs.append(MatchSpec(text))
    return specs


def spec_covers_group(spec: MatchSpec, group_name: str) -> bool:
    """True when this flag produced a group of that name."""
    if spec.is_key:
        return group_name.casefold() == spec.raw.casefold()
    return _compact_name(group_name) in {_compact_name(name) for name in spec.names}


def _say(message: str) -> None:
    cs.StatusIndicator("info").add_message(message).emit(console)


def _warn(message: str) -> None:
    cs.StatusIndicator("warning").add_message(message).emit(console)


def _claim_label(label: str, existing: dict) -> str:
    if label not in existing:
        return label
    suffix = 2
    while f"{label} ({suffix})" in existing:
        suffix += 1
    return f"{label} ({suffix})"


def group_families(args, measures, specs: list[MatchSpec] | None):
    """Group fonts by family name.

    ``--no-cluster`` uses the same groups. Each ``--match`` then claims files,
    in order. A comma names families. A key matches the family name or filename.
    A file stays with the first flag that claims it.
    """
    font_infos = [
        FontInfo(path=fm.path, family_name=fm.family_name) for fm in measures
    ]
    before = FontSorter(font_infos).group_by_family()
    family_names = list(before.keys())
    claimed: set[str] = set()
    claimed_groups: list[tuple[str, list]] = []
    announcements: list[str] = []

    for spec in specs or []:
        if spec.names:
            found_names, missed = resolve_matched_names([list(spec.names)], family_names)
            for token in missed:
                _warn(f'--match "{_escape_markup(token)}" did not match a family name in this run.')
            names = found_names[0] if found_names else []
            pool = [fm for fm in measures if fm.family_name in names]
            label = names[0] if names else spec.raw
        else:
            pool = [
                fm
                for fm in measures
                if _file_matches_key(fm.family_name, fm.path, spec.raw)
            ]
            label = spec.raw

        fresh = [fm for fm in pool if fm.path not in claimed]
        lost = [fm for fm in pool if fm.path in claimed]
        if lost:
            _warn(
                f'{cs.fmt_count(len(lost))} file(s) already matched an earlier --match, '
                f'so "{_escape_markup(spec.raw)}" did not take them.'
            )
        if spec.names and len({fm.family_name for fm in fresh}) < 2:
            if not lost:
                _warn(
                    f'--match "{_escape_markup(spec.raw)}" needs two family names that are still available.'
                )
            continue
        if not fresh:
            if not lost:
                _warn(f'--match "{_escape_markup(spec.raw)}" did not match a file in this run.')
            continue

        for fm in fresh:
            claimed.add(fm.path)
        claimed_groups.append((label, fresh))
        joined = []
        for fm in fresh:
            if fm.family_name not in joined:
                joined.append(fm.family_name)
        shown = _escape_markup(label)
        if len(joined) > 1:
            others = ", ".join(_escape_markup(name) for name in joined if name != joined[0])
            announcements.append(f"Matched [field]{_escape_markup(joined[0])}[/field] with {others}")
        else:
            announcements.append(
                f'Matched {cs.fmt_count(len(fresh))} file(s) on "{shown}"'
            )

    groups: dict[str, list] = {}
    for name, infos in before.items():
        kept = [fi for fi in infos if fi.path not in claimed]
        if kept:
            groups[name] = kept
    path_to_measure = {fm.path: fm for fm in measures}
    result = {
        name: [path_to_measure[fi.path] for fi in infos]
        for name, infos in groups.items()
    }
    for label, fresh in claimed_groups:
        result[_claim_label(label, result)] = fresh

    if getattr(args, "grouping_mode", "family") == "conservative":
        label = f"Found {cs.fmt_count(len(result))} family group(s) (--no-cluster, no clustering)"
    else:
        label = f"Found {cs.fmt_count(len(result))} family group(s)"
    cs.StatusIndicator("info").add_message(label).emit(console)
    if announcements:
        cs.emit("", console=console)
        for line in announcements:
            _say(line)
    return result
