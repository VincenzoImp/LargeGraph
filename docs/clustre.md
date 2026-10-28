# CluStRE integration

CluStRE is a published streaming graph clustering algorithm by Chhabra, Peretz
and Schulz (SEA 2025). The primary sources are the
[paper](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SEA.2025.11)
and [official source repository](https://github.com/KaHIP/CluStRE).

The native backend in this repository is a separate modularity local-moving
implementation. It does not inherit CluStRE's refinement methods or published
performance. To evaluate actual CluStRE, install the official binary. Its current
upstream build requirements include a C++20 compiler, CMake >=3.24 and MPI.
Follow the upstream installation instructions and archive the source commit.
Build with a conservative job count on an 8 GB machine; default `-j$(nproc)`
dependency builds can consume much more memory than running the algorithm.

The tested Linux build used upstream commit
`39a4e57c2de0bee45a2752597db502963a1536de`, MPICH 5.0.2 from its Python wheel,
and the following commands (no root/system MPI installation was needed):

```bash
uv sync --locked --extra images --extra leiden --extra validation --extra clustre-build
git clone https://github.com/KaHIP/CluStRE.git vendor/CluStRE
git -C vendor/CluStRE checkout 39a4e57c2de0bee45a2752597db502963a1536de
git -C vendor/CluStRE submodule update --init --recursive
PATH="$PWD/.venv/bin:$PATH" cmake -S vendor/CluStRE -B vendor/CluStRE/build \
  -DCMAKE_C_COMPILER="$PWD/.venv/bin/mpicc" \
  -DCMAKE_CXX_COMPILER="$PWD/.venv/bin/mpicxx" \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DBUILD_TESTING=OFF \
  -DKAGEN_USE_SPARSEHASH=OFF -DKAGEN_USE_CGAL=OFF
cmake --build vendor/CluStRE/build --target clustre --parallel 2
```

The disabled options concern the bundled KaGen generator, which this CSV-based
evaluation does not use. Keep `--extra clustre-build` when syncing this build
environment so its MPI libraries remain installed. The adapter appends a path
separator to `--output_path`: the upstream executable concatenates that prefix
directly with filenames. This behavior is covered by actual-binary tests:

```bash
CLUSTRE_BINARY="$PWD/vendor/CluStRE/build/clustre" .venv/bin/pytest -q
```

Use the same CSV and workspace for a direct comparison:

```bash
.venv/bin/python scripts/render_all.py data/demo/edges.csv \
  --nodes-file data/demo/nodes.csv --truth data/demo/nodes.csv \
  --work-dir work/demo --output runs/clustre-light \
  --backend clustre --clustre-binary /absolute/path/to/clustre \
  --clustre-mode light --memory 512MB --reference --hash-input

.venv/bin/python scripts/render_all.py data/demo/edges.csv \
  --nodes-file data/demo/nodes.csv --truth data/demo/nodes.csv \
  --work-dir work/demo --output runs/clustre-light-plus \
  --backend clustre --clustre-binary /absolute/path/to/clustre \
  --clustre-mode light_plus --memory 512MB --reference --hash-input
```

The adapter streams a METIS text file, which contains one adjacency line per
vertex and both directions for every edge. It records the binary SHA-256,
command, mode, explicit `--seed` and stdout/stderr log. Output must contain exactly one assignment
per vertex, with nonnegative labels. IDs are normalized to compact community
indices before exact aggregation. The temporary METIS graph is removed after
successful import; logs and original output assignments are retained.

Only `light` and `light_plus` are exposed, to avoid assuming that the refined
quotient graph fits in RAM. The adapter requires the standard resolution=1
objective; it does not guess undocumented flags. `--passes` controls the native
backend only; CluStRE controls its own passes. `--threads` sets OMP_NUM_THREADS
for the child process. DuckDB's memory limit does not constrain the CluStRE child.

CluStRE consumes a node stream, not arbitrary CSV edge order. Building that
stream is part of the end-to-end cost. Report conversion time, temporary disk,
child-process RSS and clustering time separately. Published upstream memory
figures must not be substituted for measurements on this workload and machine.

The upstream Python API that first builds an in-memory `Graph` is unsuitable for
this workload. The existence of a streaming algorithm behind an API does not
make its input construction out-of-core.
