# Measured disk-spill experiment

These two JSON files were produced by an actual execution of
`scripts/benchmark.py --spill-only --spill-memory 64MB --spill-rows 4000000`.
The run used the locally available Python 3.11 DuckDB installation. Source paths
inside the DuckDB profile identify that development run, not an installation
requirement. See `docs/verification.md` for environment details and limitations.

The sort consumed a bounded DuckDB buffer budget and demonstrably spilled to
disk. These measurements concern the sorting primitive only. No graph-size,
rendering-time or full-pipeline RAM claim follows from them.
