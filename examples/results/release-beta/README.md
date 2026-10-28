# 0.2 workbench evidence

See [verification and interpretation](../../../docs/verification-beta.md).

The parent directory retains the first complete workbench run at source
`a022c78`, including hard cgroup limits and deep artifact checks. `final-cold/`
contains the final uncached engine/workbench analysis at `22609ae` (507.33 s,
excluding generation). `final-view/` contains the final overview layout rebuild
at `1d335b5`, reusing completed graph artifacts under the same hard 8GB/no-swap
limits. Later type guards, preflight checks and caption/ZIP fixes are separately
covered by integration/browser tests and do not change the graph counts.

All three have exit code 0 and verified limits, without OOM or swap. Cgroup
memory includes page cache and reached its cap with reclaim events. Phase RSS
measurements are sampled process-tree RSS, a different quantity.

Source CSVs and massive caches are excluded from Git. The reports retain input
SHA-256, phase configurations, counts, environment and producing code revision.
Timings are specific to the recorded constrained workstation and shared-host
conditions; they are not an isolated comparison with other products.
