# Dependency inventory

The base installation has **six direct runtime dependencies**. It uses their
compiled engines rather than reimplementing database storage, numerical arrays,
columnar I/O or a force-directed layout in Python. Python transitive dependencies
and native libraries inside wheels are additional dependencies; their exact
versions depend on platform and Python version. The uv lockfile records those
variants and also includes contributor-only packages.

| Base package | Job | Why keep it |
| --- | --- | --- |
| NumPy | Compact arrays, reductions and bounded numeric buffers | Avoids Python-object-per-node memory overhead |
| DuckDB | External joins, deduplication, sorting and aggregation | Supplies the disk-backed relational engine |
| PyArrow | Batched Parquet I/O | Preserves reusable typed data without loading all edges |
| Numba | Compiled streaming moves and union-find | Runs numerical edge loops outside the Python interpreter |
| psutil | Resource monitoring and available-memory checks | Measures process-tree RSS and system resources |
| igraph | Bounded summary layout | Uses compiled graph layout on at most 1,024 visible groups |

Optional runtime extras:

- `images`: Matplotlib and SciPy for raster/vector figures and Gaussian smoothing.
- `leiden`: leidenalg for a bounded quality backend/reference.
- `networkit`: NetworKit for bounded parallel Louvain on Linux/macOS.
- `validation`: scikit-learn for adjusted mutual information. ARI and exact
  conservation checks do not require it.
- `clustre-build`: Linux mpich build dependency. CluStRE itself is an external,
  explicitly selected executable with pinned upstream source instructions.

`setuptools` is a build dependency. `pytest`, Ruff, mypy, build, Twine and coverage
are in the contributor `dev` group. Playwright/Chromium are in the `browser`
group. The `networkit` extra also serves controlled comparisons. None
of these contributor tools is required by an installed base wheel. Node/npm were used only to
format the HTML source during development; the delivered viewer has no JavaScript
package dependency, CDN, build step or network requirement.

Optional system tools are Graphviz `sfdp` for an alternative layout and Linux
systemd/cgroup v2 for enforced resource experiments. The default bounded layout
does not require Graphviz. Standard SQLite and the HTTP server come from Python.

Our source implements graph preparation/recovery orchestration, the native
streaming heuristic, exact quotient construction, profiles, the hierarchy,
budget estimates, query index, report specification and browser interaction.
CluStRE, Leiden, igraph layout, SQL execution, Parquet codecs and numerical/JIT
engines are third-party work. Their method papers and licenses remain relevant.

## Inspect your installation

```bash
largegraph doctor
uv tree --locked --no-dev
```

The installed-base dependency closure is the meaningful runtime count. Counting
all entries in `uv.lock` also counts tests, build tools, optional features and
platform alternatives. Package installation size is not resident memory usage.
See [third-party notices](../THIRD_PARTY_NOTICES.md) for upstream licenses.
