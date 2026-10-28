"""Exact structural profiles with O(nodes + batch) memory and one edge scan."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from numba import njit

from .artifacts import cached_directory, restart_partial
from .prepare import batches, write_assignments
from .runtime import Monitor, Resources, read_json, signature, write_json


@njit(cache=True)
def find_root(parents, node):
    while parents[node] != node:
        parents[node] = parents[parents[node]]
        node = parents[node]
    return node


@njit(cache=True)
def union_edges(parents, sizes, sources, targets):
    for i in range(len(sources)):
        left = find_root(parents, sources[i])
        right = find_root(parents, targets[i])
        if left == right:
            continue
        if sizes[left] < sizes[right] or (sizes[left] == sizes[right] and left > right):
            left, right = right, left
        parents[right] = left
        sizes[left] += sizes[right]


@njit(cache=True)
def compress_roots(parents):
    for i in range(len(parents)):
        parents[i] = find_root(parents, i)


def profile_graph(prepared: Path, resources: Resources) -> Path:
    """Count all connected components, including isolates; no sampled statistics."""
    meta = read_json(prepared / "manifest.json")
    config = {"prepared": meta["config"], "version": 2}
    destination = prepared.parent / ("profile-" + signature(config)[:20])
    with cached_directory(destination) as out:
        if out is None:
            return destination
        restart_partial(out)
        with Monitor(out) as monitor:
            n, m = meta["nodes"], meta["edges"]
            parents = np.arange(n, dtype=np.uint32)
            sizes = np.ones(n, dtype=np.uint32)
            for batch in batches(prepared / "edges.parquet", resources.batch_rows):
                union_edges(parents, sizes, batch.column(0).to_numpy(), batch.column(1).to_numpy())
            compress_roots(parents)
            _, inverse, counts = np.unique(parents, return_inverse=True, return_counts=True)
            labels = inverse.astype(np.uint32)
            np.save(out / "components.npy", labels)
            write_assignments(
                out / "components.parquet", labels, resources.batch_rows, column="component"
            )
            degrees = np.load(prepared / "degrees.npy")
            component_volumes = np.zeros(len(counts), dtype=np.uint64)
            np.add.at(component_volumes, labels, degrees)
            pq.write_table(
                pa.table(
                    {
                        "component": np.arange(len(counts), dtype=np.uint32),
                        "node_count": counts.astype(np.uint64),
                        "edge_count": component_volumes // 2,
                    }
                ),
                out / "component_sizes.parquet",
                compression="zstd",
            )
            values, frequencies = np.unique(degrees, return_counts=True)
            pq.write_table(
                pa.table({"degree": values, "nodes": frequencies}), out / "degree_histogram.parquet"
            )
            if int(component_volumes.sum()) != 2 * m or int(counts.sum()) != n:
                raise RuntimeError("Component conservation failed")
            stats = {
                "nodes": n,
                "edges": m,
                "components": len(counts),
                "largest_component_nodes": int(counts.max()),
                "largest_component_fraction": float(counts.max() / n),
                "isolated_nodes": int(np.count_nonzero(degrees == 0)),
                "mean_degree": 2 * m / n,
                "max_degree": int(degrees.max()),
                "degree_quantiles": dict(
                    zip(
                        ["0", "25", "50", "75", "90", "99", "100"],
                        np.percentile(degrees, [0, 25, 50, 75, 90, 99, 100]).tolist(),
                        strict=True,
                    )
                ),
                "edge_density": 2 * m / (n * (n - 1)) if n > 1 else 0,
                "statistics": "exact counts; quantiles use NumPy linear interpolation",
            }
            write_json(out / "profile.json", stats)
        write_json(
            out / "manifest.json", {"kind": "profile", "config": config, "metrics": monitor.stats}
        )
    return destination
