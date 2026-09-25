"""Split a peer group when it contains more than one optical size.

Default stays one pinned box. A second box is planned only when name tokens
show distinct sizes (Caption vs Display, and so on). Effect cuts are not
optical sizes — Display here means the optical-size word, not a style name
like Bold Display unless other sizes are present too, and then it is still
just a label, not a new algorithm.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import FontMeasures

# Longest phrases first so "small text" wins over "text".
_OPSZ_PHRASES: Tuple[Tuple[str, str], ...] = (
    ("small text", "Small Text"),
    ("smalltext", "Small Text"),
    ("caption", "Caption"),
    ("display", "Display"),
    ("subhead", "Subhead"),
    ("titling", "Titling"),
    ("poster", "Poster"),
    ("banner", "Banner"),
    ("micro", "Micro"),
    ("deck", "Deck"),
)


def _search_blob(fm: FontMeasures) -> str:
    stem = Path(fm.path).stem
    spaced = re.sub(r"(\d)([A-Za-z])", r"\1 \2", stem)
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", spaced)
    blob = f"{fm.family_name} {spaced}"
    return blob.lower().replace("-", " ").replace("_", " ")


def optical_size_label(fm: FontMeasures) -> Optional[str]:
    """Named optical size, or None when the font doesn't declare one."""
    blob = _search_blob(fm)
    for needle, label in _OPSZ_PHRASES:
        if needle in blob:
            return label
    if re.search(r"\btext\b", blob):
        return "Text"
    return None


def split_optical_size_groups(
    group: List[FontMeasures],
) -> List[Tuple[str, List[FontMeasures]]]:
    """Return one bucket, or several when the peer set mixes optical sizes.

    Unlabeled styles become ``Text`` only when another named size is present.
    A single size (or none) returns ``[("default", group)]`` so planning stays
    one pinned box.
    """
    if len(group) < 2:
        return [("default", group)]

    labeled = [(optical_size_label(fm), fm) for fm in group]
    named = {lab for lab, _fm in labeled if lab}
    if not named:
        return [("default", group)]

    buckets: dict[str, List[FontMeasures]] = {}
    for lab, fm in labeled:
        buckets.setdefault(lab or "Text", []).append(fm)

    if len(buckets) < 2:
        return [("default", group)]

    return list(buckets.items())


def expand_optical_size_groups(
    families: dict[str, List[FontMeasures]],
) -> dict[str, List[FontMeasures]]:
    """Rename mixed optical-size groups so each planned box has its own key.

    ``build_plans`` reports those names. The change summary looks families up
    by the same key, so the split has to happen before that lookup.
    """
    expanded: dict[str, List[FontMeasures]] = {}
    for fam, group in families.items():
        subgroups = split_optical_size_groups(group)
        if len(subgroups) < 2:
            expanded[fam] = group
            continue
        for label, fonts in subgroups:
            expanded[f"{fam} · {label}"] = fonts
    return expanded
