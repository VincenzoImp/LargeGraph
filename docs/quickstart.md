# Quickstart

## Installation

The base wheel needs Python 3.11+ and six scientific/runtime packages. It includes
the local HTML explorer; no Node.js, browser extension, database server, GPU or
compiler is required on platforms covered by dependency wheels.

From a source checkout:

```bash
uv sync --locked --no-dev
uv run --no-sync largegraph-viz demo --open
```

From a downloaded release wheel:

```bash
uv tool install ./largegraph_viz-0.2.0b1-py3-none-any.whl
largegraph-viz demo --open
```

Or install that wheel with `python -m pip install ./largegraph_viz-0.2.0b1-py3-none-any.whl`
inside your preferred environment. PyPI distribution uses the same package and
entry point once the owner configures Trusted Publishing. A GitHub release wheel
works independently of that account setup.

Optional features are selected explicitly:

| Extra | Purpose |
| --- | --- |
| `images` | Matplotlib/SciPy PNG, PDF, SVG exports and coordinate raster mode |
| `leiden` | Bounded Leiden backend and reference comparisons |
| `networkit` | Bounded parallel Louvain backend (Linux/macOS) |
| `validation` | Adjusted mutual information using scikit-learn |
| `clustre-build` | Linux MPI build dependency for external CluStRE |

For example, `uv sync --locked --extra images --extra leiden` in a checkout,
or `pip install 'largegraph-viz[images,leiden]'` after a PyPI release is available.
The `dev` and `browser` dependency groups are for contributors, not end users.

## Your first graph

```csv
source,target
alice,bob
bob,charlie
charlie,alice
charlie,dana
```

```bash
largegraph-viz analyze edges.csv --output analysis --ram 8GB
largegraph-viz serve analysis
```

The report opens at `http://127.0.0.1:8765`. It binds only to the local computer.
The report also opens directly from `analysis/report/index.html`; original-node
queries require `serve`, because browsers cannot query the disk index directly.
Use `--port 0` to choose a free local port.

Network, matrix and density share the selected group. Choose a coarser hierarchy
level, select a group and click **Explore children**. The table supports keyboard
selection. Search filters group labels; node lookup searches exact original IDs.
Scroll to zoom, drag to pan, and double-click to fit the graph. The caption
reports represented nodes, hidden link weight and boundary edges.
**Export view** downloads one ZIP with nodes and the induced weighted summary,
including internal edges. **Save image** downloads the current canvas.

## Input choices

```bash
largegraph-viz analyze edges.parquet --source from_id --target to_id \
  --nodes-file nodes.csv --node-column id --output analysis
```

Both edge and optional node files may be CSV or Parquet. CSV requires a header.
CSV identifiers are read as text. Parquet endpoints are explicitly cast to
strings; a numeric Parquet column cannot preserve leading zeros it never stored.
`--delimiter ';'` changes the CSV delimiter for both inputs. Empty/missing IDs
fail; whitespace is preserved. Nodes found only in the node file become isolates.

The graph contract is undirected, unweighted and simple. Duplicate/reversed
edges and self-loops are reported and removed. Use `--ignore-extra-columns` only
when deliberately discarding attributes. Directed and weighted inputs require a
separate scientifically appropriate transformation before using this beta.

## Plan resources and recover

```bash
largegraph-viz analyze edges.csv --output analysis --ram 8GB --dry-run
largegraph-viz analyze edges.csv --output analysis --ram 8GB --threads 2
# After Ctrl-C, repeat exactly the same command.
largegraph-viz inspect analysis
largegraph-viz verify analysis --deep
```

The dry run reads at most 1 MiB of CSV or Parquet metadata. Its workspace estimate
is approximate. `--memory` overrides DuckDB's budget; it does not cap other
libraries. `--temp-dir` and `--temp-limit` control spill placement and capacity.
The default analysis cache is under `analysis/cache`; `--work-dir` can place it on
an SSD or share it between compatible runs. Resource settings may change on a
retry; changing graph or algorithm settings requires a new output directory.

## Export and query

```bash
largegraph-viz neighbors analysis --node alice --limit 20
largegraph-viz members analysis --community 3 --limit 100
largegraph-viz members analysis --community 3 --limit 100 --after 1234
largegraph-viz export analysis --format graphml --output summary-graphml
largegraph-viz export analysis --format parquet --output summary-parquet
```

Neighborhoods are the first IDs in prepared lexicographic order, with total
degree and a truncation flag. This is a bounded inspection, not a random sample
or an importance ranking. Membership pagination uses a compact-ID cursor.
Exports contain the exact quotient, not an expansion into 500 million original
edges. A diagonal weight stores each internal undirected edge once.

## Quality choices

`--backend streaming` is the default semi-external native heuristic. `--passes`
and `--resolution` change its budget/objective. It is order-sensitive and does
not guarantee connected or optimal communities. For a graph that fits the
explicit 100,000-node / 2,000,000-edge safety caps, install `leiden` and choose
`--backend leiden`. NetworKit PLM is available through the `networkit` extra and
`--backend networkit` on supported platforms. Its parallel scheduling may change
results despite a fixed seed. See [CluStRE](clustre.md) for the external streaming
backend and [real comparisons](comparisons.md) for quality/time tradeoffs.
Do not compare wall times for different algorithms without also comparing
partition quality, preprocessing and memory.
