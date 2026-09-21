# Vendored FontCore subset

ebrium ships a minimal copy of FontCore so it installs without the full
library or a git submodule.

## Included modules

- `core_cli_help.py` — shared Rich `--help` building blocks (panel, footer sections)
- `core_file_collector.py` — font path collection
- `core_font_sorter.py` — family / superfamily grouping helpers
- `core_console_styles.py` — console UX formatting
- `core_console_config.py` — theme / labels / Rich setup
- `core_logging_config.py` — logging helpers / Verbosity

## Refresh from monorepo FontCore

From the Good Font Scripts monorepo root:

```bash
cp FontCore/core_cli_help.py \
   FontCore/core_file_collector.py \
   FontCore/core_font_sorter.py \
   FontCore/core_console_styles.py \
   FontCore/core_console_config.py \
   FontCore/core_logging_config.py \
   ebrium/FontCore/
```

Re-copy when console, collector, sorter, or CLI help APIs change in a way ebrium relies on.
This tree is owned by ebrium; it is not kept in live sync with FontCore.
