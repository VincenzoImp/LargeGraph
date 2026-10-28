# Resource budget

All numbers below use decimal bytes unless explicitly described otherwise.

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
The default is 1024².

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

The measured 5M/500M workload completed under a verified 8,000,000,000-byte cgroup
cap and zero permitted swap. Peak sampled stage RSS was 4.15 GB in generation
and 4.00 GB in preparation; native detection peaked around 0.62 GB. The cgroup
reached its full 8 GB limit because it includes page cache. Kernel reclaim events
were recorded without OOM events. The largest sampled preparation workspace was
30.88 GB; the input dataset and retained outputs occupy additional storage.
These measurements describe the archived synthetic workload, not arbitrary CSV
identifier lengths or every possible degree distribution. See `verification.md`.

Sources: [DuckDB out-of-core processing](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads),
[DuckDB memory management](https://duckdb.org/2024/07/09/memory-management),
[DuckDB out-of-memory limitations](https://duckdb.org/docs/2.0/guides/performance/oom).
