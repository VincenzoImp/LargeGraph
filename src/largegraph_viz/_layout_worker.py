"""Seed igraph's process-global RNG only inside an isolated bounded worker."""

import json
import random
import sys

import igraph as ig
import numpy as np


def main():
    data = json.load(sys.stdin)
    ig.set_random_number_generator(random.Random(data["seed"]))
    graph = ig.Graph(
        n=data["nodes"],
        edges=list(zip(data["sources"], data["targets"], strict=True)),
        directed=False,
    )
    initial = np.random.default_rng(data["seed"]).normal(size=(data["nodes"], 2)).tolist()
    coordinates = graph.layout_fruchterman_reingold(
        weights=data["weights"], seed=initial, niter=500
    ).coords
    json.dump(coordinates, sys.stdout, allow_nan=False)


if __name__ == "__main__":
    main()
