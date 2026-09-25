# ebrium

**Version 3.2.2**

Normalize vertical metrics across a font family — same line box, no clipping — without changing `unitsPerEm` or glyph outlines.

Formerly **FontMetricsNormalizer**. The public name and CLI are **ebrium**.

Typical pipeline: naming cleanup ([FontNameID](https://github.com/andrewsipe/FontNameID)) → structural tidy ([FontFixer](https://github.com/andrewsipe/FontFixer)) → **ebrium**.

**Docs:** [Line box, reading a run, flags, and probe](https://www.andrewsipe.com/Ebrium/) · `ebrium --help`

## Install

Preferred: [pipx](https://pipx.pypa.io/) (isolated CLI, easy upgrades):

```bash
pipx install "git+https://github.com/andrewsipe/ebrium.git"
# later: pipx upgrade ebrium
```

Or from a clone: `pipx install .` / `pip install -e .`

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
3. **Inherits** that box for effect and script cuts, while Win covers their outlines  
4. **Applies** typo, hhea, a zero line gap, and `USE_TYPO_METRICS` when OS/2 version ≥ 4  

Optical sizes named Caption, Display, Subhead, or Small Text each keep their own box. A layered or color stack copies one box across every layer file.

For the line-box picture, how to read a run, every flag, and `probe`, use the [doc site](https://www.andrewsipe.com/Ebrium/).

## Related

- [FontFixer](https://github.com/andrewsipe/FontFixer) — OS/2, style, glyph, kern tidy-up  
- [FontNameID](https://github.com/andrewsipe/FontNameID) — name-table editing  
- [Changelog](CHANGELOG.md)
