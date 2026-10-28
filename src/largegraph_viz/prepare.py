"""Canonical simple graphs, compact identifiers and disk-backed adjacency."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .runtime import (
    Monitor,
    Resources,
    artifact_directory,
    cleanup_scratch,
    environment,
    fingerprint,
    identifier,
    literal,
    read_json,
    resource_dict,
    signature,
    write_json,
)

LOG = logging.getLogger(__name__)
SCHEMA_VERSION = 1


def batches(path: Path, batch_rows: int = 250_000, columns=None):
    yield from pq.ParquetFile(path).iter_batches(batch_size=batch_rows, columns=columns)


def copy_query(con, query: str, path: Path, csv: bool = False):
    options = (
        "FORMAT CSV, HEADER true"
        if csv
        else "FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 122880"
    )
    con.execute(f"COPY ({query}) TO {literal(path)} ({options})")


def read_csv_query(path: Path, delimiter: str = ",") -> str:
    return (
        f"read_csv({literal(path)}, header=true, all_varchar=true, "
        f"delim={literal(delimiter)}, strict_mode=true, ignore_errors=false)"
    )


def prepare_graph(
    csv_path: Path,
    work_dir: Path,
    resources: Resources,
    source: str = "source",
    target: str = "target",
    delimiter: str = ",",
    nodes_path: Path | None = None,
    node_column: str = "node_id",
    hash_input: bool = False,
    ignore_extra_columns: bool = False,
) -> Path:
    inputs = {
        "edges": fingerprint(csv_path, hash_input),
        "nodes": fingerprint(nodes_path, hash_input) if nodes_path else None,
    }
    config = {
        "schema": SCHEMA_VERSION,
        "inputs": inputs,
        "source": source,
        "target": target,
        "delimiter": delimiter,
        "node_column": node_column,
        "ignore_extra_columns": ignore_extra_columns,
        "graph_contract": "undirected-unweighted-simple-drop-loops-deduplicate",
    }
    destination = work_dir.resolve() / ("prepared-" + signature(config)[:20])
    if (destination / "manifest.json").exists():
        LOG.info("Reusing %s", destination)
        return destination
    with (
        artifact_directory(destination) as out,
        Monitor(out, spill_dir=Path(resources.temp_dir) if resources.temp_dir else None) as monitor,
    ):
        con = resources.connect(out)
        try:
            relation = read_csv_query(csv_path.resolve(), delimiter)
            columns = [
                item[0] for item in con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
            ]
            if source == target or source not in columns or target not in columns:
                raise ValueError(
                    f"CSV must have distinct columns {source!r} and {target!r}; got {columns}"
                )
            if len(columns) != 2 and not ignore_extra_columns:
                raise ValueError(
                    "Extra CSV columns require --ignore-extra-columns; weighted/directed semantics are not inferred"
                )
            con.execute(
                f"CREATE TABLE raw AS SELECT {identifier(source)} AS s, {identifier(target)} AS t FROM {relation}"
            )
            invalid = con.execute(
                "SELECT count(*) FROM raw WHERE s IS NULL OR t IS NULL OR s = '' OR t = ''"
            ).fetchone()[0]
            if invalid:
                raise ValueError(f"CSV contains {invalid} missing/empty endpoints")
            raw_rows, loops = con.execute(
                "SELECT count(*), count(*) FILTER (WHERE s=t) FROM raw"
            ).fetchone()
            node_union = "SELECT s AS original_id FROM raw UNION SELECT t FROM raw"
            if nodes_path:
                nodes_relation = read_csv_query(nodes_path.resolve(), delimiter)
                node_id = identifier(node_column)
                invalid_nodes = con.execute(
                    f"SELECT count(*) FROM {nodes_relation} WHERE {node_id} IS NULL OR {node_id} = ''"
                ).fetchone()[0]
                if invalid_nodes:
                    raise ValueError("Node file contains missing/empty identifiers")
                node_union += f" UNION SELECT {node_id} FROM {nodes_relation}"
            con.execute(
                f"CREATE TABLE ids AS SELECT original_id, (row_number() OVER (ORDER BY original_id)-1)::UINTEGER AS node_id FROM ({node_union})"
            )
            n = con.execute("SELECT count(*) FROM ids").fetchone()[0]
            if not 0 < n < 2**32:
                raise ValueError("Graph must have between 1 and 2^32-1 nodes")
            copy_query(
                con, "SELECT node_id, original_id FROM ids ORDER BY node_id", out / "nodes.parquet"
            )
            # Separate blocking joins, then deduplication: do not stack every operator in one query.
            con.execute(
                "CREATE TABLE left_mapped AS SELECT ids.node_id AS s, raw.t FROM raw JOIN ids ON raw.s=ids.original_id WHERE raw.s<>raw.t"
            )
            con.execute("DROP TABLE raw")
            con.execute(
                "CREATE TABLE mapped AS SELECT least(s,ids.node_id)::UINTEGER AS source, greatest(s,ids.node_id)::UINTEGER AS target FROM left_mapped JOIN ids ON left_mapped.t=ids.original_id"
            )
            con.execute("DROP TABLE left_mapped")
            con.execute("DROP TABLE ids")
            con.execute("CREATE TABLE edges AS SELECT DISTINCT source,target FROM mapped")
            con.execute("DROP TABLE mapped")
            m = int(con.execute("SELECT count(*) FROM edges").fetchone()[0])
            copy_query(con, "SELECT * FROM edges", out / "edges.parquet")
            degrees = np.zeros(n, dtype=np.uint64)
            for batch in batches(out / "edges.parquet", resources.batch_rows):
                for col in (0, 1):
                    np.add.at(degrees, batch.column(col).to_numpy(), np.uint64(1))
            np.save(out / "degrees.npy", degrees)
            offsets = np.empty(n + 1, dtype=np.uint64)
            offsets[0] = 0
            np.cumsum(degrees, out=offsets[1:])
            np.save(out / "offsets.npy", offsets)
            # DuckDB sorts externally. Stream Arrow batches into a flat little-endian file.
            reader = con.execute(
                "SELECT target FROM (SELECT source,target FROM edges UNION ALL SELECT target AS source,source AS target FROM edges) ORDER BY source,target"
            ).fetch_record_batch(resources.batch_rows)
            with (out / "neighbors.u32").open("wb") as stream:
                for batch in reader:
                    batch.column(0).to_numpy().astype("<u4", copy=False).tofile(stream)
            if (out / "neighbors.u32").stat().st_size != 8 * m:
                raise RuntimeError(
                    "Adjacency length does not equal twice the number of unique edges"
                )
            if int(offsets[-1]) != 2 * m:
                raise RuntimeError("Degree sum does not equal 2m")
            manifest = {
                "kind": "prepared",
                "config": config,
                "nodes": n,
                "edges": m,
                "input_rows": int(raw_rows),
                "dropped_self_loops": int(loops),
                "dropped_duplicate_rows": int(raw_rows - loops - m),
                "isolated_nodes": int(np.count_nonzero(degrees == 0)),
                "resources": resource_dict(resources),
                "environment": environment(),
                "adjacency": {
                    "dtype": "little-endian uint32",
                    "index_base": 0,
                    "sorted_by": ["source", "target"],
                    "symmetric": True,
                },
                "passes": {
                    "csv_reads": 1,
                    "optional_hash_scan": hash_input,
                    "canonical_edge_scans": 2,
                    "external_sort": True,
                },
            }
        finally:
            con.close()
        cleanup_scratch(out)
        manifest["metrics"] = monitor.snapshot()
        write_json(out / "manifest.json", manifest)
    return destination


def neighbor_blocks(prepared: Path, max_entries: int = 2_000_000):
    """Bounded reads aligned with complete neighborhoods, including isolated vertices.

    RAM is O(max_entries + maximum degree), not O(number of edges). The flat
    adjacency file is deliberately not memory-mapped: sequential memmap traversal
    can inflate resident memory even if the algorithm only needs one block.
    """
    offsets = np.load(prepared / "offsets.npy")
    start, n = 0, len(offsets) - 1
    with (prepared / "neighbors.u32").open("rb") as stream:
        while start < n:
            limit = int(offsets[start]) + max_entries
            end = min(n, max(start + 1, int(np.searchsorted(offsets, limit, side="right")) - 1))
            count = int(offsets[end] - offsets[start])
            data = np.fromfile(stream, dtype="<u4", count=count)
            if len(data) != count:
                raise ValueError("Truncated adjacency file")
            yield start, end, offsets[start : end + 1] - offsets[start], data
            start = end


def export_metis(prepared: Path, destination: Path, max_entries: int = 2_000_000):
    manifest = read_json(prepared / "manifest.json")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", buffering=1024 * 1024) as stream:
        stream.write(f"{manifest['nodes']} {manifest['edges']}\n")
        for start, end, offsets, data in neighbor_blocks(prepared, max_entries):
            for local in range(end - start):
                neighbors = data[int(offsets[local]) : int(offsets[local + 1])]
                stream.write(" ".join(str(int(v) + 1) for v in neighbors) + "\n")
    temporary.replace(destination)


def write_assignments(path: Path, labels, batch_rows: int = 250_000):
    schema = pa.schema([("node_id", pa.uint32()), ("community", pa.uint32())])
    with pq.ParquetWriter(path, schema, compression="zstd") as writer:
        for begin in range(0, len(labels), batch_rows):
            end = min(begin + batch_rows, len(labels))
            writer.write_table(
                pa.table(
                    {
                        "node_id": np.arange(begin, end, dtype=np.uint32),
                        "community": labels[begin:end],
                    },
                    schema=schema,
                )
            )
