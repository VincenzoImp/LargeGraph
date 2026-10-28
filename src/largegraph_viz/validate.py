"""Conservation, planted-label recovery and bounded in-memory reference checks."""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

import numpy as np

from .cluster import modularity
from .numerics import adjusted_rand
from .prepare import batches, read_csv_query
from .runtime import Monitor, Resources, cleanup_scratch, identifier, literal, read_json, write_json


def recovery_scores(truth, labels):
    result = {"adjusted_rand_index": adjusted_rand(truth, labels)}
    if len(labels) > 100_000 or len(np.unique(truth)) * len(np.unique(labels)) > 1_000_000:
        result["adjusted_mutual_information"] = None
        result["ami_unavailable_reason"] = (
            "Exact AMI is bounded to 100,000 nodes and 1 million pairs of truth/detected groups to avoid expensive expected-MI computation; ARI still uses all nodes"
        )
        return result
    try:
        from sklearn.metrics import adjusted_mutual_info_score
    except ImportError:
        result["adjusted_mutual_information"] = None
        result["ami_unavailable_reason"] = "Install largegraph-viz[dev] for scikit-learn"
    else:
        result["adjusted_mutual_information"] = float(adjusted_mutual_info_score(truth, labels))
    return result


def align_truth(
    prepared: Path,
    truth_path: Path,
    resources: Resources,
    temporary: Path,
    node_column="node_id",
    label_column="planted_community",
):
    con = resources.connect(temporary)
    try:
        truth_query = read_csv_query(truth_path.resolve())
        cnode, clabel = identifier(node_column), identifier(label_column)
        duplicates = con.execute(
            f"SELECT count(*)-count(DISTINCT {cnode}), count(*) FILTER (WHERE {cnode} IS NULL OR {clabel} IS NULL) FROM {truth_query}"
        ).fetchone()
        if duplicates[0] or duplicates[1]:
            raise ValueError(
                "Truth CSV must have unique non-null node identifiers and non-null labels"
            )
        query = (
            f"SELECT n.node_id, t.{clabel} AS truth FROM read_parquet({literal(prepared / 'nodes.parquet')}) n "
            f"LEFT JOIN {truth_query} t ON n.original_id=t.{cnode} ORDER BY n.node_id"
        )
        # Only O(nodes), never O(edges).
        table = con.execute(query).fetch_arrow_table()
        if table["truth"].null_count:
            raise ValueError("Truth CSV is missing prepared graph nodes")
        return np.asarray(table["truth"].to_pylist())
    finally:
        con.close()
        cleanup_scratch(temporary)


def reference_leiden(
    prepared: Path,
    labels,
    resources: Resources,
    seed: int,
    max_nodes=100_000,
    max_edges=2_000_000,
    resolution=1.0,
):
    import igraph as ig
    import leidenalg as la

    manifest = read_json(prepared / "manifest.json")
    if manifest["nodes"] > max_nodes or manifest["edges"] > max_edges:
        return {
            "status": "not_run",
            "reason": "In-memory reference exceeds explicit safety caps",
            "max_nodes": max_nodes,
            "max_edges": max_edges,
        }
    edges = []
    for batch in batches(prepared / "edges.parquet", resources.batch_rows):
        edges.extend(zip(batch.column(0).to_pylist(), batch.column(1).to_pylist(), strict=True))
    ig.set_random_number_generator(random.Random(seed))
    graph = ig.Graph(n=manifest["nodes"], edges=edges, directed=False)
    partition = la.find_partition(
        graph, la.RBConfigurationVertexPartition, resolution_parameter=resolution, seed=seed
    )
    reference_labels = np.asarray(partition.membership, dtype=np.uint32)
    comparison = recovery_scores(reference_labels, labels)
    transitivity = float(graph.transitivity_undirected(mode="zero"))
    degree = np.asarray(graph.degree(), dtype=float)
    wedges = float(np.sum(degree * (degree - 1) / 2))
    comparison.update(
        {
            "status": "completed",
            "communities": len(partition),
            "seed": seed,
            "modularity": modularity(prepared, reference_labels, resolution, resources.batch_rows),
            "triangle_count_from_transitivity": round(transitivity * wedges / 3),
            "global_transitivity": transitivity,
            "connected_components": len(graph.connected_components()),
        }
    )
    return comparison


def validate_graph(
    prepared: Path,
    clustering: Path,
    quotient: Path,
    output: Path,
    resources: Resources,
    truth_path: Path | None = None,
    reference=False,
    seed=42,
    truth_node="node_id",
    truth_label="planted_community",
):
    output.mkdir(parents=True, exist_ok=True)
    with Monitor(output) as monitor:
        manifest = read_json(prepared / "manifest.json")
        cluster = read_json(clustering / "manifest.json")
        degrees = np.load(prepared / "degrees.npy")
        labels = np.load(clustering / "labels.npy")
        offsets = np.load(prepared / "offsets.npy")
        m, n = manifest["edges"], manifest["nodes"]
        total_weight = sum(
            int(batch.column(2).to_numpy().sum())
            for batch in batches(quotient / "edges.parquet", resources.batch_rows)
        )
        checks = {
            "degree_sum_equals_2m": int(degrees.sum()) == 2 * m,
            "adjacency_length_equals_2m": (prepared / "neighbors.u32").stat().st_size == 8 * m,
            "offsets_match_degrees": np.array_equal(np.diff(offsets), degrees),
            "assignment_count_equals_n": len(labels) == n,
            "quotient_edge_mass_equals_m": total_weight == m,
            "canonical_edges": True,
        }
        edge_count = 0
        for batch in batches(prepared / "edges.parquet", resources.batch_rows):
            a, b = (batch.column(i).to_numpy() for i in (0, 1))
            checks["canonical_edges"] &= bool(np.all(a < b) and np.all(b < n))
            edge_count += len(a)
        checks["edge_rows_equal_m"] = edge_count == m
        quality = modularity(
            prepared, labels, cluster["config"]["resolution"], resources.batch_rows
        )
        checks["reported_modularity_matches"] = math.isclose(
            quality, cluster["modularity"], abs_tol=1e-10
        )
        result = {
            "checks": checks,
            "all_checks_pass": all(checks.values()),
            "modularity": quality,
            "degree_summary": {
                "min": int(degrees.min()),
                "max": int(degrees.max()),
                "mean": float(degrees.mean()),
                "isolates": int(np.count_nonzero(degrees == 0)),
            },
            "graph": {"nodes": n, "edges": m},
            "clustering": str(clustering.resolve()),
        }
        values, frequencies = np.unique(degrees, return_counts=True)
        tail = np.cumsum(frequencies[::-1])[::-1]
        with (output / "degree_distribution.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["degree", "node_count", "fraction", "fraction_degree_at_least"])
            for value, count, count_tail in zip(values, frequencies, tail, strict=True):
                writer.writerow([int(value), int(count), float(count / n), float(count_tail / n)])
        if truth_path:
            truth = align_truth(
                prepared, truth_path, resources, output / "truth-scratch", truth_node, truth_label
            )
            result["planted_recovery"] = recovery_scores(truth, labels)
            names, encoded, sizes = np.unique(truth, return_inverse=True, return_counts=True)
            k = len(names)
            block_weights = np.zeros((k, k), dtype=np.uint64) if k <= 2048 else None
            within = 0
            for batch in batches(prepared / "edges.parquet", resources.batch_rows):
                a, b = (encoded[batch.column(i).to_numpy()] for i in (0, 1))
                within += int(np.count_nonzero(a == b))
                if block_weights is not None:
                    np.add.at(block_weights, (np.minimum(a, b), np.maximum(a, b)), np.uint64(1))
            result["realized_planted_connectivity"] = {
                "within_edges": within,
                "between_edges": m - within,
                "between_edge_fraction": (m - within) / m if m else 0,
                "blocks": k,
                "connectivity_matrix_exported": block_weights is not None,
                "additional_full_edge_scans": 1,
            }
            if block_weights is not None:
                np.savez_compressed(
                    output / "planted_connectivity.npz",
                    names=names,
                    sizes=sizes,
                    upper_triangle_weights=block_weights,
                )
        if reference:
            result["leiden_reference"] = reference_leiden(
                prepared, labels, resources, seed, resolution=cluster["config"]["resolution"]
            )
        if not result["all_checks_pass"]:
            write_json(output / "validation.json", result)
            raise RuntimeError("Scientific conservation checks failed; see validation.json")
    result["metrics"] = monitor.stats
    write_json(output / "validation.json", result)
    return result
