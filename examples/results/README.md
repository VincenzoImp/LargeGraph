# Archived experimental evidence

All files in this directory come from actual local runs on 2026-10-28. They
contain numerical results and manifests, not the large input graph or temporary
workspaces. Absolute paths identify the original run and are not installation
requirements. `hardware.json` describes the workstation; CPU quotas and hard
memory limits are recorded separately.

- `validation-suite.csv` and `.json`: 30 native-backend runs: 10K/100K vertices,
  average degree 20, five scenarios, three graph seeds. Each run includes all
  three views, conservation checks, planted ARI/AMI and a bounded Leiden reference.
- `order-sensitivity.json`: three bijective relabelings of the same 10K/100K-edge
  graph. ARI to the original ordering ranges from about 0.906 to 0.955, showing
  order dependence rather than pretending detection is invariant.
- `clustre-comparison.json`: the actual upstream executable, pinned to the commit
  in `docs/clustre.md`, evaluated in light and light_plus modes on the same
  10K/100K-edge demo as the native backend. These configurations have different
  pass/refinement budgets; this is an integration comparison, not a claim of
  equal-budget algorithmic superiority.
- `dense-cgroup.json` and `dense-pipeline.json`: a 100K-node, 10M-edge run with 32
  planted blocks, a verified 8,000,000,000-byte cgroup limit, zero permitted swap
  and an eight-core CPU-time quota. The cgroup peak was about 1.09 GB including
  page cache; sampled process-tree RSS remained below 1 GB.
- `bridge-validation.json`: data accompanying the bridge-scenario figures in
  `examples/figures`. Generation used `configs/small.json` with scenario=bridges.
- `full-scale-cgroup.json` and `full-scale-launch.json`: actual hard-limit
  verification and command for the complete 5M-node/500M-edge workload, including
  generation. It completed in 988.20 seconds, with zero permitted swap and no OOM.
- `full-scale-pipeline.json`, `full-scale-generation.json`, `full-scale-prepared.json`,
  `full-scale-clustering.json` and `full-scale-quotient.json`: per-stage measurements,
  hashes, model parameters, convergence and exact conservation. Planted ARI=1.0
  on this strong assortative instance; full-scale AMI was explicitly not run.
- `full-scale-final-views-cgroup.json`, `full-community-view.json` and
  `full-density-view.json`: cached rendering of every one of the 512 groups,
  also under the 8 GB hard cap. `full-degree-distribution.csv` contains the exact
  full-graph degree histogram and complementary cumulative distribution.

The exact full weighted quotient is committed separately in
`examples/full-quotient`. Raw graph input and the complete memory traces remain
in the local `runs` tree and are excluded from Git. The final figures have PNG and
PDF versions in `examples/figures`.

The synthetic generator and native detector are documented precisely in the
methodology. Strong assortative cases give high recovery, while weak and
core–periphery cases do not. Null ARI is near zero. All views share their detected
partition, so visual agreement between them is not independent evidence.

`docs/verification.md` is the authoritative status of target-scale verification.
