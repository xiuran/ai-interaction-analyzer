# providers/ — Modular Refactor (WIP)

This directory is a work-in-progress modular refactor of the data loading logic.

**Current status: NOT used.** The main entry point `scripts/analyzer.py` contains all provider logic inline and does NOT import from this directory.

If you're contributing, please edit `scripts/analyzer.py` directly — it is the source of truth.

This directory will be integrated in a future version to replace the inline loaders in `analyzer.py`.
