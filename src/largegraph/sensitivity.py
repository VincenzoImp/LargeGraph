"""Relabel the SAME small graph to quantify streaming node-order sensitivity."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .cluster import cluster_graph
from .prepare import batches, prepare_graph
from .runtime import Resources, configure_threads, environment, read_json, write_json
from .validate import recovery_scores


def order_sensitivity(
    prepared: Path, clustering: Path, output: Path, resources: Resources, seeds=(101, 102, 103)
):
    manifest = read_json(prepared / "manifest.json")
    if manifest["nodes"] > 100_000 or manifest["edges"] > 2_000_000:
        raise ValueError(
            "Order-sensitivity experiment is capped at 100,000 nodes / 2 million edges"
        )
    config = read_json(clustering / "manifest.json")["config"]
    if config["backend"] != "streaming":
        raise ValueError(
            "This experiment currently compares the deterministic native streaming backend"
        )
    n = manifest["nodes"]
    baseline = np.load(clustering / "labels.npy")
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for seed in seeds:
        case = output / f"seed-{seed}"
        case.mkdir(exist_ok=False)
        permutation = np.random.default_rng(seed).permutation(n)
        edge_file, nodes_file = case / "edges.csv", case / "nodes.csv"
        with edge_file.open("w") as stream:
            stream.write("source,target\n")
            for batch in batches(prepared / "edges.parquet", resources.batch_rows):
                values = np.column_stack([permutation[batch.column(i).to_numpy()] for i in (0, 1)])
                np.savetxt(stream, values, delimiter=",", fmt="%010d")
        with nodes_file.open("w") as stream:
            stream.write("node_id\n")
            np.savetxt(stream, np.arange(n), fmt="%010d")
        permuted_graph = prepare_graph(
            edge_file, case / "work", resources, nodes_path=nodes_file, hash_input=True
        )
        alternative = cluster_graph(
            permuted_graph, resources, passes=config["passes"], resolution=config["resolution"]
        )
        labels = np.load(alternative / "labels.npy")[permutation]
        reports.append(
            {
                "seed": seed,
                "comparison_to_original_order": recovery_scores(baseline, labels),
                "modularity": read_json(alternative / "manifest.json")["modularity"],
                "clustering": str(alternative),
                "same_graph_up_to_bijection": True,
            }
        )
        np.save(case / "compact_id_permutation.npy", permutation)
    report = {
        "baseline": str(clustering.resolve()),
        "cases": reports,
        "environment": environment(),
        "interpretation": "Same graph relabeled bijectively. Variation measures node-order dependence, not variation in the generated graph.",
    }
    write_json(output / "order-sensitivity.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--clustering", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103])
    parser.add_argument("--memory", default="512MB")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args(argv)
    configure_threads(args.threads)
    order_sensitivity(
        args.prepared,
        args.clustering,
        args.output,
        Resources(memory=args.memory, threads=args.threads),
        args.seeds,
    )


if __name__ == "__main__":
    main()
