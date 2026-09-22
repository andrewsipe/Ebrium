# ebrium

**Version 3.2.2**

Normalize vertical metrics across a font family — same line box, no clipping — without changing `unitsPerEm` or glyph outlines.

Formerly **FontMetricsNormalizer**. The public name and CLI are **ebrium**.

Typical pipeline: naming cleanup ([FontNameID](https://github.com/andrewsipe/FontNameID)) → structural tidy ([FontFixer](https://github.com/andrewsipe/FontFixer)) → **ebrium**.

**Docs:** [Concepts, flags, and report lookup](https://andrewsipe.github.io/ebrium/) · full flag detail also in `ebrium <subcommand> --help`

## Install

Preferred: [pipx](https://pipx.pypa.io/) (isolated CLI, easy upgrades):

```bash
pipx install "git+https://github.com/andrewsipe/ebrium.git"
# later: pipx upgrade ebrium
```

Or from a clone: `pipx install .` / `pip install -e .`

Requires Python 3.9+. Formats: TTF, OTF, WOFF, WOFF2 (`.ttx` with `--use-ttx`).

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

# Variable fonts: MVAR/HVAR coverage only (no writes)
ebrium probe /path/to/fonts -r
```

By default, matching fonts are **modified in place** (no backup). Use `-n` or `--report` first.

## What it does (in short)

1. **Measures** cap height, x-height, ascenders, descenders, bounds  
2. **Clusters** optically similar styles (cap height as the stable anchor)  
3. **Plans** shared typo/hhea metrics and Win extremes that prevent clipping  
4. **Applies** those metrics to the fonts  

Decorative outliers can inherit typo metrics while expanding Win bounds. Line gaps go to zero; `USE_TYPO_METRICS` is set when OS/2 version ≥ 4.

For definitions, clustering logic, every flag, and how to read `--report`, use the [doc site](https://andrewsipe.github.io/ebrium/).

## Related

- [FontFixer](https://github.com/andrewsipe/FontFixer) — OS/2, style, glyph, kern tidy-up  
- [FontNameID](https://github.com/andrewsipe/FontNameID) — name-table editing  
- [Changelog](CHANGELOG.md)
