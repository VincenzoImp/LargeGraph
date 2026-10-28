# CLI and research workflows

Use `largegraph` from an installed wheel, or `uv run --no-sync largegraph`
in a synced checkout. `--help` lists the current commands. There is one analysis
pipeline, shared by the CLI, Python API and benchmarks.

## Generate and analyze

```bash
largegraph generate --config configs/small.json --output data/demo
largegraph analyze data/demo/edges.csv --nodes-file data/demo/nodes.csv \
  --truth data/demo/nodes.csv --output runs/demo --images --reference \
  --hierarchy-targets 16 64 256 --hash-input
```

Generation creates exactly the requested number of unique undirected edges,
an optional-node CSV with planted labels, and a manifest. Explicit generation
flags override JSON values. The JSON accepts generation/resource parameters;
unknown keys fail. Generation refuses to overwrite existing output and does not
resume partial generation. The analysis pipeline resumes its completed phases.

`--images` requires the `images` extra. It writes community node-link, matrix
and density figures as PNG/PDF/SVG, plus numeric display data, below
`RUN/report/images/`. All counts use every canonical edge; drawing filters affect
only visible links. `--max-groups` limits display reductions and `--max-edges`
limits drawn links. `--pixels` bounds raster dimensions to 64–4096.

`--layout auto|igraph|sfdp` chooses the bounded layout for the report and figures.
`sfdp` requires Graphviz. `--reference` requires the `leiden` extra and runs only
below explicit node/edge safety caps. `--truth-node` and `--truth-label` select
the original-ID and planted-label columns. ARI uses all nodes; exact AMI is
bounded and requires the `validation` extra.

Supplied coordinates add a point-density raster without computing a full graph
layout:

```bash
largegraph analyze edges.csv --output runs/positions --images \
  --coordinates positions.npy --pixels 1024
```

The file must be a finite numeric N×2 `.npy` array in prepared compact-ID order.
Inspect `nodes.parquet` in the prepared artifact to align original IDs. The
raster is written to `report/images/coordinates/`; the aggregate views remain
available. Both truth and coordinate inputs participate in cache fingerprints.

## Reusable preparation and validation

```bash
largegraph prepare edges.csv --nodes-file nodes.csv --work-dir work/demo \
  --export-metis graph.metis --memory 3GB --threads 2
largegraph validate runs/demo --output runs/demo-validation \
  --truth data/demo/nodes.csv --reference --memory 512MB
```

Preparation returns the reusable artifact directory and can export streamed
METIS adjacency. Standalone validation operates on a completed analysis; it
does not repeat preparation or clustering. Its output must be a new directory.
`verify RUN --deep` instead checks stored file sizes and hashes. `inspect RUN`,
`neighbors`, `members`, `export` and `serve` operate on the same analysis record;
see the [quickstart](quickstart.md) and [API guide](api.md).

## Resource experiments

```bash
uv run --no-sync python -m largegraph.benchmark --output runs/benchmark \
  --sizes 10000 100000 --scenarios communities weak bridges core-periphery null \
  --seeds 42 43 44 --hierarchy-targets 16 64 --reference --memory 512MB --rss-limit-gb 6
uv run --no-sync python -m largegraph.benchmark --output runs/spill-test \
  --spill-only --spill-memory 64MB --spill-rows 4000000
```

Each case generates a dataset and invokes the canonical `analyze` workflow in a
fresh subprocess, retaining the complete analysis, validation, stage log and
metrics. The sampled RSS guard is a stop mechanism, not a hard OS memory limit.
For enforced Linux limits:

```bash
uv run --no-sync python -m largegraph.constrained --output runs/limited \
  --memory-gb 8 --cpu-cores 8 -- \
  .venv/bin/largegraph analyze edges.csv --output runs/limited-analysis \
  --memory 3GB --threads 2
```

The runner verifies cgroup limits and disables swap. The CPU quota does not
reproduce another processor model. Before a target-scale run, inspect storage
with `largegraph analyze edges.csv --output runs/full --dry-run` and read
the [resource budget](resource-budget.md) and [experimental protocol](experiments.md).

Only the current API and file formats are supported before the first stable
release. Recompute an earlier analysis in a new output directory. Historical
experiment manifests describe their producing code and dependency versions;
they do not introduce compatibility paths into the runtime.
