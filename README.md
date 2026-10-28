# LargeGraph

Explore graphs larger than RAM on a CPU-only computer. Turn a CSV or Parquet
edge list into an offline interactive report, exact community summaries and
optional figures. Data stays on your machine.

[Quickstart](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/quickstart.md) · [Python API](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/api.md) ·
[CLI](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/cli.md) · [Methods](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/methodology.md) · [Benchmarks](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/benchmarks.md)

![Interactive explorer](https://raw.githubusercontent.com/VincenzoImp/LargeGraph/main/examples/figures/explorer.png)

## Run

Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
git clone https://github.com/VincenzoImp/LargeGraph.git
cd LargeGraph
uv sync --locked --no-dev
uv run --no-sync largegraph demo --open
```

Analyze your data and query original nodes:

```bash
uv run --no-sync largegraph analyze edges.csv --output analysis
uv run --no-sync largegraph serve analysis
```

Inputs use `source,target` columns; custom names are configurable. IDs remain
strings. Include isolates with `--nodes-file`. The graph is **undirected,
unweighted and simple**: loops and duplicate/reversed edges are removed and
reported. Extra attributes require explicit opt-in to discard.

## Results

| Task | Output |
| --- | --- |
| Explore structure | Linked network, matrix and density views; hierarchy, search and selection |
| Measure structure | Exact quotient weights, connected components, degrees and isolates |
| Query nodes | Indexed original IDs, neighborhoods and paginated community members |
| Share | Standalone HTML; Parquet, CSV and GraphML summaries; optional PNG/PDF/SVG |
| Resume | Verified preparation phases and completed native clustering passes |

Add `--images` after installing the `images` extra. Optional backends include
bounded Leiden/NetworKit and external CluStRE. The base has six direct runtime
dependencies; see [dependencies and licenses](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/dependencies.md).

## Python

```python
from largegraph import AnalysisOptions, analyze

result = analyze("edges.parquet", "analysis", options=AnalysisOptions(passes=5))
print(result.report)
print(result.neighbors("alice", limit=20))
result.export("summary", format="graphml")
```

## Scale

Edges stream through disk-backed operations. Current detection and exact
profiles keep O(nodes) numerical state; billions of edges and billions of nodes
have different RAM costs. Graph size, RAM and CPU settings are configurable.
`--dry-run` estimates resources; `--ram` plans a budget rather than enforcing it.
See [resource costs and constraints](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/resource-budget.md).

A measured synthetic case with **5M nodes and 500M edges** completed in about
**8.5 minutes**, excluding generation, under an enforced **8 GB** limit and zero
swap. These are reference measurements, not product limits or universal timings.
The [benchmark record](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/benchmarks.md) contains the conditions and raw evidence.

Community detection is heuristic. Layout distances are not metric distances;
captions disclose filtering and artificial groups. See [methods](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/methodology.md)
and the [real-network comparison](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/comparisons.md).

The first PyPI release is being prepared. [Contribute](https://github.com/VincenzoImp/LargeGraph/blob/main/CONTRIBUTING.md) or follow
the [release guide](https://github.com/VincenzoImp/LargeGraph/blob/main/docs/releasing.md). Source: MIT; dependencies retain their
[own licenses](https://github.com/VincenzoImp/LargeGraph/blob/main/THIRD_PARTY_NOTICES.md).
