"""Pure NumPy numerical definitions shared by compiled execution and contract tests."""

from __future__ import annotations

import numpy as np


def move_block(
    start,
    end,
    offsets,
    neighbors,
    labels,
    degrees,
    volumes,
    scores,
    marks,
    touched,
    total_degree,
    resolution,
):
    moved = 0
    if total_degree == 0:
        return 0
    for v in range(start, end):
        degree = float(degrees[v])
        if degree == 0:
            continue
        local = v - start
        current = labels[v]
        volumes[current] -= degrees[v]
        count = 0
        stamp = v + 1
        for pos in range(offsets[local], offsets[local + 1]):
            community = labels[neighbors[pos]]
            if marks[community] != stamp:
                marks[community] = stamp
                touched[count] = community
                scores[community] = 0.0
                count += 1
            scores[community] += 1.0
        current_edges = scores[current] if marks[current] == stamp else 0.0
        best = current
        best_score = current_edges - resolution * degree * float(volumes[current]) / total_degree
        for i in range(count):
            community = touched[i]
            score = (
                scores[community] - resolution * degree * float(volumes[community]) / total_degree
            )
            # Strict gain, deterministic ties; never claim the guarantees of Leiden.
            if score > best_score + 1e-12:
                best, best_score = community, score
        labels[v] = best
        volumes[best] += degrees[v]
        moved += int(best != current)
    return moved


def block_probabilities(sizes, mixing: float, scenario: str):
    k = len(sizes)
    if k == 1:
        return np.ones((1, 1))
    mass = sizes / sizes.sum()
    outer = np.outer(mass, mass)
    if scenario == "null":
        return outer / outer.sum()
    if scenario == "core-periphery":
        affinity = np.full((k, k), 0.03)
        affinity[0, :] = affinity[:, 0] = 0.6
        affinity[0, 0] = 1.0
        weights = outer * affinity
        return weights / weights.sum()
    outside = outer.copy()
    np.fill_diagonal(outside, 0)
    if scenario == "bridges" and k > 2:
        allowed = np.zeros((k, k), dtype=bool)
        for i in range(k):
            allowed[i, (i + 1) % k] = allowed[(i + 1) % k, i] = True
        outside *= allowed
    weights = np.diag((1 - mixing) * mass)
    if k > 1:
        weights += mixing * outside / outside.sum()
    return weights / weights.sum()


def matrix_arrays(reduction):
    upper = reduction["weights"]
    adjacency = upper + upper.T  # diagonal now equals twice the internal edge count
    total_degree = float(reduction["volumes"].sum())
    expected = np.outer(reduction["volumes"].astype(float), reduction["volumes"].astype(float))
    if total_degree:
        expected /= total_degree
    # A descriptive stabilized log ratio, not a significance test.
    enrichment = np.log2((adjacency.astype(float) + 1) / (expected + 1))
    sizes = reduction["sizes"].astype(float)
    possible = np.outer(sizes, sizes)
    np.fill_diagonal(possible, sizes * (sizes - 1))
    density = np.divide(
        adjacency.astype(float), possible, out=np.zeros_like(possible), where=possible > 0
    )
    return adjacency, expected, enrichment, density


def raster_points(coords, mass, pixels, bounds):
    xmin, xmax, ymin, ymax = bounds
    x = np.clip(((coords[:, 0] - xmin) / (xmax - xmin) * (pixels - 1)).astype(int), 0, pixels - 1)
    y = np.clip(((coords[:, 1] - ymin) / (ymax - ymin) * (pixels - 1)).astype(int), 0, pixels - 1)
    grid = np.zeros((pixels, pixels), dtype=np.uint64)
    np.add.at(grid, (y, x), mass)
    return grid


def raster_edges(coords, a, b, weights, pixels, bounds):
    xmin, xmax, ymin, ymax = bounds
    x = (coords[:, 0] - xmin) / (xmax - xmin) * (pixels - 1)
    y = (coords[:, 1] - ymin) / (ymax - ymin) * (pixels - 1)
    grid = np.zeros((pixels, pixels), dtype=np.uint64)
    for u, v, weight in zip(a, b, weights, strict=True):
        length = max(1, int(np.ceil(max(abs(x[u] - x[v]), abs(y[u] - y[v])))))
        xx = np.clip(np.rint(np.linspace(x[u], x[v], length + 1)).astype(int), 0, pixels - 1)
        yy = np.clip(np.rint(np.linspace(y[u], y[v], length + 1)).astype(int), 0, pixels - 1)
        cells = np.unique(yy * pixels + xx)
        np.add.at(grid.ravel(), cells, np.uint64(weight))
    return grid


def adjusted_rand(a, b):
    if len(a) != len(b):
        raise ValueError("Label arrays differ in length")
    n = len(a)
    if n < 2:
        return 1.0
    _, aa, ac = np.unique(a, return_inverse=True, return_counts=True)
    _, bb, bc = np.unique(b, return_inverse=True, return_counts=True)
    pairs = aa.astype(np.uint64) * np.uint64(len(bc)) + bb.astype(np.uint64)
    counts = np.unique(pairs, return_counts=True)[1].astype(float)

    def comb(x):
        return float(np.sum(x.astype(float) * (x.astype(float) - 1) / 2))

    observed, left, right = comb(counts), comb(ac), comb(bc)
    expected = left * right / (n * (n - 1) / 2)
    maximum = (left + right) / 2
    return 1.0 if maximum == expected else (observed - expected) / (maximum - expected)
