# Python API

The public entry points are `analyze`, `Analysis`, `AnalysisOptions` and
`Resources`. Before the first stable release, API and format changes may break earlier runs.
Only the current API and analysis format are accepted; there are no migration
adapters. Recompute earlier analyses in a new output directory. Manifests retain
exact library versions for provenance.

```python
from pathlib import Path
from largegraph import Analysis, AnalysisOptions, Resources, analyze

result = analyze(
    "edges.parquet",
    "analysis",
    work_dir="ssd-cache",
    options=AnalysisOptions(
        nodes_file=Path("nodes.csv"),
        passes=5,
        hierarchy_targets=(16, 64, 256),
        hash_input=True,
    ),
    resources=Resources(memory="3GB", threads=2, batch_rows=250_000),
    ram="8GB",
)
print(result.report)
result = Analysis.open("analysis")
print(result.neighbors("001", limit=20))
print(result.members(community=3, limit=100, after=-1))
result.export("summary-csv", format="csv")
```

`analyze` returns an immutable dataclass with paths to `prepared`, `clustering`,
`quotient`, `profile`, `hierarchy`, `index` and `output`. It checks configuration
before expensive operations, verifies completed caches, and resumes interrupted
phases. It raises exceptions for programmatic handling; the CLI formats those
errors and uses exit code 2. Ctrl-C exits the CLI with code 130.

`Analysis.open` reads the run record without scanning the graph. `neighbors`
uses SQLite for the identifier and seeks directly to a bounded CSR neighborhood;
it reads at most `limit` neighbor IDs. Membership queries use a disk index and a
compact-ID cursor. Both APIs limit a response to 10,000 rows. Closing the browser
does not affect artifacts or the original CSV.

`AnalysisOptions` is also the schema for `analyze --config settings.json`:

```json
{
  "passes": 8,
  "resolution": 1.0,
  "hierarchy_targets": [16, 64, 256],
  "max_groups": 128,
  "max_edges": 1200,
  "hash_input": true
}
```

Explicit CLI flags override config values. Resource controls (`ram`, `memory`,
`threads`, `batch_rows`, spill directory) are separate CLI flags or `Resources`
fields. Path values in JSON resolve from the working directory, just like flags.
`max_groups` caps static figures and artificial reductions of a large
disconnected forest; actual interactive cuts and fine partitions are included up
to the fixed browser safety cap of 1,024 groups per level.
Different analysis options require a new run directory. Compatible preparation
artifacts can still be shared using the same work directory.

## Artifact layout

```text
analysis/
  analysis.json          # job configuration, status and relative artifact paths
  preflight.json         # approximate resource plan
  cache/
    prepared-*/          # nodes/edges Parquet, degrees, offsets, flat adjacency
    cluster-*/           # complete assignments, objective and pass history
    quotient-*/          # exact weighted summary
    profile-*/           # components, degree histogram and profile
    hierarchy-*/         # nested topology cuts and exact rollups
    index-*/             # read-only SQLite identifier/membership index
  report/
    index.html           # portable standalone explorer
    report.json          # bounded aggregate data for the explorer
    summary/             # exact quotient Parquet files
    provenance/          # phase manifests
    validation/          # conservation checks
    inventory.json       # output file lengths and SHA-256 baselines
```

Copy `report/` to share an aggregate result without the original graph or index.
To keep original-node queries, preserve the run, inputs and referenced caches.
Default cache paths are relative to the run, so moving the entire run preserves
its local references. A custom external work directory must be moved consistently.

## Import and plotting behavior

Importing `largegraph` does not import Matplotlib, Arrow, NumPy or Numba.
The CLI configures thread environment variables before scientific imports. An
embedding application that already initialized a BLAS runtime should configure
its own thread policy. Static plotting uses a local Matplotlib style context.
The bounded layout seeds igraph in an isolated worker. This avoids replacing
an embedding application's global RNG and controls igraph's internal jitter.
Layout reproducibility is evaluated within the recorded library/platform build;
bitwise identity across different native-library versions is not promised.

## Figures and scientific checks

Set `images=True` for community, matrix and multi-resolution density figures.
`layout="igraph"` or `"sfdp"` selects the bounded layout for the HTML report and
figures; `"auto"` selects an available engine. `coordinates=Path("positions.npy")`
adds an exact point raster in `report/images/coordinates/`, using an N×2 numeric
array in prepared-node order. It requires `images=True`; coordinates are supplied
by the caller, never computed through an all-node force layout.

`truth=Path("nodes.csv")`, `truth_node="node_id"` and
`truth_label="planted_community"` enable planted-label recovery checks.
`reference=True` adds a Leiden comparison below explicit in-memory safety caps
and requires the `leiden` extra. The truth and coordinate files participate in
the analysis fingerprint. They must exist before an analysis starts.
