"""Topology conservation, concurrent cache reuse and loopback-only queries."""

import http.client
import json
import subprocess
import sys
import threading

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from largegraph_viz import Resources, analyze
from largegraph_viz.hierarchy import build_hierarchy
from largegraph_viz.layout import layout
from largegraph_viz.runtime import read_json, write_json
from largegraph_viz.server import create_server


def test_hierarchy_is_nested_and_preserves_disconnected_roots(tmp_path):
    quotient = tmp_path / "quotient"
    quotient.mkdir()
    sources = np.array([i for i in range(63) if i % 16 != 15], dtype=np.uint32)
    targets = sources + 1
    weights = np.arange(1, len(sources) + 1, dtype=np.uint64)
    volumes = np.zeros(64, dtype=np.uint64)
    np.add.at(volumes, sources, weights)
    np.add.at(volumes, targets, weights)
    pq.write_table(
        pa.table({"source": sources, "target": targets, "weight": weights}),
        quotient / "edges.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "community": np.arange(64, dtype=np.uint32),
                "node_count": np.ones(64, dtype=np.uint64),
                "degree_volume": volumes,
            }
        ),
        quotient / "nodes.parquet",
    )
    write_json(
        quotient / "manifest.json",
        {
            "config": {"fixture": "four weighted chains"},
            "communities": 64,
            "node_count": 64,
            "edge_count": int(weights.sum()),
        },
    )
    hierarchy = build_hierarchy(
        quotient, Resources(memory="128MB", threads=1, batch_rows=7), (2, 8, 16)
    )
    meta = read_json(hierarchy / "manifest.json")
    assert [cut["groups"] for cut in meta["cuts"]] == [4, 8, 16]
    coarse = None
    for cut in meta["cuts"]:
        directory = hierarchy / cut["directory"]
        labels = np.load(directory / "mapping.npy")
        assert len(np.unique(labels)) == cut["groups"]
        for group in np.unique(labels):
            assert len(np.unique(np.flatnonzero(labels == group) // 16)) == 1
            if coarse is not None:
                assert len(np.unique(coarse[labels == group])) == 1
        coarse = labels
        assert int(pq.read_table(directory / "edges.parquet")["weight"].to_numpy().sum()) == int(
            weights.sum()
        )
        assert int(pq.read_table(directory / "nodes.parquet")["node_count"].to_numpy().sum()) == 64


def test_two_processes_build_one_immutable_artifact(tmp_path):
    code = """
import sys,time
from pathlib import Path
from largegraph_viz.artifacts import cached_directory
from largegraph_viz.runtime import write_json
root=Path(sys.argv[1])
with cached_directory(root/'artifact') as out:
    if out is not None:
        with (root/'builders').open('a') as f: f.write('builder\\n')
        time.sleep(.2)
        write_json(out/'manifest.json',{'done':True})
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    for process in processes:
        _, error = process.communicate(timeout=30)
        assert process.returncode == 0, error
    assert (tmp_path / "builders").read_text().splitlines() == ["builder"]


def test_layout_is_seeded_without_mutating_process_rng():
    import random

    generator = np.random.default_rng(17)
    weights = np.triu((generator.random((25, 25)) < 0.2).astype(np.uint64), 1)
    state = random.getstate()
    first, _ = layout(weights, seed=9, engine="igraph")
    second, _ = layout(weights, seed=9, engine="igraph")
    np.testing.assert_array_equal(first, second)
    assert random.getstate() == state


def test_optional_networkit_backend_runs_in_a_bounded_worker(tmp_path):
    pytest.importorskip("networkit")
    from largegraph_viz import AnalysisOptions

    edges = tmp_path / "edges.csv"
    edges.write_text("source,target\na,b\nb,c\nc,a\nx,y\ny,z\nz,x\nc,x\n")
    result = analyze(
        edges,
        tmp_path / "run",
        options=AnalysisOptions(backend="networkit"),
        resources=Resources(memory="128MB", threads=1),
    )
    meta = read_json(result.clustering / "manifest.json")
    assert "NetworKit" in meta["algorithm"]
    assert meta["modularity"] > 0.3
    assert read_json(result.report.parent / "validation/validation.json")["all_checks_pass"]


def test_local_server_queries_and_rejects_unknown_hosts(tmp_path):
    edges = tmp_path / "edges.csv"
    edges.write_text("source,target\n001,alice\nalice,bob\n")
    result = analyze(edges, tmp_path / "run", resources=Resources(memory="128MB", threads=1))
    server = create_server(result.output, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request("GET", "/api/neighbors?node=001&limit=1")
        response = connection.getresponse()
        assert response.status == 200
        value = json.loads(response.read())
        assert value["degree"] == 1 and value["neighbors"][0]["original_id"] == "alice"
        connection.request("GET", "/api/neighbors?node=001&limit=999999")
        response = connection.getresponse()
        assert response.status == 400
        response.read()
        connection.request("GET", "/../../analysis.json")
        response = connection.getresponse()
        assert response.status == 404
        response.read()
        connection.request("GET", "/api/neighbors?node=001", headers={"Host": "untrusted.example"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
