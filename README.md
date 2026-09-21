# ebrium

**Version 2.1.0**

Normalize vertical metrics across a font family without changing unitsPerEm or glyph outlines.

Formerly developed as **FontMetricsNormalizer**; the public name and CLI are **ebrium**.

Typical pipeline: after naming cleanup ([FontNameID](https://github.com/andrewsipe/FontNameID)) and structural tidy-ups ([FontFixer](https://github.com/andrewsipe/FontFixer)).

## Strategy

- Cap height is the stable anchor for identifying optically identical fonts
- Family-wide Win metrics prevent clipping using normalized extremes
- Core cluster gets identical typo/hhea metrics (normalized across UPMs)
- Decorative outliers inherit typo metrics but expand win bounds
- Line gaps set to zero across typo and hhea
- `USE_TYPO_METRICS` enabled when OS/2 version ≥ 4

## Installation

```bash
# from GitHub
pip install "git+https://github.com/andrewsipe/ebrium.git"

# from zip
pip install https://github.com/andrewsipe/ebrium/archive/refs/heads/main.zip

# from a clone
cd ebrium && pip install .
# or editable: pip install -e .
```

Then:

```bash
ebrium /path/to/fonts -r
# or
python -m ebrium /path/to/fonts -r
```

## Usage

```bash
# Normalize a directory (recursive)
ebrium /path/to/fonts -r

# Preview without writing
ebrium /path/to/fonts -r -n

# Skip confirmation
ebrium /path/to/fonts -r -y

# Detailed impact report (implies dry-run)
ebrium /path/to/fonts -r --report
```

## Command-line options

### Basics

| Flag | Meaning |
|------|---------|
| `paths` | Font files or directories (default: current directory) |
| `-r, --recursive` | Recurse into directories |
| `-n, --dry-run` | Preview without writing |
| `-y, --yes` | Skip confirmation |
| `-v / -vv` | Verbose / debug |
| `--use-ttx` | Include `.ttx` files |
| `--report` | Family vs per-font analysis (implies dry-run) |
| `--probe-variation-metrics` | Read-only MVAR/HVAR probe (no measure/write) |

### Vertical spacing (% of UPM)

| Flag | Meaning |
|------|---------|
| `--letter-height PERCENT` | Target letter span (default: 130) |
| `--top-margin PERCENT` | Extra space above capitals (default: 25) |
| `--max-adjustment PERCENT` | Cap how far family extremes may pull a font |
| `--no-auto-adjust` | Use exact `--letter-height` (no x-height tweak) |

### Grouping mode

One flag, four choices — `--safe-max` was never a fifth independent mode; it's
always plain family grouping with clustering turned off, so it reads as a
variant of `--grouping family`.

| `--grouping MODE` | Meaning |
|------|---------|
| `family` | Group by family name, cluster within families (**default**) |
| `family-safe-max` | Group by family; bbox extremes for every font, no clustering (prevents clipping) |
| `superfamily` | Merge shared-prefix families, cluster across the superfamily |
| `individual` | Normalize each font alone (no grouping/clustering) |

### Grouping modifiers

| Flag | Meaning |
|------|---------|
| `--combine "A,B"` | Force-merge families (repeatable) |
| `--ignore-prefix TOKEN` | Ignore token when normalizing names (repeatable) |
| `--exclude NAME` | Keep family out of superfamily merges (`--grouping superfamily` only, repeatable) |

### Line box (typo / hhea)

One flag, four choices — `--force-baseline`, `--safe-hhea` and
`--force-baseline-main-cluster` used to be three separate flags, but
`--safe-hhea` always silently overrode `--force-baseline` at runtime, and
`--force-baseline-main-cluster` never meant anything on its own (it only
ever narrowed which font `--force-baseline` picks as its reference — the
same relationship `--safe-max` has to `--grouping family`). So they're now
one choice flag instead of three flags that can't be freely combined.

| `--line-box MODE` | Meaning |
|------|---------|
| `auto` | Each font keeps its own planned typo/hhea values (**default**) |
| `force-baseline` | Unify typo/hhea across the family using its largest-span style |
| `force-baseline-main-cluster` | Like `force-baseline`, but the reference comes only from the largest optical cluster |
| `safe-hhea` | Average existing typo/hhea across the family and apply uniformly |

| Modifier | Meaning |
|------|---------|
| `--line-box-from PATH_OR_GLOB` | Pin the reference font (path, filename, or filename glob); implies `--line-box force-baseline` if `--line-box` is left at its default |

### Detection overrides (glob patterns, repeatable)

`--assume-script`, `--assume-decorative`, `--assume-unicase`, `--assume-uniwidth`, `--exclude-measuring`

## How it works

1. **Measure** — cap height, x-height, ascenders, descenders, bounds  
2. **Cluster** — optically identical fonts via cap height  
3. **Plan** — normalized metrics from family/cluster analysis  
4. **Apply** — write metrics to font files  

Checkpoints (`.metrics_checkpoint.json`) cache measurements and clusters; they invalidate when config or the font set changes.

## Supported formats

TTF, OTF, WOFF, WOFF2

## Dependencies

See `requirements.txt` (also declared in `pyproject.toml`):

- `fonttools>=4.40.0`
- `rich>=13.0.0`
- `brotli>=1.0.9` (WOFF2)

## Layout

```
ebrium/                 # this repo (https://github.com/andrewsipe/ebrium)
├── ebrium/             # Python package
├── FontCore/           # vendored slim FontCore subset (see FontCore/VENDOR.md)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Related tools

- [FontFixer](https://github.com/andrewsipe/FontFixer) — structural tidy-up (OS/2, style, glyph, kern)
- [FontNameID](https://github.com/andrewsipe/FontNameID) — name-table editing
