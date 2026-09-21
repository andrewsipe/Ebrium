# Product notes — ebrium

Standalone product tree for https://github.com/andrewsipe/ebrium

## Origin

Consolidated from monorepo `FontMetricsNormalizer/` (package was already named `ebrium`).
FontCore is vendored (console + collector + sorter); no submodule.

## Deferred (housekeeping pass)

1. CLI / `--help` polish (FontFixer-style groups, safety wording, Rich footer)
2. Tests / fixtures
3. Optional split of large `planning.py`
4. Archive or redirect old `FontMetricsNormalizer` GitHub remote when ready
5. Remove `FontMetricsNormalizer/` from monorepo + PushCore when leaving workspace
