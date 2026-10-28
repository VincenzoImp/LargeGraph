# Measured verification

All results below were executed on 2026-10-28. Raw reports and representative
figures are committed under `examples/results`, `examples/measurements` and
`examples/figures`. The exact weighted community graph of the full run is in
`examples/full-quotient`; the 500-million-row input stays outside Git.

## Target-scale result

**5,000,000 vertices and 500,000,000 unique undirected edges completed end to end
under a verified 8,000,000,000-byte cgroup limit, with swap disabled.** The CPU-time
quota was eight core equivalents; the application used two configured threads.
The cgroup includes children and page cache. It reached the 8 GB cap and reclaimed
cache without any OOM events or OOM kills. The largest sampled stage process-tree
RSS was 4,147,277,824 bytes, during generation.

The host was an AMD Ryzen 9 7950X with 16 physical cores, 32 logical threads and
about 66.5 billion bytes of RAM, running Linux 6.12. This is a **constrained
workstation measurement**, not a timing measurement from a physical 8 GB machine
or a claim that different CPU/SSD models run equally fast. Hardware and actual
cgroup values are archived separately.

| Phase | Wall seconds | Sampled peak RSS | Additional observation |
| --- | ---: | ---: | --- |
| Synthetic generation | 486.16 | 4.15 GB | 575M proposals; exactly 500M retained unique pairs |
| Preparation | 363.52 | 4.00 GB | 5M nodes; 500M rows; no loops or duplicates left |
| Native streaming detection | 76.40 | 0.62 GB | Converged in 3 passes, including full objective scans |
| Exact quotient | 18.72 | 0.68 GB | Node, edge and degree-volume conservation passed |
| Validation | 28.72 | 1.26 GB | All checks passed; planted ARI=1.0 |

The controller measured **988.20 seconds (16.47 minutes)** for generation and the
complete pipeline, including imports, input hashing, rendering and validation.
The primary run rendered 128 display groups in the node-link/matrix views and
density levels 32, 128 and 512. A cached follow-up rendered all 512 groups in
every view under the same hard limits; its cgroup report is archived separately.
The archived final figures also use adaptive marker areas and stable identifier
colors to keep all 512 groups readable.

The exact partition contains 512 groups. It recovered all planted memberships on
this strong assortative synthetic instance: ARI=1.0 and modularity=0.9091585929.
There are 456,124,163 within-group and 43,875,837 between-group edges. The mean
degree is 200, with minimum 41 and maximum 6,800. Full-scale AMI was explicitly
not computed because of its documented cost cap; it is not substituted with a
sampled result.

Generation spilled about 18.70 GB and preparation about 9.76 GB. The largest
sampled preparation workspace was 30.88 GB. These stage-local disk peaks exclude
other retained datasets, and sampled monitoring can miss shorter peaks. See the
resource budget before sizing a different workload.

Evidence: `full-scale-cgroup.json`, `full-scale-launch.json`,
`full-scale-generation.json`, `full-scale-prepared.json`, `full-scale-clustering.json`,
`full-scale-quotient.json` and `full-scale-pipeline.json` under `examples/results`.
The complete cgroup trace and large source data remain in the local `runs` tree.

## Smaller experiments and failures

Thirty runs cover two graph sizes (10K/100K nodes, average degree 20), five
scenarios and three graph seeds. Each run produced all views, exact conservation
checks, planted recovery and a bounded Leiden reference.

| Scenario | Mean ARI, 10K nodes | Mean ARI, 100K nodes |
| --- | ---: | ---: |
| Strong communities | 0.9994 | 0.9965 |
| Weak communities | 0.0601 | 0.0454 |
| Community bridges | 0.9983 | 0.9973 |
| Core-periphery roles | 0.0014 | 0.0011 |
| No planted affinity | approximately 0 | approximately 0 |

These are results of the native five-pass local-moving heuristic, not a
guarantee of recovery on other graphs. In particular, weak-community recovery is
poor, and assortative community detection does not recover the core-periphery
role labels. Scores, dispersion, reference comparisons and failures are retained
in `validation-suite.csv` and `.json`. Different views share a partition and are
not independent evidence of its correctness.

Three relabelings of the same 10K-node/100K-edge demo give ARI to the original
ordering between 0.9063 and 0.9546. This directly demonstrates order dependence.
A separate 100K-node/10M-edge experiment with 32 planted groups completed under
the same 8 GB hard cap and zero swap, with about 1.09 GB cgroup memory peak.

## Actual CluStRE integration

The official executable at commit `39a4e57c2de0bee45a2752597db502963a1536de`
was built with MPICH 5.0.2 and executed in light and light_plus modes on the same
10K-node/100K-edge demo used by the native backend. Seed 42 was passed explicitly.

| Backend/configuration | Modularity | Planted ARI |
| --- | ---: | ---: |
| Native, 5 passes | 0.7521 | 0.9540 |
| CluStRE light | 0.3401 | 0.3270 |
| CluStRE light_plus | 0.7135 | 0.8775 |

These configurations have different refinement budgets. This is an integration
comparison on one input, not an equal-budget performance study or a claim that
the native algorithm outperforms published alternatives generally. Exact child
peak RSS and CPU usage come from Linux wait4 resource accounting; sampled parent
and child-tree measurements are also retained. Full-scale verification above
concerns the native backend. Build instructions and logs are described in
`clustre.md`; the actual-binary integration tests cover both modes and an isolate.

## Software checks

- **23 tests pass on Python 3.12 and Python 3.11**, including actual CluStRE runs
  when `CLUSTRE_BINARY` is set. Without that optional binary, 21 pass and 2 skip.
- Ruff passes. The source, project metadata, configuration files and documented
  fixture commands were checked.
- Numerical contracts include 60 graph/resolution combinations over four passes,
  compared against an independent dense objective, plus block probabilities,
  matrix normalizations, raster mass and label-invariant ARI.
- Integration checks cover real Numba compilation, CSV/Parquet, deduplication,
  self-loops, isolates, cache invalidation, coordinate rasterization, truth-label
  independence, exact quotient conservation and the actual CluStRE executable.
- The 10K/100K-edge demo, bridge gallery, all target-scale views and a Python 3.11
  fixture render were produced and visually inspected.
- A separate 4M-row sort with a 64 MB DuckDB budget demonstrated actual disk
  spilling; the current and original raw profiles are retained under
  `examples/measurements`. It is supplementary evidence, not a substitute for
  the full-scale graph run.

`uv.lock` records dependency resolution. Per-run manifests preserve exact
versions, graph hashes, seeds, resource settings and transformations. The tested
Python 3.12 environment used NumPy 2.5.4, DuckDB 1.5.6, PyArrow 24.0.0,
Numba 0.68.1, igraph 1.0.0, Leidenalg 0.12.0, Matplotlib 3.11.2 and SciPy 1.18.1.
The Python 3.11 environment used NumPy 2.4.6 and SciPy 1.17.1. Timing and accuracy
claims are limited to the archived configurations.
