"""Scientific invariants against independently computed tiny reference graphs."""

import csv

import numpy as np
import pyarrow.parquet as pq
import pytest

from largegraph_viz.aggregate import aggregate_graph, display_reduction
from largegraph_viz.cluster import cluster_graph, modularity
from largegraph_viz.generate import generate_graph
from largegraph_viz.prepare import export_metis, neighbor_blocks, prepare_graph
from largegraph_viz.runtime import Resources, read_json
from largegraph_viz.validate import adjusted_rand, validate_graph
from largegraph_viz.views import matrix_arrays, raster_edges, raster_points, render_coordinates

R = Resources(memory="128MB", threads=1, batch_rows=3)


def tiny_graph(tmp_path):
    # Two triangles, one bridge, a duplicate, a reverse duplicate, a loop and an isolate.
    source = tmp_path / "edges.csv"
    source.write_text("source,target\na,b\nb,c\na,c\nx,y\ny,z\nx,z\nc,x\nb,a\na,b\nz,z\n")
    nodes = tmp_path / "nodes.csv"
    nodes.write_text("node_id\nisolate\n")
    return prepare_graph(source, tmp_path / "work", R, nodes_path=nodes, hash_input=True)


def test_exact_preparation_and_adjacency(tmp_path):
    prepared = tiny_graph(tmp_path)
    manifest = read_json(prepared / "manifest.json")
    assert manifest["nodes"] == 7
    assert manifest["edges"] == 7
    assert manifest["dropped_duplicate_rows"] == 2
    assert manifest["dropped_self_loops"] == 1
    assert manifest["isolated_nodes"] == 1
    ids = pq.read_table(prepared / "nodes.parquet").to_pydict()
    names = dict(zip(ids["node_id"], ids["original_id"], strict=True))
    expected = {
        frozenset(edge)
        for edge in [
            ("a", "b"),
            ("b", "c"),
            ("a", "c"),
            ("x", "y"),
            ("y", "z"),
            ("x", "z"),
            ("c", "x"),
        ]
    }
    neighbors = {}
    for begin, end, offsets, data in neighbor_blocks(prepared, max_entries=2):
        for v in range(begin, end):
            block = data[int(offsets[v - begin]) : int(offsets[v - begin + 1])]
            neighbors[names[v]] = {names[int(x)] for x in block}
    assert neighbors["isolate"] == set()
    assert {frozenset([a, b]) for a in neighbors for b in neighbors[a]} == expected
    assert all(a in neighbors[b] for a in neighbors for b in neighbors[a])
    export_metis(prepared, tmp_path / "graph.metis", max_entries=2)
    lines = (tmp_path / "graph.metis").read_text().splitlines()
    assert lines[0] == "7 7"
    assert len(lines) == 8
    assert sum(len(line.split()) for line in lines[1:]) == 14


def test_clustering_quotient_and_normalizations(tmp_path):
    prepared = tiny_graph(tmp_path)
    clustering = cluster_graph(prepared, R, passes=8)
    labels = np.load(clustering / "labels.npy")
    quality = modularity(prepared, labels)
    # Independent definition using the tiny dense adjacency matrix.
    adjacency = np.zeros((7, 7))
    for a, b in zip(
        *[
            pq.read_table(prepared / "edges.parquet")[key].to_numpy()
            for key in ["source", "target"]
        ],
        strict=True,
    ):
        adjacency[a, b] = adjacency[b, a] = 1
    degrees = adjacency.sum(axis=1)
    independent = (
        (adjacency - np.outer(degrees, degrees) / 14) * (labels[:, None] == labels[None, :])
    ).sum() / 14
    assert quality == pytest.approx(independent)
    history = read_json(clustering / "manifest.json")["history"]
    assert all(
        a["modularity"] <= b["modularity"] + 1e-10
        for a, b in zip(history, history[1:], strict=False)
    )
    quotient = aggregate_graph(prepared, clustering, R)
    for cap in (2, 4, 128):
        reduced = display_reduction(quotient, cap, R)
        assert reduced["weights"].sum() == 7
        assert reduced["sizes"].sum() == 7
        matrix, _, _, density = matrix_arrays(reduced)
        assert matrix.sum() == 14
        assert np.array_equal(matrix.sum(axis=1), reduced["volumes"])
        assert np.all((density >= 0) & (density <= 1))
    report = validate_graph(prepared, clustering, quotient, tmp_path / "validation", R)
    assert report["all_checks_pass"]


def test_generated_unique_count_and_truth_independence(tmp_path):
    config = dict(nodes=150, edges=600, communities=5, seed=17, resources=R)
    first = generate_graph(tmp_path / "first", **config)
    second = generate_graph(tmp_path / "second", **config)
    rows = list(csv.DictReader((first / "edges.csv").open()))
    pairs = [(int(r["source"]), int(r["target"])) for r in rows]
    assert len(pairs) == len(set(pairs)) == 600
    assert all(a < b for a, b in pairs)
    assert (first / "edges.csv").read_bytes() == (second / "edges.csv").read_bytes()
    planted = np.load(first / "planted_labels.npy")
    assert len(planted) == 150
    assert np.count_nonzero(planted[1:] != planted[:-1]) > 30
    prepared = prepare_graph(
        first / "edges.csv", tmp_path / "work", R, nodes_path=first / "nodes.csv"
    )
    assert read_json(prepared / "manifest.json")["nodes"] == 150


def test_raster_conservation_and_line_semantics():
    coords = np.array([[0.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
    mass = np.array([100, 3, 7], dtype=np.uint64)
    grid = raster_points(coords, mass, 64, [0, 1, 0, 1])
    assert int(grid.sum()) == 110
    assert grid[0, 0] == 107
    edges = raster_edges(coords, np.array([0]), np.array([1]), np.array([5]), 64, [0, 1, 0, 1])
    assert np.count_nonzero(edges) == 64
    assert edges.max() == 5
    assert edges.sum() == 64 * 5  # pixel sum deliberately is not graph edge count


def test_coordinate_input_is_checked_and_rasterized(tmp_path):
    prepared = tiny_graph(tmp_path)
    coords = tmp_path / "coords.npy"
    np.save(coords, np.arange(14).reshape(7, 2).astype(float))
    output = tmp_path / "image"
    render_coordinates(coords, prepared, output, R, pixels=64)
    assert np.load(output / "node_counts.npy").sum() == 7
    assert (output / "coordinate_density.png").stat().st_size > 0
    np.save(coords, np.zeros((6, 2)))
    with pytest.raises(ValueError, match="N x 2"):
        render_coordinates(coords, prepared, tmp_path / "invalid", R, pixels=64)


def test_cache_tracks_input_and_ignores_truth_labels(tmp_path):
    source = tmp_path / "edges.csv"
    source.write_text("source,target\na,b\n")
    a = prepare_graph(source, tmp_path / "work", R)
    assert prepare_graph(source, tmp_path / "work", R) == a
    source.write_text("source,target\na,b\nb,c\n")
    assert prepare_graph(source, tmp_path / "work", R) != a


def test_detection_does_not_consume_planted_labels(tmp_path):
    source = tmp_path / "edges.csv"
    source.write_text("source,target\na,b\nb,c\nc,a\nc,d\n")
    nodes = tmp_path / "nodes.csv"
    nodes.write_text("node_id,planted_community\na,0\nb,0\nc,0\nd,1\n")
    first = prepare_graph(source, tmp_path / "work", R, nodes_path=nodes)
    original_labels = np.load(cluster_graph(first, R) / "labels.npy")
    nodes.write_text("node_id,planted_community\na,9\nb,8\nc,7\nd,6\n")
    second = prepare_graph(source, tmp_path / "work", R, nodes_path=nodes)
    changed_truth_labels = np.load(cluster_graph(second, R) / "labels.npy")
    np.testing.assert_array_equal(original_labels, changed_truth_labels)


@pytest.mark.parametrize("contents", ["source,target\na,\n", "source,target,weight\na,b,5\n"])
def test_malformed_or_implicitly_weighted_inputs_fail(tmp_path, contents):
    source = tmp_path / "edges.csv"
    source.write_text(contents)
    with pytest.raises(ValueError):
        prepare_graph(source, tmp_path / "work", R)


def test_empty_edge_graph_keeps_isolates(tmp_path):
    source = tmp_path / "edges.csv"
    source.write_text("source,target\n")
    nodes = tmp_path / "nodes.csv"
    nodes.write_text("node_id\na\nb\n")
    prepared = prepare_graph(source, tmp_path / "work", R, nodes_path=nodes)
    clustering = cluster_graph(prepared, R)
    quotient = aggregate_graph(prepared, clustering, R)
    assert modularity(prepared, np.load(clustering / "labels.npy")) == 0
    assert display_reduction(quotient, 2, R)["weights"].sum() == 0


def test_ari_is_label_permutation_invariant():
    assert adjusted_rand([0, 0, 1, 1], [8, 8, 3, 3]) == 1
    assert adjusted_rand([0, 0, 1, 1], [0, 1, 0, 1]) == pytest.approx(-0.5)
