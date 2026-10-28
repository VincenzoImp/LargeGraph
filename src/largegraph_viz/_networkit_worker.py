"""Isolate NetworKit's global seed/thread settings for a bounded backend."""

import argparse
import json

import networkit as nk
import numpy as np

from .prepare import batches
from .runtime import read_json


def main():
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("prepared", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--threads", type=int, required=True)
    parser.add_argument("--passes", type=int, required=True)
    parser.add_argument("--resolution", type=float, required=True)
    args = parser.parse_args()
    nk.setNumberOfThreads(args.threads)
    nk.setSeed(args.seed, False)
    meta = read_json(args.prepared / "manifest.json")
    graph = nk.Graph(meta["nodes"], weighted=False, directed=False)
    for batch in batches(args.prepared / "edges.parquet"):
        for a, b in zip(batch.column(0).to_numpy(), batch.column(1).to_numpy(), strict=True):
            graph.addEdge(int(a), int(b))
    algorithm = nk.community.PLM(
        graph,
        refine=True,
        gamma=args.resolution,
        par="balanced",
        maxIter=args.passes,
        turbo=True,
        recurse=True,
    ).run()
    _, labels = np.unique(np.asarray(algorithm.getPartition().getVector()), return_inverse=True)
    np.save(args.output, labels.astype(np.uint32))
    print(
        json.dumps(
            {
                "version": nk.__version__,
                "refine": True,
                "gamma": args.resolution,
                "par": "balanced",
                "maxIter": args.passes,
                "turbo": True,
                "recurse": True,
                "seed": args.seed,
                "threads": args.threads,
                "reproducibility": "parallel scheduling can vary results despite a fixed seed",
            }
        )
    )


if __name__ == "__main__":
    main()
