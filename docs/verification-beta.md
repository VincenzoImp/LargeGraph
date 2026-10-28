# Public beta verification

The 0.2 workbench was exercised at the target scale, in addition to the original
[0.1 experiment](verification.md). This page separates new measurements from
historical evidence and cached view rebuilds.

## Complete uncached analysis

The final full analysis used the original 7,777,974,671-byte CSV, with SHA-256
`17b9293a4341106ca0ddd1b2c6b4dd86467155ff5649c8b8b9caacb05404d000`:

- 5,000,000 nodes and 500,000,000 unique undirected edges.
- A new empty analysis/cache directory; OS page cache was not flushed.
- Rootless cgroup limit 8,000,000,000 bytes, swap disabled, CPU quota 8 equivalents.
- DuckDB 3GB, two configured application threads, 250,000-row batches.
- Native detection, exact quotient, components/profile, hierarchy cuts 16/64/256,
  lookup/membership index, conservation validation, HTML and static figures.
- 512 detected groups; modularity 0.909158592907265. The input is the strong
  synthetic scenario, not evidence of universal community recovery.
- **507.33 seconds (8.46 minutes)**, excluding synthetic generation.
- **No OOM events or OOM kills, no swap usage.** Cgroup memory reached the 8GB
  cap because it includes file cache; reclaim events were recorded.

The largest sampled phase process-tree RSS was **4.13 GB**; preparation used
about **28.1 GB** peak working storage and **10.0 GB** peak spill in this run.
These are separate from the cgroup's page-cache-inclusive peak.

The producing source was `22609aeb46532ef88972c1133926361d729b244d`. Raw commands,
limits, manifests, file hashes and conservation results are under
[`examples/results/release-beta/final-cold`](../examples/results/release-beta/final-cold/).
The earlier uncached workbench run took 506.22 seconds and is retained in the
parent evidence directory. Different operation sets and shared-host activity
prevent interpreting the small timing differences as a speedup benchmark.

The machine is the recorded Ryzen 9 7950X workstation, constrained by cgroup; it
is not a physical low-end eight-core computer. Documentation, package checks and
small development tasks ran on the shared host. Times are descriptive and
hardware-specific. CPU quota limits CPU time, not CPU architecture/frequency.

## Final viewer and indexed lookup

The final independent overview layouts and singleton-query handling were rebuilt
from the same complete engine artifacts under the same hard limit. This took
about **31.5 seconds**, including input hashing, conservation validation, seeded
layouts, static figures and HTML. This is a cached view rebuild, not a second
CSV-ingestion timing. The corresponding source was
`1d335b5fb66a3bf9e58fe8ff3f76ecf051512757`; raw evidence is in `final-view/`.
Subsequent preflight/type guards, captions and ZIP-date fixes do not change the
graph transformations; they are covered by small integration/browser tests.

The final portable HTML is approximately **2.01 MB**, with all 512 detected
groups and coarser cuts. A 50-query sequence for original IDs 0–49, limit 100,
had median response time about **0.6 ms** in the recorded warm-cache setting.
This is a bounded indexed lookup measurement, not a cold-storage latency promise.
Both runs passed deep comparison against recorded artifact SHA-256 baselines.

## Installation, platforms and behavior

The base wheel and source distribution were installed into clean Python 3.12
environments outside the checkout. The packaged demo and deep verification ran
without Matplotlib, SciPy, Leiden, scikit-learn or NetworKit. That installation
resolved **six direct and eight total third-party Python runtime packages**;
native libraries bundled in wheels are additional components.

The release checks cover:

- Lint/format and type checks for the public API/configuration/budget boundary.
- Exact count, adjacency, modularity, raster and hierarchy invariants.
- Process interruption, pass/phase recovery, simulated disk full, corruption,
  changed-input/config refusal and two-process reuse of one artifact.
- Real Chromium interaction with GPU disabled: linked selection, hierarchy,
  search, zoom, responsive layout, image and ZIP/CSV exports.
- Loopback API queries, response caps and unknown-host/path rejection.
- Optional local CluStRE, Leiden and NetworKit integration checks.
- Wheel/sdist metadata and citation schema validation.

GitHub CI exercises Linux Python 3.11, 3.12 and 3.13, and macOS/Windows Python
3.12. The Linux browser/package job installs a clean base wheel independently.
Optional CluStRE tests require the separately built binary; NetworKit is not a
mandatory dependency of platform jobs. Large-scale resource measurements apply
to Linux only. The [real Facebook comparison](comparisons.md) records external
backends obtaining higher modularity than the native five-pass partition.
