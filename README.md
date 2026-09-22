# ebrium

**Version 3.2.0**

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
ebrium family /path/to/fonts -r
# or
python -m ebrium family /path/to/fonts -r
```

## Usage

`ebrium` is subcommand-first: you pick how fonts are grouped, and that
choice determines which other flags apply. There's no default subcommand —
picking one is the point, not an afterthought.

```bash
# Group by family name, cluster within each family (most common case)
ebrium family /path/to/fonts -r

# Preview without writing
ebrium family /path/to/fonts -r -n

# Skip confirmation
ebrium family /path/to/fonts -r -y

# Detailed impact report (implies dry-run)
ebrium family /path/to/fonts -r --report

# Normalize each font on its own, no grouping at all
ebrium individual /path/to/fonts -r

# Merge families that share a name prefix
ebrium superfamily /path/to/fonts -r

# Read-only MVAR/HVAR coverage report; no grouping, measuring, or writing
ebrium probe /path/to/fonts -r
```

Full flag reference for any subcommand: `ebrium <subcommand> --help`.

## Subcommands

Earlier versions put every flag at the top level and warned at runtime when
one didn't apply to the mode you'd chosen (`--exclude` only works with
superfamily, `--line-box` does nothing under individual, and so on). That
information already existed as branches in the code — `grouping.py` and
`planning.py` both switch on the grouping strategy as their first decision.
The parser now matches that shape: each subcommand only defines the flags
that do something for it, so an invalid combination
(`ebrium individual fonts/ --exclude X`) is an ordinary argparse error
instead of a warning you might not notice.

| Subcommand | What it does | Flags beyond input/preview/spacing/detection |
|---|---|---|
| `individual` | Normalize each font on its own; no grouping, no clustering | *(none — see below)* |
| `family` | Group by family name, cluster within each family | `--safe-max`, `--combine`, `--ignore-term`, `--line-box*`, `--report` |
| `superfamily` | Merge families sharing a name prefix, cluster across the merge | `--combine`, `--ignore-term`, `--exclude`, `--line-box*`, `--report` |
| `probe` | Read-only MVAR/HVAR coverage report | *(none — just input + `-v`)* |

`probe` used to be a `--probe-variation-metrics` flag. It never touched
grouping, measurement, or config — `variation_probe.py` is fully
self-contained — so it was always a separate tool wearing a flag; it's a
subcommand now because that's what it actually is.

### Shared across `individual` / `family` / `superfamily`

**Input:** `paths` (font files or directories; default: current directory), `-r, --recursive`, `--use-ttx`

**Preview and confirmation:** `-n, --dry-run`, `-y, --yes` (`probe` has neither — it never writes and never prompts)

**Vertical spacing (% of UPM):**

| Flag | Meaning |
|------|---------|
| `-l, --letter-height PERCENT` | Target letter span (default: 130); a **floor**, not a fixed value — auto-adjust may raise it for large x-heights (use `--no-auto-adjust` for exactly what you typed) |
| `-t, --top-margin PERCENT` | Extra space above capitals (default: 25); ignored when a font's actual ascenders already clear it by a wide margin |
| `--no-auto-adjust` | Use exactly `--letter-height` (skip the x-height adjustment) |

**Detection overrides (filename globs, repeatable):** `-a, --assume TYPE:PATTERN` where TYPE is `script`, `decorative`, `unicase`, or `uniwidth` (e.g. `-a script:'*Swash*'`); plus `--exclude-measuring PATTERN` (excludes from family calculations rather than classifying — kept separate on purpose).

**General:** `-h, --help`, `--version`, `-v / -vv` (`probe`: `-v` shows per-pole deltas; repeating has no extra effect)

### `family` only

| Flag | Meaning |
|------|---------|
| `--safe-max` | bbox extremes for every font in the family instead of clustering (prevents clipping) |

### `family` and `superfamily`

| Flag | Meaning |
|------|---------|
| `--max-adjustment PERCENT` | Cap how far family extremes may pull a font (omitted under `individual` — no multi-font pull to cap) |
| `-c, --combine "A,B"` | Merge one group per flag, comma-separated **inside** the flag (repeat `--combine` for separate groups — `-c A -c B` does **not** merge A with B) |
| `-i, --ignore-term TERM` | Drop a whole word from family names before grouping, case-sensitive, wherever it appears (repeatable, or comma-separated in one flag) |
| `-e, --exclude FAMILY` | Keep a family out of the merge (**`superfamily` only**, repeatable) |

**Report:** `--report` — family vs per-font analysis (implies `--dry-run`)

**Line box (typo / hhea):** one flag, four choices — `--force-baseline`,
`--safe-hhea` and `--force-baseline-main-cluster` used to be three separate
flags, but `--safe-hhea` always silently overrode `--force-baseline` at
runtime, and `--force-baseline-main-cluster` never meant anything on its own
(it only ever narrowed which font `--force-baseline` picks as its
reference). So they're one choice flag instead of three that can't be
freely combined, and it doesn't exist under `individual` at all (single-font
"families" have nothing to unify).

| `--line-box MODE` | Meaning |
|------|---------|
| `auto` | Each font keeps its own planned typo/hhea values (**default**) |
| `force-baseline` | Unify typo/hhea across the family using its largest-span style |
| `force-baseline-main-cluster` | Like `force-baseline`, but the reference comes only from the largest optical cluster |
| `safe-hhea` | Average existing typo/hhea across the family and apply uniformly |

Short form: `-b MODE`.

| Modifier | Meaning |
|------|---------|
| `--line-box-from PATH_OR_GLOB` | Pin the reference font (path, filename, or filename glob); implies `--line-box force-baseline` if `--line-box` is left at its default |

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
