"""Fresh-process, bounded comparisons on an already prepared graph.

The optional benchmarks group supplies NetworKit. These are detector comparisons,
not a ranking of complete visualization products. Graph loading, detection,
common modularity evaluation and process RSS are reported separately.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import _bootstrap  # noqa: F401


def worker(args):
    from largegraph.runtime import Resources, configure_threads, environment, read_json

    configure_threads(args.threads)
    import numpy as np

    from largegraph.cluster import modularity, native_cluster
    from largegraph.prepare import batches

    meta = read_json(args.prepared / "manifest.json")
    if meta["nodes"] > 100_000 or meta["edges"] > 2_000_000:
        raise ValueError("Comparison is bounded to 100,000 nodes and 2,000,000 edges")
    resources = Resources(memory="256MB", threads=args.threads)
    start = time.perf_counter()
    graph = None
    if args.worker == "networkit":
        import networkit as nk

        nk.setNumberOfThreads(args.threads)
        nk.setSeed(args.seed, False)
        graph = nk.Graph(meta["nodes"], weighted=False, directed=False)
        for batch in batches(args.prepared / "edges.parquet"):
            for a, b in zip(batch.column(0).to_numpy(), batch.column(1).to_numpy(), strict=True):
                graph.addEdge(int(a), int(b))
    elif args.worker == "leiden":
        import igraph as ig
        import leidenalg as la

        edges = []
        for batch in batches(args.prepared / "edges.parquet"):
            edges.extend(zip(batch.column(0).to_pylist(), batch.column(1).to_pylist(), strict=True))
        graph = ig.Graph(n=meta["nodes"], edges=edges, directed=False)
    load_seconds = time.perf_counter() - start
    start = time.perf_counter()
    if args.worker == "streaming":
        labels, history = native_cluster(args.prepared, 5, 1, resources)
        parameters = {
            "passes": 5,
            "order": "lexicographic compact ID",
            "jit": "cache state depends on installation; detector timer includes JIT startup",
        }
    elif args.worker == "leiden":
        partition = la.find_partition(
            graph,
            la.RBConfigurationVertexPartition,
            resolution_parameter=1,
            seed=args.seed,
            n_iterations=5,
        )
        labels = np.array(partition.membership, dtype=np.uint32)
        parameters = {"iterations": 5, "resolution": 1, "seed": args.seed}
    else:
        algorithm = nk.community.PLM(
            graph, refine=True, gamma=1, par="balanced", maxIter=32, turbo=True, recurse=True
        ).run()
        labels = np.asarray(algorithm.getPartition().getVector(), dtype=np.uint32)
        parameters = {
            "refine": True,
            "gamma": 1,
            "par": "balanced",
            "maxIter": 32,
            "turbo": True,
            "recurse": True,
            "seed": args.seed,
        }
    seconds = time.perf_counter() - start
    quality_start = time.perf_counter()
    quality = modularity(args.prepared, labels)
    quality_seconds = time.perf_counter() - quality_start
    import psutil

    result = {
        "backend": args.worker,
        "seed": args.seed,
        "threads": args.threads,
        "nodes": meta["nodes"],
        "edges": meta["edges"],
        "graph_load_and_backend_import_seconds": load_seconds,
        "detector_seconds": seconds,
        "common_quality_evaluation_seconds": quality_seconds,
        "modularity": quality,
        "communities": len(np.unique(labels)),
        "parameters": parameters,
        "final_process_rss_bytes": psutil.Process().memory_info().rss,
        "environment": environment(),
    }
    if sys.platform == "linux":
        import resource

        result["process_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    if args.worker == "networkit":
        result["networkit_version"] = nk.__version__
        result["components"] = nk.components.ConnectedComponents(graph).run().numberOfComponents()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--worker", choices=["streaming", "leiden", "networkit"])
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args)))
        return
    if args.output is None:
        parser.error("--output is required")
    results = []
    for backend in ("streaming", "leiden", "networkit"):
        for seed in (42, 43, 44):
            start = time.perf_counter()
            process = subprocess.run(
                [
                    sys.executable,
                    __file__,
                    str(args.prepared),
                    "--worker",
                    backend,
                    "--seed",
                    str(seed),
                    "--threads",
                    str(args.threads),
                ],
                capture_output=True,
                text=True,
                check=True,
                env={
                    **os.environ,
                    "OMP_NUM_THREADS": str(args.threads),
                    "OPENBLAS_NUM_THREADS": str(args.threads),
                },
            )
            result = json.loads(process.stdout)
            result["fresh_process_wall_seconds"] = time.perf_counter() - start
            results.append(result)
    from largegraph.runtime import write_json

    write_json(
        args.output,
        {
            "results": results,
            "scope": "Bounded detector comparison from identical canonical prepared edges; preparation/report excluded. Algorithm budgets differ. Native sequential order is fixed across seeds. JIT cache and OS page cache were not flushed. No ground-truth partition is assumed.",
        },
    )


if __name__ == "__main__":
    main()
