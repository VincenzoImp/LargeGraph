"""Disk-indexed ID lookup and bounded random-access neighborhood inspection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from .artifacts import cached_directory, restart_partial
from .prepare import batches
from .runtime import Monitor, Resources, read_json, signature, write_json


def build_index(prepared: Path, clustering: Path, profile: Path, resources: Resources) -> Path:
    config = {
        "prepared": read_json(prepared / "manifest.json")["config"],
        "clustering": read_json(clustering / "manifest.json")["config"],
        "version": 1,
    }
    destination = prepared.parent / ("index-" + signature(config)[:20])
    with cached_directory(destination) as out:
        if out is None:
            return destination
        restart_partial(out)
        with Monitor(out) as monitor:
            labels = np.load(clustering / "labels.npy", mmap_mode="r")
            components = np.load(profile / "components.npy", mmap_mode="r")
            con = sqlite3.connect(out / "lookup.sqlite")
            try:
                con.execute("PRAGMA cache_size=-16384")
                con.execute("PRAGMA temp_store=FILE")
                con.execute(
                    "CREATE TABLE nodes(node_id INTEGER PRIMARY KEY, original_id TEXT NOT NULL UNIQUE, community INTEGER NOT NULL, component INTEGER NOT NULL)"
                )
                for batch in batches(prepared / "nodes.parquet", min(resources.batch_rows, 50_000)):
                    ids, names = batch.column(0).to_numpy(), batch.column(1).to_pylist()
                    con.executemany(
                        "INSERT INTO nodes VALUES(?,?,?,?)",
                        (
                            (int(node), name, int(labels[node]), int(components[node]))
                            for node, name in zip(ids, names, strict=True)
                        ),
                    )
                    con.commit()
                con.execute("CREATE INDEX community_nodes ON nodes(community,node_id)")
                con.execute("CREATE INDEX component_nodes ON nodes(component,node_id)")
                con.commit()
            finally:
                con.close()
        write_json(
            out / "manifest.json",
            {"kind": "lookup-index", "config": config, "metrics": monitor.stats},
        )
    return destination


def connect_index(index: Path):
    # URI is constructed from a resolved URI so '?' and '#' in paths are escaped.
    con = sqlite3.connect((index / "lookup.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def neighbors(prepared: Path, index: Path, node: str, limit: int = 100) -> dict:
    """Return the first neighbors in compact-ID order, with an explicit total."""
    if not 1 <= limit <= 10_000:
        raise ValueError("limit must be between 1 and 10,000")
    with connect_index(index) as con:
        row = con.execute("SELECT * FROM nodes WHERE original_id=?", (node,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown original node ID: {node!r}")
        offsets = np.load(prepared / "offsets.npy", mmap_mode="r")
        compact = row["node_id"]
        start, stop = int(offsets[compact]), int(offsets[compact + 1])
        count = min(limit, stop - start)
        with (prepared / "neighbors.u32").open("rb") as stream:
            stream.seek(4 * start)
            ids = np.fromfile(stream, dtype="<u4", count=count)
        if len(ids) != count:
            raise ValueError("Truncated adjacency file")
        records = []
        if count:
            placeholders = ",".join("?" for _ in ids)
            records = [
                dict(value)
                for value in con.execute(
                    f"SELECT * FROM nodes WHERE node_id IN ({placeholders}) ORDER BY node_id",
                    [int(value) for value in ids],
                )
            ]
        return {
            "node": dict(row),
            "degree": stop - start,
            "returned": len(records),
            "truncated": stop - start > count,
            "order": "compact node ID (lexicographic original ID), not importance",
            "neighbors": records,
        }


def members(index: Path, community: int, limit: int = 100, after: int = -1) -> dict:
    if community < 0 or not 1 <= limit <= 10_000 or after < -1:
        raise ValueError("Invalid community, cursor or limit")
    with connect_index(index) as con:
        records = [
            dict(row)
            for row in con.execute(
                "SELECT * FROM nodes WHERE community=? AND node_id>? ORDER BY node_id LIMIT ?",
                (community, after, limit + 1),
            )
        ]
    more = len(records) > limit
    records = records[:limit]
    return {
        "community": community,
        "members": records,
        "has_more": more,
        "next_after": records[-1]["node_id"] if records and more else None,
    }
