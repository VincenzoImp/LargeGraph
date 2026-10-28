# Experimental protocol

## Sequence

1. Render 10,000 nodes / 100,000 edges and inspect the three views.
2. Run invariant tests and compare recovered groups to planted groups.
3. Compare native detection, bounded Leiden and actual CluStRE light/light_plus
   when its binary is available. Keep conversion and detection costs separate.
4. Vary seed, mixing, group sizes and graph scenario. Include a no-planted-affinity
   control and the core–periphery case, where assortative groups need not match
   the roles encoded by the generator.
5. Relabel the same graph to test node-order sensitivity. Different generator
   seeds change the graph; different layout seeds alone do not change native
   detection. Do not confuse these three experiments.
6. Force external sorting below a small memory budget, verifying observed disk
   spill from profiling or sampled storage. Do not infer out-of-core capability
   merely because the software supports spilling in principle.
7. Increase dataset size progressively, then run the actual 5M/500M workload
   under a recorded 8 GB OS/container memory limit. Do not extrapolate an 8 GB
   compatibility claim from unconstrained workstation execution.

The benchmark script automates generation, the full pipeline, optional reference
comparison and CSV/JSON reports for multiple sizes/scenarios/seeds. Its default
mean degree is 20 for fast previews; use **--mean-degree 200** when studying the
specified target density. Each stage starts in a fresh process. First-run imports
and JIT time are included. If measuring warmed performance, explicitly report
which runs are cold and preserve the raw data.

To test order sensitivity, take the `prepared` and `clustering` paths from a
run's `pipeline.json`:

```bash
.venv/bin/python scripts/order_sensitivity.py \
  --prepared work/demo/prepared-REPLACE_WITH_ACTUAL_ID \
  --clustering work/demo/cluster-REPLACE_WITH_ACTUAL_ID \
  --output runs/order-sensitivity --seeds 101 102 103
```

This bounded experiment bijectively relabels the *same* graph, using zero-padded
identifiers to control lexicographic preparation order. It restores labels to
original compact-node order before calculating ARI/AMI. The permutation arrays
and alternative workspaces are retained.

## Required reports

Record n, m, average degree, isolates, observed degree distribution, planted
block sizes, realized within/between block connectivity, ARI/AMI, modularity at
the stated resolution, reference agreement, and order sensitivity. For small
reference graphs, also report transitivity and connected components. A high
modularity value on the null does not establish real planted communities.

Record wall time, sampled peak process-tree RSS, disk peak, spill peak, thread
count, batch size, temporary-storage budget, software versions and hardware.
The monitoring interval is recorded. Prefer at least three graph seeds and
report dispersion, not only the fastest run. Keep failed runs and their logs.
Do not calculate confidence intervals by treating dependent pixels or views as
independent samples.

Assess figures for quantitative interpretability: legends match transformations,
all filtered weight is disclosed, internal-edge conventions are consistent, and
`Other` is explicitly artificial. Preserve raw matrices, quotient tables and
unsmoothed grids alongside publication figures.

## Acceptance evidence

| Requirement | Evidence |
| --- | --- |
| Exactly m unique generated edges | CSV row count and external uniqueness/loop check |
| Correct preparation | Known tiny graph with reverse duplicates, loops and isolates |
| Correct aggregation | sum quotient weights=m; sizes=n; volumes=2m |
| Correct matrix conventions | symmetric row sums=volumes; density in [0,1] |
| Correct raster counts | unsmoothed node mass=n; edge-pixel semantics independently tested |
| Detection behavior | exact nondecreasing local objective, planted recovery, null, order perturbations |
| Low-memory external execution | nonzero observed spill plus process-tree measurement |
| 5M/500M on 8 GB | measured full-scale run under the recorded memory constraint |
| Reproducibility | input hashes, seeds, manifests, environment, raw outputs |

The software and test suite implement these measurements. A run not yet performed
is not a passed acceptance criterion; see `verification.md` for actual status.
