# Public beta acceptance plan

The product is a local, CPU-only workbench for graphs larger than RAM. Exact
preparation and aggregation are combined with explicitly heuristic partitions
and bounded visual exploration. Performance claims require measurements.

## Delivery gates

- A normal wheel installation runs a bundled demo without a compiler or account.
- `analyze` accepts CSV and Parquet, validates settings before expensive work,
  reports resource estimates and produces a portable interactive report.
- Interrupted analyses reuse completed phases and clustering passes. Completed
  outputs are immutable; partial reports never replace successful reports.
- Degree profiles, connected components, topology-based hierarchy, bounded local
  queries and interoperable summary exports have documented cost and semantics.
- Base dependencies have a concrete job; reference/validation/build dependencies
  are optional. Development and CI use the uv lockfile.
- Integration tests cover recovery, conservation, invalid inputs, packaged demo,
  browser interaction and wheel installation. Existing target-scale evidence is
  retained and a new constrained regression is recorded before release.
- Documentation includes a quickstart, API, recovery guide, limitations, benchmark
  protocol, dependency inventory and contributor/release instructions.
- GitHub has usable issue templates, CI and a versioned release. PyPI publishing
  uses Trusted Publishing when the owner has configured the account/project.

## Scope boundaries

The initial public beta preserves the undirected, unweighted simple-graph
contract. It rejects implicit weights/directions. Dense all-pairs results and
unbounded in-memory algorithms are outside the resource contract. Hierarchy and
layout are descriptive; neither establishes ground-truth communities. Linux is
the measured large-scale platform. Other platforms require their own CI evidence.

## Implementation order

1. Artifact integrity, locking, recovery and preparation checkpoints.
2. Shared configuration, resource preflight and typed Python entry points.
3. Profiles, components, hierarchy, neighborhood queries and exports.
4. Self-contained linked interactive report and packaged demo.
5. Dependency split, uv workflows, documentation and release packaging.
6. Recovery/browser/package checks, constrained benchmark, public release.
