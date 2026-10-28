# Workbench methods and costs

These methods extend the original [engine methodology](methodology.md). They
preserve its undirected, unweighted simple-graph contract. Let n be the node
count, m the canonical undirected edge count, k the detected group count, q the
number of nonzero quotient pairs and B the batch size.

| Operation | Resident numerical state | Main work |
| --- | --- | --- |
| Exact profile/components | O(n + B) | One canonical-edge scan plus array reductions |
| Topology hierarchy | O(k + B), plus DuckDB budget | External ordering of q pairs, union-find, one weighted rollup per retained cut |
| Lookup index | O(n) mapped labels, bounded SQLite/batch cache | Stream node records and build disk indices |
| Original-node neighbors | Bounded result and mapped offset pages | Indexed ID lookup and a seek/read of at most the requested neighbors |
| Membership page | Bounded result | Indexed community/compact-ID range query |
| Portable report | At most 1,024 groups per level | Bounded layouts, matrices and JSON; no original-node browser objects |
| Export | O(B), plus optional DuckDB budget | Stream exact quotient nodes/pairs; do not expand weights into original edges |

## Components and degree profile

The component pass uses union-by-size and path compression over every canonical
edge. All nodes, including isolates, start as singleton sets. The resulting
component labels, sizes and edge counts are saved. Summed sizes must equal n and
summed degree volumes must equal 2m. Degrees, their histogram, mean, maximum and
isolate count are exact. Quantiles use NumPy's linear interpolation convention.
No triangle counts, centralities or shortest-path distributions are inferred
from this profile.

## Descriptive topology hierarchy

This is a hierarchy *over detected groups*, distinct from the detector itself.
For an external quotient edge between groups a and b with node populations
`s_a,s_b`, define the descriptive affinity:

```text
affinity(a,b) = edge_count(a,b) / sqrt(s_a * s_b)
```

Sort external pairs by descending affinity, then source/target ID, using external
sorting. Apply Kruskal-style union-find and save cuts at requested group counts.
This is single linkage on a normalized maximum spanning forest. A retained cut
is a genuine union of connected quotient regions; later cuts nest inside earlier
ones. Disconnected roots remain separate even if their count exceeds a requested
cap. Every cut is rolled up using original quotient weights, so internal edges,
cross-group edges, node population and degree volume are conserved.

The normalization is a descriptive choice, not a significance test or a
degree-corrected stochastic model. Single linkage can chain regions into a large
group and is sensitive to weak bridges. A hierarchy cut is not presented as a new
community-detection optimum, nor as evidence of real hierarchical organization.
Requested cuts do not guarantee balanced populations. A virtual browser overview
does not create graph edges between disconnected roots.

## Browser bounds and layout

Actual cuts of at most 1,024 groups are included in full, followed by the detected
groups when that count also fits. Large disconnected forests use an explicitly
flagged artificial `Other` display collection. They cannot be explored as if all
of those groups were a single detected community. Original-node membership and
neighbors remain available through bounded local queries.

Each cut uses the bounded weighted igraph layout, with its RNG seeded in an
isolated process so an embedding application's RNG is unaffected. Each level has an independent overview layout. Exact parent IDs and navigation
preserve the hierarchy without forcing fine groups into overlapping positions
near a large coarse parent. Distances remain layout-dependent. Stored
positions reproduce the report; exact recomputation depends on native library
versions/platform. Parallel NetworKit partitions may vary despite a fixed seed.

Network glyph area scales with population, with a disclosed 0.4-pixel minimum
radius for visibility. Network lines show a bounded strongest-weight set recomputed within the visible
region. All visible induced pairs remain in the matrix and ZIP export. Captions
disclose hidden link weight and edges crossing the view boundary. A matrix cell
on the diagonal counts each internal undirected edge twice, matching adjacency
and degree-volume conventions. A stored quotient diagonal counts it once.

The browser density layer accumulates population linearly with a fixed,
normalized Gaussian kernel on a 256×256 grid at aggregate positions. Its color
scale is `log1p` normalized within the view. Kernel support outside the current
camera is clipped. It is a qualitative layout-conditioned mass map, not an
embedding or density estimate of all original-node coordinates. Exact populations
are in tables/exports; the optional static raster mode exports raw integer grids.

## Bounded quality backends

The optional Leiden and NetworKit backends are limited to 100,000 nodes and
2,000,000 canonical edges, checked before materializing their graphs. These caps
are policy bounds, not a proof of memory usage on every installation. CluStRE is
an explicitly selected external streaming executable. The native default keeps
the original semi-external implementation and its documented limitations.

NetworKit runs in an isolated worker to contain its global thread/seed settings;
it uses PLM with refinement, recursive coarsening, gamma=`resolution`,
maxIter=`passes`, `par=balanced` and `turbo=True`. Leiden uses
RBConfigurationVertexPartition, `resolution_parameter=resolution` and
`n_iterations=passes`. These budgets have different meanings; equal flag values
do not make algorithm work or output quality equivalent. All final partitions
are evaluated using the common full-edge modularity implementation.
