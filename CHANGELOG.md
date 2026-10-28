# Changelog

## Unreleased

- Update the CI checkout and artifact actions, with byte-for-byte artifact
  upload/download verification.
- Update mypy and Twine while retaining the validated runtime dependency versions.
- Review future major Python dependency upgrades individually; group only minor
  and patch updates.
- Check exact sorted CSR neighborhoods across multiple Arrow batches to catch
  ordering regressions that preserve edge counts.

## 0.2.0b1

- Introduce `analyze`, `demo`, `serve`, `inspect`, `verify`, `neighbors`, `members`
  and `export` commands and a typed public analysis API.
- Add a self-contained local explorer with linked network/matrix/density views,
  hierarchy cuts, search, selection, exports and optional indexed node queries.
- Add Parquet input, exact connected components and degree profiles, a normalized
  maximum-spanning-forest hierarchy, SQLite lookup/membership indices and exact
  Parquet/CSV/GraphML quotient exports.
- Resume preparation phases and native clustering passes. Lock cache reuse,
  retain immutable completed reports and record file checksum baselines.
- Add resource preflight, a bundled reproducible demo, shared configuration and
  bounded optional Leiden/NetworKit backends. Preserve explicit undirected simple-graph
  semantics and count/approximation disclosures.
- Seed igraph in a worker for reproducible layouts without global RNG changes.
- Reduce the base to six direct runtime dependencies. Move figures, Leiden and
  extended validation to extras; standardize contributor/CI workflows on uv.
- Add recovery/browser/package tests, contributor documentation, issue templates
  and Trusted Publishing workflows. Large-scale Linux evidence is retained.

The beta does not add weighted/directed graph semantics, global optimality
guarantees, automatic recovery of synthetic generation or unbounded all-node
browser layouts. Existing 0.1 caches use the original schema and must be rebuilt
for the new workflow.

## 0.1.0

Initial research implementation: synthetic generation, disk-backed CSV
preparation, semi-external modularity moves, optional CluStRE, exact community
quotients, static complementary views and measured 5M-node/500M-edge experiments.
