# Verification status

Status recorded on 2026-10-28. **Implementation is not yet fully validated.**

The repository contains the three visualization scripts, synthetic generator,
disk-backed preparation and exact quotient pipeline, native streaming detector,
optional CluStRE adapter, validation, order-sensitivity and benchmark runners,
fixtures, CI configuration and scientific documentation.

## Executed locally

| Check | Actual result |
| --- | --- |
| Ruff lint | Passed |
| Python syntax, project TOML and JSON configuration parsing | Passed |
| Standard-library runtime contract tests | 4 passed |
| Shared NumPy numerical contract tests | 6 passed |
| External sort with DuckDB budget 64 MB, 4,000,000 rows, one thread | Completed with verified disk spill |
| Complete dependency availability check | Failed: no single compatible scientific environment available |
| Full pytest suite | Not run: pytest and other dependencies unavailable |

The local-move numerical test evaluates 60 random graph/resolution combinations,
each over four passes, against an independent dense modularity definition. It
also checks community-volume conservation. Further tests cover batch boundaries,
block probabilities, matrix conventions, raster mass and ARI label invariance.
These tests exercise the shared function in Python. **They do not establish that
the Numba compilation and production I/O integration work.**

The measured external-sort experiment is archived in
[`examples/measurements/spill-report.json`](../examples/measurements/spill-report.json)
with the original DuckDB JSON profile. It used DuckDB 1.5.5, Python 3.11.15 and
psutil 7.2.2. The observed process RSS peak was 175,726,592 bytes, profiler spill
peak 293,863,424 bytes, and monitored wall time about 1.26 seconds. This is a
synthetic sorting experiment, not a graph visualization benchmark or a full-scale
memory claim. Timing on this workstation must not be generalized to an 8 GB PC.

The usable local library copies target different Python versions. NumPy 2.5.4
was available for Python 3.12, while DuckDB/PyArrow were available for Python
3.11. No compatible complete environment containing Matplotlib, SciPy, Numba,
igraph, Leiden and the test dependencies was found. PyPI installation failed
because the session could not resolve the package index. No network or
filesystem restrictions were bypassed.

## Still required before declaring the plan complete

- Install a compatible environment using `pip install -e '.[dev]'` or `uv sync --extra dev`.
- Run the complete pytest suite, including actual Numba compilation and CSV/Parquet integration; fix any failures.
- Generate and visually inspect the first 10K/100K figures.
- Run the multi-scenario and multi-seed benchmarks and order-sensitivity experiment.
- Evaluate an actual CluStRE binary in light/light_plus modes.
- Run the measured target workload after resource and storage checks, under a recorded memory constraint.
- Publish to GitHub if account authentication becomes available. The available gh credential was invalid when checked; no remote repository was created.

This file distinguishes implemented functionality from actual acceptance evidence.
It must be updated as remaining experiments are executed. The goal is still active.
