# Third-party notices

The project's original Python/JavaScript/HTML source is licensed under MIT, as
specified in [LICENSE](LICENSE). This does not relicense its dependencies.
Distributions of dependencies and their bundled native libraries carry their
own license files and notices. The project wheel does not vendor their code.

| Component | Upstream license / source |
| --- | --- |
| NumPy | [BSD and bundled notices](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| DuckDB | [MIT](https://github.com/duckdb/duckdb/blob/main/LICENSE) |
| Apache Arrow / PyArrow | [Apache-2.0 and bundled notices](https://github.com/apache/arrow/blob/main/LICENSE.txt) |
| Numba | [BSD](https://github.com/numba/numba/blob/main/LICENSE) |
| llvmlite / LLVM | [BSD / Apache-2.0 with LLVM exception](https://github.com/numba/llvmlite/blob/main/LICENSE) |
| psutil | [BSD-3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| python-igraph / igraph | [GPL](https://github.com/igraph/python-igraph) |
| Matplotlib (optional) | [Matplotlib license and bundled notices](https://matplotlib.org/stable/project/license.html) |
| SciPy (optional) | [BSD and bundled notices](https://github.com/scipy/scipy/blob/main/LICENSE.txt) |
| leidenalg (optional) | [GPL-3.0-or-later](https://github.com/vtraag/leidenalg/blob/main/LICENSE) |
| scikit-learn (optional) | [BSD-3-Clause](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING) |
| CluStRE (external, optional) | [Upstream source and license](https://github.com/KaHIP/CluStRE) |

This is an attribution inventory, not a replacement for the exact license texts
in installed distributions. In particular, the complete dependency stack is not
MIT-only. If you redistribute an application together with GPL components,
review the corresponding distribution obligations. Preserve upstream license
files and any notices from bundled codecs, fonts, BLAS and LLVM builds.

The bundled 2,000-node demo and archived full-scale synthetic graph were generated
by this project. Real-world datasets, when used in benchmarks, retain their
original terms and are linked rather than silently relicensed.
