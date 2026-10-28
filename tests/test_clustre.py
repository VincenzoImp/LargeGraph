"""Optional integration against the actual upstream executable, never a mock."""

import os
from pathlib import Path

import numpy as np
import pytest

from largegraph_viz.aggregate import aggregate_graph
from largegraph_viz.cluster import cluster_graph
from largegraph_viz.prepare import prepare_graph
from largegraph_viz.runtime import Resources, read_json


@pytest.mark.skipif(
    not os.environ.get("CLUSTRE_BINARY"),
    reason="Set CLUSTRE_BINARY to test the upstream executable",
)
@pytest.mark.parametrize("mode", ["light", "light_plus"])
def test_upstream_modes_and_output_directory(tmp_path, mode):
    fixture = Path(__file__).resolve().parents[1] / "examples"
    resources = Resources(memory="128MB", threads=1, batch_rows=3)
    prepared = prepare_graph(
        fixture / "small_edges.csv",
        tmp_path / "work",
        resources,
        nodes_path=fixture / "small_nodes.csv",
    )
    clustering = cluster_graph(
        prepared,
        resources,
        backend="clustre",
        clustre_binary=Path(os.environ["CLUSTRE_BINARY"]),
        clustre_mode=mode,
        seed=17,
    )
    labels = np.load(clustering / "labels.npy")
    assert labels.ndim == 1 and len(labels) == 13
    manifest = read_json(clustering / "manifest.json")
    command = manifest["history"]["command"]
    assert manifest["history"]["child_peak_rss_bytes"] > 0
    assert "--seed=17" in command
    assert any(
        option.startswith("--output_path=") and option.endswith(os.sep) for option in command
    )
    quotient = aggregate_graph(prepared, clustering, resources)
    assert read_json(quotient / "manifest.json")["edge_count"] == 21
