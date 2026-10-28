# Benchmarks

## Synthetic reference workload

| Measurement | Recorded result |
| --- | ---: |
| Nodes / unique undirected edges | 5,000,000 / 500,000,000 |
| Complete analysis from an existing CSV | 507.33 seconds |
| Largest sampled phase process-tree RSS | 4.13 GB |
| Peak preparation working disk / spill | 28.1 GB / 10.0 GB |
| Detected groups / modularity | 512 / 0.909158592907265 |
| Portable HTML | About 2 MB |
| OOM events / OOM kills / swap usage | 0 / 0 / 0 |

The analysis included detection, exact quotient, components/profile, hierarchy,
lookup/membership index, validation, HTML and static figures. Generation was
excluded. The analysis/cache directory was new; OS caches were not flushed.
The shared Ryzen 9 7950X workstation was constrained to 8,000,000,000 bytes,
zero swap and eight CPU-quota equivalents. DuckDB used 3GB and two threads.
A CPU quota does not reproduce a low-end processor's architecture or frequency.
Cgroup memory includes file cache and reached its limit through normal reclaim;
it differs from process RSS. These sizes and budgets are examples, not limits.

The input is the strong synthetic community scenario, not evidence of universal
partition quality. CSV SHA-256:
`17b9293a4341106ca0ddd1b2c6b4dd86467155ff5649c8b8b9caacb05404d000`.
[Raw phase manifests and verification](../examples/results/full-scale/) record
the producing source and library versions. They are measurement records, not
analysis inputs for the current format. Naming/API cleanup is covered by current
integration tests; it is not presented as another full-scale measurement.

## Real-network comparison

The [SNAP Facebook comparison](comparisons.md) records fresh-process runs on
4,039 nodes and 88,234 edges. It separates detector, loading, common evaluation
and process-memory costs. External backends obtain higher modularity than the
native five-pass heuristic. It does not establish a full-scale speed ranking.

## Verification

CI runs Linux Python 3.12/3.13 and macOS/Windows Python 3.12. Checks cover graph
invariants, recovery/corruption, current CLI/API workflows, Chromium interaction
with GPU disabled, and clean wheel installation. Optional CluStRE tests require
its external binary; NetworKit tests require its extra. Large-scale resource
evidence applies to Linux only. Reproduce experiments using the
[protocol](experiments.md) and [CLI](cli.md).
