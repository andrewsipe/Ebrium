# ebrium

**Version 4.1.0**

Normalize vertical metrics across a font family — one line box, outlines unchanged — without changing `unitsPerEm`. Text stays inside the box. A layer or swash may clip.

Formerly **FontMetricsNormalizer**. The public name and CLI are **ebrium**.

Typical pipeline: naming cleanup ([FontNameID](https://github.com/andrewsipe/FontNameID)) → structural tidy ([FontFixer](https://github.com/andrewsipe/FontFixer)) → **ebrium**.

**Docs:** [Line box, reading a run, flags, and probe](https://www.andrewsipe.com/Ebrium/) · `ebrium --help`

## Install

Preferred: [uv](https://docs.astral.sh/uv/) (isolated CLI, easy upgrades):

```bash
uv tool install "git+https://github.com/andrewsipe/Ebrium.git"
# later: uv tool upgrade ebrium
```

From a clone: `uv tool install --editable .` (edits take effect immediately).

Requires Python 3.9+. Formats: TTF, OTF, WOFF, WOFF2 (`.ttx` with `--use-ttx`).

Tests: `python -m unittest discover -s tests`

## Quick start

One command. Fonts are grouped by family name.

```bash
# Default: one centered line box per family
ebrium /path/to/fonts -r -n

# Outline extremes, so nothing clips
ebrium /path/to/fonts -r --no-cluster

# One box for two family names that do not already group
ebrium /path/to/fonts -r --match "Family A,Family B"

# Read-only metrics
ebrium probe /path/to/fonts -r
```

Variable fonts are included at the default instance. `probe` does not write fonts. `-o` writes the table rows.

By default, matching fonts are **modified in place** (no backup). Use `-n` first. `probe` only reads.

## What it does (in short)

1. **Measures** cap height, x-height, ascenders, descenders, accented capitals, and bounds  
2. **Shares** one centered line box across the core styles in a family  
3. **Inherits** that box for a layer, swash, or script, while a color font with a color table copies one box across its files  
4. **Applies** typo, hhea, a zero line gap, and `USE_TYPO_METRICS` when OS/2 version ≥ 4  

The family name is the group. Two names share a box with `--match`. Style words such as Caption or Display do not split the group.

For the line-box picture, how to read a run, every flag, and `probe`, use the [doc site](https://www.andrewsipe.com/Ebrium/).

## Related

- [FontFixer](https://github.com/andrewsipe/FontFixer) — OS/2, style, glyph, kern tidy-up  
- [FontNameID](https://github.com/andrewsipe/FontNameID) — name-table editing  
- [Changelog](CHANGELOG.md)
