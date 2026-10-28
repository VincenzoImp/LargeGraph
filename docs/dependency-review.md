# Core dependency upgrade review

Candidate: DuckDB 2.0.0 and PyArrow 26.0.0. The validated public beta uses
DuckDB 1.5.6 and PyArrow 24.0.0. Developer-tool updates are integrated separately.

## Correctness and API migration

An independently constructed 8,192-node ring test compares all 114,688 CSR
neighbor entries in exact order, spanning many Arrow batches. The original
candidate mismatched 67,584 entries despite correct edge/degree totals. DuckDB 2
DB-API Arrow export re-materializes rows and can lose sorted order with
`preserve_insertion_order=false`. The relational `con.sql(query).to_arrow_reader`
path restores ordered streaming. Scalar DB-API queries are fully drained before
relational work, and readers are explicitly closed. See the
[upstream migration notes](https://github.com/duckdb/duckdb-python/releases/tag/v2.0.0).

Prepared schema 3 and analysis version 2 isolate candidate caches. Existing beta
reports remain readable; recomputation with the candidate needs a new output
directory. The local suite passes 51 tests on both candidate and legacy stacks,
including optional integrations. CI separately exercises the legacy engine.

## Full-scale resource evidence

Source `7d8a1e9a5a3624c225fbac44e14b579fb1a2b5f3` processed the identical existing
CSV with 5M nodes and 500M unique undirected edges. Generation was excluded; the
analysis/cache directory was new, OS caches were not flushed, and the workstation
was shared. The run used a hard 8,000,000,000-byte cgroup limit, no swap, eight CPU
quota equivalents, two application threads and a 3GB DuckDB buffer budget.

| Measurement | Published-beta engine reference | Candidate |
| --- | ---: | ---: |
| Complete analysis seconds | 507.33 | 500.03 |
| Largest sampled phase process-tree RSS GB | 4.13 | 6.83 |
| Peak preparation working disk GB | 28.1 | 30.8 |
| OOM / OOM kills / swap | 0 / 0 / 0 | 0 / 0 / 0 |

All 5M original-ID mappings were compared. The entire 4GB CSR, degree array,
offset array and community labels have **identical SHA-256** to the reference.
All conservation checks pass. Raw evidence is in
[`examples/results/duckdb2-review`](../examples/results/duckdb2-review/).

The candidate nevertheless has about **65% higher sampled peak RSS**, and retains
more resident memory in later phases. The timing difference is not a controlled
speedup claim. This combined stack/API-path comparison does not isolate which
library or allocator causes the increase.

## Merge decision

Keep the core-engine upgrade as a draft until profiling or an upstream fix
restores a suitable RAM margin for ordinary 8GB computers. Passing the hard limit
establishes feasibility, not the absence of a memory regression. Integrate the
independently validated mypy/Twine updates separately. Future major dependency
updates should be separate PRs, rather than coupling core changes to developer
tools.
