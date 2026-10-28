# Comparisons and a real graph

The workbench's goal is a usable resource-aware workflow, not a claim to replace
every graph library. Disk preparation, reusable exact summaries, recovery, local
exploration and exports are combined in one product. Mature external algorithms
remain useful components or baselines.

| Tool/method | Established strength | Relationship to this project |
| --- | --- | --- |
| [NetworKit](https://networkit.github.io/) | Compiled parallel graph analytics | Optional bounded PLM backend and comparison baseline |
| [Leiden](https://github.com/vtraag/leidenalg) | High-quality modularity/CPM community methods | Optional bounded backend/reference |
| [CluStRE](https://github.com/KaHIP/CluStRE) | Memory-efficient streaming community detection | Explicit external backend |
| [GraphChi](https://www.usenix.org/conference/osdi12/technical-sessions/presentation/kyrola) | Disk-oriented graph computation on one computer | Prior engineering approach; no direct speed claim here |
| [graph-tool](https://graph-tool.skewed.de/) | Broad compiled analysis and statistical inference | A different, complementary analysis ecosystem |
| [Gephi](https://gephi.org/desktop/) | Interactive desktop exploration and styling | A different workflow; no blanket performance comparison |

## SNAP Facebook case

The [SNAP Facebook combined dataset](https://snap.stanford.edu/data/ego-Facebook.html)
has 4,039 nodes and 88,234 edges. It combines anonymized ego networks. Source:
J. McAuley and J. Leskovec, *Learning to Discover Social Circles in Ego Networks*,
NIPS 2012. Original data retains upstream terms and is fetched separately; the
repository records its URL and SHA-256, rather than redistributing the input.

```bash
uv sync --locked --extra images --extra leiden --extra validation --group benchmarks
uv run --no-sync python scripts/fetch_facebook.py
uv run --no-sync largegraph-viz analyze data/facebook/edges.csv \
  --output runs/facebook --backend leiden --memory 256MB --hash-input --images
uv run --no-sync python scripts/compare_backends.py PREPARED_DIRECTORY \
  --output runs/facebook-comparison.json --threads 2
```

Use the prepared path from `largegraph-viz inspect runs/facebook`. The comparison
launches a fresh process per backend and seed, using identical canonical node
ordering and edges. Preparation/report generation are excluded. It separates
graph loading/import, detector time, common quality evaluation and process peak
RSS. Seed values are 42,43,44. Native order is fixed, so its repeated seeds are
not independent randomized partitions. JIT/OS caches are not flushed.

Measured medians on the development Linux workstation:

| Detector | Mean modularity | Communities across seeds | Median detector seconds | Median load/import seconds | Max process RSS MB |
| --- | ---: | --- | ---: | ---: | ---: |
| Native, 5 passes | 0.810422 | 101,101,101 | 0.132 | <0.001 | 238.6 |
| Leiden, 5 iterations | 0.835672 | 16,14,15 | 0.510 | 0.181 | 227.9 |
| NetworKit PLM, refinement, maxIter=32 | 0.835585 | 16,16,16 | 0.007 | 0.552 | 297.5 |

These are different algorithms and budgets. NetworKit's kernel is fastest in this
case; both external methods find higher modularity than the native five-pass
heuristic. This is why the product offers backend choices. No ground-truth
exclusive partition is assumed from the dataset's overlapping circles. Higher
modularity is not proof of a truer social partition.

Raw measurements are in
[`examples/results/facebook`](../examples/results/facebook/README.md). They do
not establish a ranking at 500 million edges or between full visualization
products. The [experimental protocol](experiments.md) defines fair future
comparisons: same semantics/input, explicit resource limits, cold and warm costs,
output quality, precision, I/O, time to a useful result and failure behavior.
