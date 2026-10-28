"""Exact quotient counts on disk, with separately bounded display reductions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .artifacts import cached_directory, restart_partial
from .prepare import batches, copy_query, query_batches
from .runtime import (
    Monitor,
    Resources,
    cleanup_scratch,
    environment,
    literal,
    read_json,
    signature,
    write_json,
)


def aggregate_graph(prepared: Path, clustering: Path, resources: Resources):
    config = {
        "prepared": read_json(prepared / "manifest.json")["config"],
        "clustering": read_json(clustering / "manifest.json")["config"],
        "version": 2,
    }
    destination = prepared.parent / ("quotient-" + signature(config)[:20])
    with cached_directory(destination) as out:
        if out is None:
            return destination
        restart_partial(out)
        with Monitor(
            out, spill_dir=Path(resources.temp_dir) if resources.temp_dir else None
        ) as monitor:
            labels = np.load(clustering / "labels.npy")
            degrees = np.load(prepared / "degrees.npy")
            k = int(labels.max()) + 1
            sizes = np.bincount(labels, minlength=k).astype(np.uint64)
            volumes = np.zeros(k, dtype=np.uint64)
            np.add.at(volumes, labels, degrees)
            schema = pa.schema([("source", pa.uint32()), ("target", pa.uint32())])
            mapped_path = out / "mapped.parquet"
            with pq.ParquetWriter(mapped_path, schema, compression="zstd") as writer:
                for batch in batches(prepared / "edges.parquet", resources.batch_rows):
                    a, b = (labels[batch.column(i).to_numpy()] for i in (0, 1))
                    writer.write_table(
                        pa.table(
                            {"source": np.minimum(a, b), "target": np.maximum(a, b)}, schema=schema
                        )
                    )
            con = resources.connect(out)
            try:
                con.execute(
                    f"CREATE TABLE quotient AS SELECT source,target,count(*)::UBIGINT AS weight FROM read_parquet({literal(mapped_path)}) GROUP BY source,target"
                )
                copy_query(con, "SELECT * FROM quotient", out / "edges.parquet")
                total, internal = con.execute(
                    "SELECT coalesce(sum(weight),0),coalesce(sum(weight) FILTER (WHERE source=target),0) FROM quotient"
                ).fetchall()[0]
                internal_counts = np.zeros(k, dtype=np.uint64)
                with query_batches(
                    con,
                    "SELECT source,weight FROM quotient WHERE source=target",
                    resources.batch_rows,
                ) as reader:
                    for batch in reader:
                        internal_counts[batch.column(0).to_numpy()] = batch.column(1).to_numpy()
                nodes = pa.table(
                    {
                        "community": np.arange(k, dtype=np.uint32),
                        "node_count": sizes,
                        "degree_volume": volumes,
                        "internal_edges": internal_counts,
                        "external_degree": volumes - 2 * internal_counts,
                    }
                )
                pq.write_table(nodes, out / "nodes.parquet", compression="zstd")
                copy_query(
                    con,
                    f"SELECT * FROM read_parquet({literal(out / 'nodes.parquet')})",
                    out / "nodes.csv",
                    csv=True,
                )
            finally:
                con.close()
            mapped_path.unlink()
            cleanup_scratch(out)
            m = read_json(prepared / "manifest.json")["edges"]
            if int(total) != m or int(sizes.sum()) != len(labels) or int(volumes.sum()) != 2 * m:
                raise RuntimeError("Aggregation conservation failed")
        write_json(
            out / "manifest.json",
            {
                "kind": "quotient",
                "config": config,
                "communities": k,
                "node_count": len(labels),
                "edge_count": m,
                "internal_edges": int(internal),
                "external_edges": int(total - internal),
                "conservation": {"nodes": True, "edges": True, "degree_volume": True},
                "diagonal_convention": "One stored diagonal weight per internal undirected edge; degree counts it twice.",
                "metrics": monitor.stats,
                "environment": environment(),
            },
        )
    return destination


def display_reduction(quotient: Path, max_groups: int, resources: Resources):
    """Keep the largest groups; explicitly collect the tail in an artificial Other.

    Fine quotient edges always stay on disk. Only a bounded dense display matrix
    is resident, so a quotient as large as the original graph is still safe.
    Prefix selections are nested display caps, not a topology-based hierarchy.
    """
    if not 2 <= max_groups <= 1024:
        raise ValueError("max_groups must be between 2 and 1024")
    nodes = pq.read_table(quotient / "nodes.parquet")
    sizes = nodes["node_count"].to_numpy()
    volumes = nodes["degree_volume"].to_numpy()
    k = len(sizes)
    order = np.lexsort((np.arange(k), -sizes.astype(np.int64)))
    count = min(k, max_groups)
    mapping = np.empty(k, dtype=np.uint32)
    other = k > max_groups
    kept = count - 1 if other else count
    mapping.fill(count - 1)
    mapping[order[:kept]] = np.arange(kept, dtype=np.uint32)
    display_sizes = np.zeros(count, dtype=np.uint64)
    display_volumes = np.zeros(count, dtype=np.uint64)
    np.add.at(display_sizes, mapping, sizes)
    np.add.at(display_volumes, mapping, volumes)
    weights = np.zeros((count, count), dtype=np.uint64)
    for batch in batches(quotient / "edges.parquet", resources.batch_rows):
        a, b = (mapping[batch.column(i).to_numpy()] for i in (0, 1))
        np.add.at(weights, (np.minimum(a, b), np.maximum(a, b)), batch.column(2).to_numpy())
    names = [f"C{int(v)}" for v in order[:kept]]
    if other:
        names.append(f"Other ({k - kept:,} communities)")
    return {
        "mapping": mapping,
        "sizes": display_sizes,
        "volumes": display_volumes,
        "weights": weights,
        "names": names,
        "artificial_other": other,
        "retained_communities": order[:kept],
        "all_communities": k,
    }
