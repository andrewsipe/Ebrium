# ebrium

**Version 3.2.2**

Normalize vertical metrics across a font family — same line box, no clipping — without changing `unitsPerEm` or glyph outlines.

Formerly **FontMetricsNormalizer**. The public name and CLI are **ebrium**.

Typical pipeline: naming cleanup ([FontNameID](https://github.com/andrewsipe/FontNameID)) → structural tidy ([FontFixer](https://github.com/andrewsipe/FontFixer)) → **ebrium**.

**Docs:** [Line box, reading a run, flags, and report lookup](https://www.andrewsipe.com/Ebrium/) · full flag detail also in `ebrium <subcommand> --help`

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

Pick a subcommand — how fonts are grouped — then run. There is no default.

```bash
# Most common: group by family name, cluster within each family
ebrium family /path/to/fonts -r

# Preview only
ebrium family /path/to/fonts -r -n

# Skip confirmation
ebrium family /path/to/fonts -r -y

# Impact report (implies dry-run) — see docs for reading the output
ebrium family /path/to/fonts -r --report

# One font at a time (no family pull)
ebrium individual /path/to/fonts -r

# Merge families that share a name prefix
ebrium superfamily /path/to/fonts -r

# Variable fonts: these subcommands rewrite the default instance only.
# probe reports whether the line box already moves, and whether a flat Win
# box is overflowed at the axis poles. It does not write.
ebrium probe /path/to/variable-fonts -r

# A few files: em, line spacing, outlines, and the clipping box
ebrium probe /path/to/fonts

# The same facts, spelled out
ebrium probe /path/to/fonts -vv
```

By default, matching fonts are **modified in place** (no backup). Use `-n` or `--report` first.

## What it does (in short)

1. **Measures** cap height, x-height, ascenders, descenders, bounds  
2. **Clusters** optically similar styles (cap height as the stable anchor)  
3. **Plans** shared typo/hhea metrics and Win extremes that prevent clipping  
4. **Applies** those metrics to the fonts  

Decorative outliers can inherit typo metrics while expanding Win bounds. Line gaps go to zero; `USE_TYPO_METRICS` is set when OS/2 version ≥ 4.

For the line-box picture, how to read a run, clustering logic, every flag, and `--report`, use the [doc site](https://www.andrewsipe.com/Ebrium/).

## Related

- [FontFixer](https://github.com/andrewsipe/FontFixer) — OS/2, style, glyph, kern tidy-up  
- [FontNameID](https://github.com/andrewsipe/FontNameID) — name-table editing  
- [Changelog](CHANGELOG.md)
