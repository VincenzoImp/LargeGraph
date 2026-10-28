"""A topology-based single-linkage forest of the exact weighted quotient.

External edges are ordered by weight / sqrt(group size product), then endpoint
IDs. Union-by-size produces nested cuts of a maximum spanning forest. This is a
descriptive hierarchy, not an extra community-detection optimality guarantee.
Disconnected components are never merged merely to meet a display budget.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from numba import njit

from .artifacts import cached_directory, restart_partial
from .prepare import batches, copy_query, query_batches
from .profile import compress_roots, find_root
from .runtime import Monitor, Resources, cleanup_scratch, literal, read_json, signature, write_json


@njit(cache=True)
def merge_until(parents, sizes, a, b, start, remaining, target):
    cursor = start
    while cursor < len(a) and remaining > target:
        left, right = find_root(parents, a[cursor]), find_root(parents, b[cursor])
        cursor += 1
        if left == right:
            continue
        if sizes[left] < sizes[right] or (sizes[left] == sizes[right] and left > right):
            left, right = right, left
        parents[right] = left
        sizes[left] += sizes[right]
        remaining -= 1
    return cursor, remaining


def rollup(quotient: Path, mapping, out: Path, resources: Resources) -> None:
    """Aggregate *weights*, including diagonal edges, without expanding them."""
    out.mkdir(parents=True, exist_ok=True)
    nodes = pq.read_table(quotient / "nodes.parquet")
    k = int(mapping.max()) + 1
    sizes, volumes = np.zeros(k, dtype=np.uint64), np.zeros(k, dtype=np.uint64)
    np.add.at(sizes, mapping, nodes["node_count"].to_numpy())
    np.add.at(volumes, mapping, nodes["degree_volume"].to_numpy())
    schema = pa.schema([("source", pa.uint32()), ("target", pa.uint32()), ("weight", pa.uint64())])
    mapped = out / "mapped.parquet"
    with pq.ParquetWriter(mapped, schema, compression="zstd") as writer:
        for batch in batches(quotient / "edges.parquet", resources.batch_rows):
            a, b = (mapping[batch.column(i).to_numpy()] for i in (0, 1))
            writer.write_table(
                pa.table(
                    {
                        "source": np.minimum(a, b),
                        "target": np.maximum(a, b),
                        "weight": batch.column(2),
                    },
                    schema=schema,
                )
            )
    con = resources.connect(out)
    try:
        copy_query(
            con,
            f"SELECT source,target,sum(weight)::UBIGINT AS weight FROM read_parquet({literal(mapped)}) GROUP BY source,target ORDER BY source,target",
            out / "edges.parquet",
        )
    finally:
        con.close()
    internal = np.zeros(k, dtype=np.uint64)
    total = 0
    for batch in batches(out / "edges.parquet", resources.batch_rows):
        a, b, w = (batch.column(i).to_numpy() for i in range(3))
        diagonal = a == b
        internal[a[diagonal]] = w[diagonal]
        total += int(w.sum())
    pq.write_table(
        pa.table(
            {
                "community": np.arange(k, dtype=np.uint32),
                "node_count": sizes,
                "degree_volume": volumes,
                "internal_edges": internal,
                "external_degree": volumes - 2 * internal,
            }
        ),
        out / "nodes.parquet",
        compression="zstd",
    )
    original = read_json(quotient / "manifest.json")
    if total != original["edge_count"] or int(sizes.sum()) != original["node_count"]:
        raise RuntimeError("Hierarchy rollup lost graph mass")
    np.save(out / "mapping.npy", mapping)
    mapped.unlink()
    cleanup_scratch(out)
    write_json(
        out / "manifest.json",
        {
            "kind": "hierarchy-cut",
            "communities": k,
            "node_count": int(sizes.sum()),
            "edge_count": total,
            "internal_edges": int(internal.sum()),
            "external_edges": total - int(internal.sum()),
        },
    )


def build_hierarchy(quotient: Path, resources: Resources, targets=(16, 64, 256)) -> Path:
    targets = sorted(set(int(value) for value in targets), reverse=True)
    if not targets or any(value < 2 or value > 1024 for value in targets):
        raise ValueError("Hierarchy targets must be between 2 and 1024")
    config = {
        "quotient": read_json(quotient / "manifest.json")["config"],
        "targets": targets,
        "version": 1,
    }
    destination = quotient.parent / ("hierarchy-" + signature(config)[:20])
    with cached_directory(destination) as out:
        if out is None:
            return destination
        restart_partial(out)
        nodes = pq.read_table(quotient / "nodes.parquet")
        n = len(nodes)
        parents, sizes = np.arange(n, dtype=np.uint32), np.ones(n, dtype=np.uint32)
        remaining = n
        targets = [target for target in targets if target < n]
        cuts = []

        def save_cut(requested):
            compress_roots(parents)
            _, labels = np.unique(parents, return_inverse=True)
            labels = labels.astype(np.uint32)
            name = f"cut-{len(cuts)}"
            (out / name).mkdir()
            np.save(out / name / "mapping.npy", labels)
            cuts.append(
                {"directory": name, "requested": requested, "groups": int(labels.max()) + 1}
            )

        with Monitor(out) as monitor:
            con = resources.connect(out / "sort")
            try:
                edge_path, node_path = (
                    literal(quotient / "edges.parquet"),
                    literal(quotient / "nodes.parquet"),
                )
                query = f"SELECT e.source,e.target FROM read_parquet({edge_path}) e JOIN read_parquet({node_path}) a ON e.source=a.community JOIN read_parquet({node_path}) b ON e.target=b.community WHERE e.source<>e.target ORDER BY e.weight::DOUBLE/sqrt(a.node_count::DOUBLE*b.node_count::DOUBLE) DESC,e.source,e.target"
                with query_batches(con, query, resources.batch_rows) as reader:
                    for batch in reader:
                        if not targets:
                            break
                        a, b = (batch.column(i).to_numpy() for i in (0, 1))
                        cursor = 0
                        while targets and cursor < len(a):
                            cursor, remaining = merge_until(
                                parents, sizes, a, b, cursor, remaining, targets[0]
                            )
                            if remaining <= targets[0]:
                                save_cut(targets.pop(0))
                if targets:
                    # Preserve the forest, even if its component count exceeds a requested cap.
                    save_cut(targets[-1])
            finally:
                con.close()
                cleanup_scratch(out / "sort")
            if not cuts:
                save_cut(n)
            for cut in cuts:
                directory = out / cut["directory"]
                rollup(quotient, np.load(directory / "mapping.npy"), directory, resources)
        cuts.reverse()
        write_json(
            out / "manifest.json",
            {
                "kind": "hierarchy",
                "config": config,
                "cuts": cuts,
                "fine_groups": n,
                "method": "normalized maximum-spanning-forest single linkage",
                "disconnected_policy": "retain disconnected roots; a requested cap may be exceeded",
                "metrics": monitor.stats,
            },
        )
    return destination
