"""CPU layouts on bounded summaries; no plotting imports or global RNG changes."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import numpy as np


def selected_edges(weights, max_edges: int):
    if max_edges < 0:
        raise ValueError("max_edges must be nonnegative")
    a, b = np.nonzero(np.triu(weights, k=1))
    w = weights[a, b]
    order = np.lexsort((b, a, -w.astype(np.int64)))[:max_edges]
    total = int(w.sum())
    shown = int(w[order].sum())
    return (
        a[order],
        b[order],
        w[order],
        {
            "display_edge_pairs": len(order),
            "all_external_display_pairs": len(w),
            "shown_external_edge_weight": shown,
            "omitted_external_edge_weight": total - shown,
            "policy": "largest raw edge weights; filtering affects the image only",
        },
    )


def layout(weights, seed=42, engine="auto"):
    n = len(weights)
    a, b = np.nonzero(np.triu(weights, k=1))
    w = np.log1p(weights[a, b].astype(float))
    if n == 1:
        return np.zeros((1, 2)), "single-node"
    if len(a) == 0:
        angles = 2 * np.pi * np.arange(n) / n
        return np.column_stack((np.cos(angles), np.sin(angles))), "circle-for-isolates"
    if engine == "sfdp" or (engine == "auto" and shutil.which("sfdp")):
        if not shutil.which("sfdp"):
            raise ValueError("sfdp is not installed; choose --layout igraph or install Graphviz")
        dot = ["graph G {", f'graph [start="{seed}", overlap=prism];', "node [shape=point];"]
        dot += [f"{i};" for i in range(n)]
        dot += [
            f"{int(u)} -- {int(v)} [weight={float(weight):.9g}];"
            for u, v, weight in zip(a, b, w, strict=True)
        ]
        dot.append("}")
        run = subprocess.run(
            ["sfdp", "-Tplain"], input="\n".join(dot), capture_output=True, text=True, check=True
        )
        coords = np.zeros((n, 2))
        for line in run.stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == "node":
                coords[int(fields[1])] = [float(fields[2]), float(fields[3])]
        return coords, "Graphviz-sfdp"
    # igraph uses random jitter even with explicit initial coordinates. Its RNG
    # setter is global and has no getter, so a worker gives reproducibility
    # without overwriting an embedding application's RNG configuration.
    run = subprocess.run(
        [sys.executable, "-m", "largegraph_viz._layout_worker"],
        input=json.dumps(
            {
                "nodes": n,
                "sources": a.tolist(),
                "targets": b.tolist(),
                "weights": w.tolist(),
                "seed": seed,
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=300,
    )
    return np.asarray(
        json.loads(run.stdout), dtype=float
    ), "igraph-Fruchterman-Reingold-seeded-worker"
