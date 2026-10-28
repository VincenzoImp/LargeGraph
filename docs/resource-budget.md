# Resource budget

All numbers below use decimal bytes unless explicitly described otherwise.
Graph sizes and RAM/CPU budgets are examples, not fixed product limits.
`--ram`, `--memory`, `--threads`, batch sizes and spill storage are configurable.

## Scaling beyond the reference workload

The edge list and adjacency can exceed RAM because joins, sorting and scans use
SSD storage and bounded batches. The current native detector retains O(n)
numerical state: degrees, labels, volumes, scores, marks and loaded offsets use
at least **40 × n bytes** during moving passes, before temporary arrays, buffers,
JIT and DuckDB. At one billion nodes that state alone is about **40 GB**. Exact
component/profile reductions also require O(n) state and sorting temporaries.

A billion edges among fewer nodes is therefore a different resource problem
from a billion nodes. Neither arbitrary billion-node operation on an 8 GB
computer nor a billion-edge benchmark has been demonstrated here. The current
compact-ID representation accepts fewer than 2^32 nodes; this is a genuine
format constraint, independent of the reference workload. Moving all node state
to external-memory algorithms is future work, not an existing guarantee.

The following table is one measured workload, not a maximum supported size.

For n=5,000,000 and m=500,000,000 unique undirected edges:

| Structure | Raw size |
| --- | ---: |
| Two uint32 canonical endpoint columns | 4.00 GB |
| Symmetric uint32 adjacency targets | 4.00 GB on disk |
| uint64 degrees | 40 MB |
| uint64 adjacency offsets | approximately 40 MB |
| uint32 assignment array | 20 MB |
| uint64 community-volume array at n singleton groups | 40 MB |
| float64 candidate-score array | 40 MB |
| uint32 marking array | 20 MB |
| uint32 touched-community buffer | 4 × maximum degree bytes |
| 1024×1024 uint64 pixel grid | 8.39 MB |
| 4096×4096 uint64 pixel grid | 134.22 MB |

The adjacency is read, not retained in full RAM. Numeric community state is a few
hundred MB at the target size. Python, native-library allocations, NumPy sorting
temporaries, Arrow buffers, JIT compilation and figure buffers are additional.
Multiple raster channels and float64 smoothing buffers can exceed 0.5 GB at 4096².
The analysis default is 512².

`--memory 3GB` applies to DuckDB-managed allocations. The process total can exceed
it. Use two threads first, do not run full pipelines in parallel, and leave room
for the OS and native allocations. The benchmark's RSS guard samples the process
tree every 0.1 seconds, so short peaks can be missed. It sums RSS, which can count
shared pages more than once across processes. Monitoring is neither a cgroup nor
a hard address-space limit. Use an OS/container memory limit for an 8 GB hardware
claim and record the exact configuration.

Disk cost includes CSV (often around 8 GB for the numeric target workload),
canonical Parquet, adjacency, database staging, candidate files, quotient staging,
external sort runs and possibly a METIS text export. A provisional 100 GB of free
SSD space is a starting estimate, not an upper bound. High duplicate rates,
long string IDs and skew can change disk requirements considerably. Check actual
free space and measure smaller representative datasets. Temporary spill is capped
by `--temp-limit`; the persistent scratch database and outputs are separate.

The generator streams O(batch size) edge proposals but keeps O(n+K²) latent state.
The generation block count is capped at 2048. Duplicate removal uses external
grouping. Dense requested graphs or badly concentrated proposals can need many
top-up rounds and much longer runtimes. No claim of constant-time generation per
retained edge is made near saturation.

Disk monitoring sums logical file sizes. Sparse allocation, filesystem
compression and sampled intervals can make actual allocated storage differ.

The exact quotient can have O(m) distinct pairs. It is retained on disk; no
algorithm loads the full quotient into a Python graph. Only a display matrix of
at most 1024² weights is retained for layout and rendering. The original graph
is not passed to NetworkX, igraph, sfdp or an in-memory Leiden implementation.
The explicit Leiden validation reference is limited to 100,000 nodes and 2 million
edges. These caps are intentionally separate from production-scale detection.

Measured reference results and raw evidence are in [benchmarks](benchmarks.md).

Sources: [DuckDB out-of-core processing](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads),
[DuckDB memory management](https://duckdb.org/2024/07/09/memory-management),
[DuckDB out-of-memory limitations](https://duckdb.org/docs/2.0/guides/performance/oom).


## Configuration and display bounds

`analyze --ram 8GB` plans DuckDB at 3GB by default and reserves room for
arrays, Arrow, JIT and rendering. It is a planning target; the enforced cgroup
runner remains the hard-limit option. Run it from an installed package with
`python -m largegraph.constrained --output limited --memory-gb 8 --cpu-cores 8 -- largegraph analyze edges.csv --output analysis`.

The browser contains at most 1,024 aggregate groups per level, never 5 million
node objects. The target-scale portable HTML was about 2 MB. Query responses cap
at 10,000 rows. A bounded seeded layout runs in a separate CPU worker; its memory
is included in process-tree monitoring. The operation cost table is in
[workbench methods](workbench-methods.md).
