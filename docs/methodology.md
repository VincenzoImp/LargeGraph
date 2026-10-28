# Methodology

## Research question and interpretation

The software supports visual inspection of connectivity at scales where individual
vertices cannot be distinguished. Its claims concern reproducible transformations,
exact aggregated counts and measured resource usage. The appearance of a two-dimensional
projection is not independent evidence of community structure or of a natural
geometric shape. Community, matrix and raster views share a partition and therefore
are complementary representations, not independent replications.

## Graph contract and preparation

Let G=(V,E) be an undirected, unweighted, simple graph with n vertices and m edges.
Identifiers are mapped bijectively to compact unsigned 32-bit integers. Unordered
pairs are canonicalized as (min(u,v),max(u,v)). Self-loops are removed and repeated
pairs are collapsed. Both operations are counted. Vertices mentioned only in a
self-loop remain in V. An optional node table adds isolates.

The CSV is parsed into a persistent DuckDB workspace. String-to-integer joins,
deduplication and adjacency sorting are staged so their intermediates can spill
to disk. Canonical edges are stored as Parquet; the symmetric adjacency targets
are written as little-endian uint32 values ordered by source then target. Offset
and degree arrays use uint64. Every adjacency scan reads bounded blocks aligned
with complete neighborhoods. The largest neighborhood may exceed the requested
block size; this exception is explicit and costs O(maximum degree), not O(m).

The input is read once for ingestion, plus an optional complete SHA-256 pass.
External sorting and joins may make multiple internal disk passes. They must not
be described as a single streaming pass or as O(m) CPU work. Sorting has external
sorting I/O complexity; runtime depends heavily on spill volume and disk speed.

## Community detection

The default backend implements sequential modularity local moves with disk-backed
adjacency. It is an implementation of a modularity local-moving rule, not an
implementation of CluStRE, Leiden, or their guarantees. Initially every vertex is
a singleton. For each vertex i, temporarily remove its degree from its current
community volume. Among neighboring communities and its current community, choose
a strictly better score:

    score(i,C) = k(i,C) - gamma * degree(i) * volume(C)/(2m).

Only the current vertex is removed when volumes are evaluated. Equal scores retain
the first currently best assignment; only strict gains cause moves. Sequential
passes reuse the same adjacency order and stop on no moves or a pass cap. There
is no singleton-splitting, coarse optimization or claim of a global optimum.
The quality is checked using the exact full-graph objective after every pass:

    Q_gamma = sum_C [ internal_edges(C)/m - gamma*(volume(C)/(2m))^2 ].

The state consists of O(n) arrays for assignments, volumes, scores and marks, plus
a touched-community buffer of maximum-degree size. Each moving pass takes O(n+m)
work; its quality evaluation is another O(n+m) scan. Numba compiles the inner loop.
The first run includes JIT cost. Degree heterogeneity, order effects, resolution
limits and local minima affect results. Neither internal connectivity nor recovery
of planted blocks is guaranteed. Report results and failures across scenarios.

An alternative invokes the actual published CluStRE executable in `light` or
`light_plus` mode on a METIS file exported from exactly the prepared graph. Its
binary hash, command, logs and assignments are retained. This is an optional
backend, not an implicit substitution. The in-memory Python `stream_cluster(g)`
API is deliberately not used because constructing g would require the full graph.
The adapter does not expose unsupported objective parameters.

## Exact quotient graph

For a fixed partition c:V→{0,...,K-1}, the quotient table stores

    W_ab = number of original edges with endpoint communities {a,b}, a <= b.

Internal edges occupy the diagonal once. Thus sum_(a<=b) W_ab=m and the total
degree volume is 2m. Community sizes, internal edges, external degree and degree
volumes are exported. Full pair counts are aggregated externally, even if the
quotient is too large for RAM. Small K is never assumed for this stage.

For display cap H, retain the H-1 largest communities when K>H and collect the
tail into an explicitly artificial `Other`. All node and edge masses are retained.
The top prefixes make reductions at different H nested. `Other` is not a detected
community and its apparent cohesion or position is not interpretable as such.
Full fine assignments and quotient tables remain available for subsequent work.

## Node-link view

Compute coordinates only for the bounded display graph. Candidate engines are
Graphviz sfdp (Hu's multilevel force-directed method) and igraph's compiled
Fruchterman–Reingold layout. The initial seed and actual engine are recorded.
Raw edge weights are transformed with log(1+w) for layout and line width.
Point area is proportional to vertex count; its scale adapts to the number of
display groups, and an explicit size legend is shown. Colors are obtained from
a stable hash of display identifiers, independently of group size. They identify display groups;
they are not categorical labels inferred independently of the partition. IDs
and colors do not establish group identity across different detection runs.

Only the strongest display links may be rendered, with the omitted raw weight
reported. The full weighted display table is exported and the exact quotient is
never filtered. Groups with no visible links can still have many unshown links;
their apparent isolation is not evidence of disconnection. Distances, orientation, overlaps and apparent gaps depend on the
layout and are not measurements of graph distance.

## Matrix view

Define symmetric adjacency mass A with A_ab=W_ab for a<b, A_ba=W_ab, and
A_aa=2W_aa. Row sums equal degree volumes and sum A=2m. Render three matrices:

1. Adjacency mass with a logarithmic color scale (zeros masked).
2. Edge density A_ab/(n_a*n_b), using n_a*(n_a-1) on the diagonal.
3. Stabilized degree-adjusted enrichment log2((A_ab+1)/(E_ab+1)), where
   E_ab=volume(a)*volume(b)/(2m).

The expectation is the standard configuration-model adjacency expectation used
in modularity, not an exact finite simple-graph expectation. Enrichment is a
descriptive ratio, not a statistical test or p-value. A pseudocount of one is
explicit. Sizes of one and zero-edge graphs are handled without division by zero.
Rows are ordered by group size for a shared mapping across figures.

## Raster view

Without supplied coordinates, put each bounded display group's vertex mass at
its layout location. This is an aggregated map, not a layout of n individual
vertices. Save exact uint64 node counts per pixel before display smoothing.
Each retained inter-group link contributes its raw edge weight once to every
traversed pixel. Summing that edge raster does not give m: long lines cover more
pixels. Internal edges are excluded from the line layer and remain in quotient
diagonals. Filtered external weight is reported. Gaussian smoothing and log
shading are visual operations only; exact arrays are saved separately. Smoothing
does not establish physical density or remove uncertainty from the layout.

With supplied coordinates, require an N×2 numeric `.npy` array in prepared compact
node order. Two bounded scans find the extent and accumulate all node counts.
There is no detection, interpolation, invented geometry or smoothing in this mode.
An edgeless graph and coincident coordinates remain valid inputs.

## Synthetic model

Sample unequal positive block sizes using normalized lognormal proportions with
integer remainder allocation. Randomly permute vertex identifiers independently
of block labels. Sample positive degree propensities theta from 1+Pareto(alpha-1),
capped at 100, and normalize them separately within each block.

An ordered block pair (a,b) is drawn with probability P_ab saved as a numerical
matrix. Endpoints are independent draws proportional to theta in their blocks.
The default matrix puts (1-mu)*n_a/n on diagonal a and distributes off-diagonal
mass mu proportional to n_a*n_b. The bridge scenario restricts the off-diagonal
support to a cycle of blocks. The weak scenario uses mu>=0.65. The core–periphery
scenario uses affinity 1 for core–core, 0.6 for core–periphery and 0.03 otherwise,
multiplied by block-size products and normalized. The null uses only block-size
products; planted labels then do not alter pair affinity.

Convert each proposed pair to unordered form and reject loops. Deduplicate on
disk while retaining the first arrival sequence of every pair. Keep the first m
unique arrivals. If necessary, generate additional proposals and reaggregate,
up to a convergence cap. This defines a fixed-m weighted sampling-without-
replacement simple graph in the degree-corrected block-model family. It is **not**
the canonical independent Bernoulli or Poisson DC-SBM. Proposals, attempts, block
probabilities, sizes, seed and realized retained edge count are recorded.
Reproducibility requires the same seed, software and batch size. Realized degrees
and mixing can differ after conditioning on simplicity. Local triadic closure,
overlapping memberships, realistic temporal dynamics and a prescribed clustering
coefficient are not enforced. They must not be claimed from visual resemblance.

## Scope of scientific evidence

Conservation tests establish transformation correctness, not community accuracy.
Ground-truth ARI/AMI, a bounded Leiden reference, order sensitivity, multiple seeds
and a no-planted-affinity control assess different failure modes. A strong
modularity value alone is insufficient, especially given modularity's resolution
limit. A small run fitting in RAM does not validate large-scale memory behavior;
that requires a verified spill experiment and measured target-scale execution.

ARI is evaluated on all available nodes. Exact AMI is limited to 100,000 nodes
and one million truth-group/detected-group pairs
because its expected-mutual-information calculation can be expensive for large
contingency tables. Larger reports explicitly mark AMI as not run, rather than
silently substituting a sampled statistic.

Primary sources and tool documentation are collected in `references.bib`.
