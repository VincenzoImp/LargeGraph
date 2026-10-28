# largegraph-viz

**Explore graphs larger than RAM on a CPU-only computer.**

Turn an edge list into an interactive local report, exact community summaries,
structural profiles and publication-ready figures. Preparation uses disk-backed
operations; the browser receives a bounded summary. No GPU, hosted service,
account or graph upload is needed to analyze your data.

[Quickstart](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/quickstart.md) · [Python API](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/api.md) ·
[Methods](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/methodology.md) · [Real case & comparisons](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/comparisons.md) · [Resource budget](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/resource-budget.md) ·
[Measured results](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/verification.md) · [Contributing](https://github.com/VincenzoImp/largegraph-viz/blob/main/CONTRIBUTING.md)

![Interactive graph explorer](https://raw.githubusercontent.com/VincenzoImp/largegraph-viz/main/examples/figures/explorer.png)

## Try it

With [uv](https://docs.astral.sh/uv/getting-started/installation/), from a checkout:

```bash
git clone https://github.com/VincenzoImp/largegraph-viz.git
cd largegraph-viz
uv sync --locked --no-dev
uv run --no-sync largegraph-viz demo --open
```

The demo is bundled and recomputed locally. Open `largegraph-demo/report/index.html`
if a browser does not start automatically. The standalone HTML works offline.
Released wheels also install with `pip` or `uv tool install`; see
[installation](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/quickstart.md#installation). Python 3.11+; Linux is the
measured target-scale platform. CI exercises Linux, macOS and Windows.

## Analyze your graph

```bash
uv run --no-sync largegraph-viz analyze edges.csv --output my-analysis --ram 8GB
uv run --no-sync largegraph-viz serve my-analysis
```

CSV and Parquet inputs use `source,target` columns. Node identifiers are preserved
as strings, including `001`. This beta implements **undirected, unweighted,
simple graphs**: loops are removed, repeated/reversed edges are deduplicated and
all changes are reported. Extra columns require an explicit opt-in. Weights and
directions are not inferred. Include isolates with `--nodes-file nodes.csv`.

Before a large job, add `--dry-run` to inspect the input and estimated disk/RAM
requirements. `--ram` is a planning target, **not an operating-system limit**.
[Hard limits](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/resource-budget.md) use the optional Linux cgroup runner.

## What you get

| Task | Result |
| --- | --- |
| Understand structure | Linked network, matrix and density views; selection, search and hierarchical exploration |
| Inspect exact counts | All-edge quotient weights, node counts, degree volumes, internal and boundary edges |
| Characterize the graph | Degree distribution, connected components, isolates and largest-component size |
| Investigate original nodes | Indexed ID lookup, paginated community membership and bounded neighborhood queries |
| Share results | Portable HTML, Parquet/CSV/GraphML summary exports; optional PNG/PDF/SVG figures |
| Recover long jobs | Completed preparation phases and native clustering passes are reused after interruption |

Static figures: `uv sync --extra images`, then add `--images` to `analyze`.
The base installation has **six direct dependencies**. Leiden, NetworKit, extended validation
and external CluStRE build tools are optional; see the
[dependency inventory](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/dependencies.md).

## Scale and interpretation

The 0.2 workbench processed **5 million nodes and 500 million unique undirected
edges**, including profiles, a query index, hierarchy, interactive report and
static figures, under an enforced **8,000,000,000-byte memory limit**, swap
disabled. The first full workbench run took about **8.4 minutes from the existing
CSV**, excluding generation. Its portable HTML was about **2 MB**. This is evidence
for that dataset and workstation, not a universal time guarantee. The original
generation-plus-analysis experiment took about 16.5 minutes. See the
[raw evidence and limitations](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/verification.md).

Counts use the complete canonical graph. Native detection is a modularity
heuristic and can struggle with weak or core-periphery structure. The hierarchy
is a descriptive maximum-spanning-forest construction. Layout distances are not
metric distances, and density shows aggregate positions. Filtering, artificial
`Other` groups and omitted link weight are disclosed in the report. Full node
coordinates are used only when explicitly supplied.

An 8 GB computer still needs an SSD workspace: initially allow around 100 GB for
the target workload. Long identifiers, duplicates and sorting can change disk
requirements substantially. See [recovery and integrity](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/recovery.md),
[methodology](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/methodology.md) and [benchmark protocol](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/experiments.md).

## Use from Python

```python
from largegraph_viz import AnalysisOptions, analyze

result = analyze("edges.parquet", "my-analysis", options=AnalysisOptions(passes=5))
print(result.report)
print(result.neighbors("alice", limit=20))
result.export("summary", format="graphml")
```

The [API guide](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/api.md) covers configuration and reusable artifacts.
[Individual view commands](https://github.com/VincenzoImp/largegraph-viz/blob/main/docs/legacy-cli.md) remain available for research
workflows. For bugs or resource regressions, include a small reproducer and
`largegraph-viz doctor` output in an issue.

Our source is MIT-licensed. Dependencies retain their own licenses, including
GPL components; see [third-party notices](https://github.com/VincenzoImp/largegraph-viz/blob/main/THIRD_PARTY_NOTICES.md).
