"""Semi-external modularity local moving and an explicit CluStRE adapter."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import numpy as np
from numba import njit

from .numerics import move_block
from .prepare import export_metis, neighbor_blocks, write_assignments
from .runtime import (
    Monitor,
    Resources,
    artifact_directory,
    environment,
    fingerprint,
    read_json,
    resource_dict,
    signature,
    write_json,
)

LOG = logging.getLogger(__name__)

_move_block = njit(cache=True)(move_block)


def modularity(prepared: Path, labels, resolution=1.0, batch_rows=250_000):
    from .prepare import batches

    degrees = np.load(prepared / "degrees.npy")
    total = int(degrees.sum())
    if total == 0:
        return 0.0
    volumes = np.bincount(labels.astype(np.int64), weights=degrees.astype(float))
    internal = 0
    for batch in batches(prepared / "edges.parquet", batch_rows):
        u, v = (batch.column(i).to_numpy() for i in (0, 1))
        internal += int(np.count_nonzero(labels[u] == labels[v]))
    return internal / (total / 2) - resolution * float(np.square(volumes / total).sum())


def native_cluster(prepared: Path, passes: int, resolution: float, resources: Resources):
    degrees = np.load(prepared / "degrees.npy")
    n = len(degrees)
    labels = np.arange(n, dtype=np.uint32)
    volumes = degrees.copy()
    scores = np.zeros(n)
    marks = np.zeros(n, dtype=np.uint32)
    touched = np.empty(max(1, int(degrees.max(initial=0))), dtype=np.uint32)
    total_degree = float(degrees.sum())
    history = []
    for iteration in range(passes):
        marks.fill(0)
        moved = 0
        for start, end, offsets, neighbors in neighbor_blocks(prepared, resources.batch_rows * 4):
            moved += _move_block(
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
            )
        # Exact objective per pass is deliberately an additional edge scan.
        quality = modularity(prepared, labels, resolution, resources.batch_rows)
        history.append({"pass": iteration + 1, "moved_nodes": moved, "modularity": quality})
        LOG.info("Streaming pass %d: %d moves; Q=%.6f", iteration + 1, moved, quality)
        if len(history) > 1 and quality + 1e-10 < history[-2]["modularity"]:
            raise RuntimeError("Local moves unexpectedly decreased modularity")
        if moved == 0:
            break
    _, labels = np.unique(labels, return_inverse=True)
    return labels.astype(np.uint32), history


def clustre_cluster(prepared: Path, out: Path, binary: Path, mode: str, resources: Resources):
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("--clustre-binary must name an executable CluStRE installation")
    graph_path = out / "graph.metis"
    export_metis(prepared, graph_path, resources.batch_rows * 4)
    results = out / "clustre-output"
    results.mkdir()
    command = [
        str(binary.resolve()),
        str(graph_path.resolve()),
        "--one_pass_algorithm=modularity",
        f"--mode={mode}",
        f"--output_path={results.resolve()}",
    ]
    with (out / "clustre.log").open("w") as log:
        subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            env={**os.environ, "OMP_NUM_THREADS": str(resources.threads)},
        )
    candidates = list(results.glob("*.txt"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one CluStRE assignment file, found {candidates}; inspect clustre.log"
        )
    labels = np.loadtxt(candidates[0], dtype=np.int64, ndmin=1)
    n = read_json(prepared / "manifest.json")["nodes"]
    if labels.ndim != 1 or len(labels) != n or np.any(labels < 0):
        raise RuntimeError("Invalid CluStRE assignment length or negative labels")
    _, labels = np.unique(labels, return_inverse=True)
    graph_path.unlink()
    return labels.astype(np.uint32), {
        "command": command,
        "binary": fingerprint(binary, True),
        "mode": mode,
    }


def cluster_graph(
    prepared: Path,
    resources: Resources,
    backend="streaming",
    passes=5,
    resolution=1.0,
    clustre_binary: Path | None = None,
    clustre_mode="light",
):
    if passes < 1 or not np.isfinite(resolution) or resolution <= 0:
        raise ValueError("passes and resolution must be positive")
    if backend == "clustre" and (resolution != 1.0 or clustre_mode not in {"light", "light_plus"}):
        raise ValueError("CluStRE adapter supports light/light_plus and resolution=1 only")
    binary = fingerprint(clustre_binary, True) if clustre_binary else None
    config = {
        "prepared": read_json(prepared / "manifest.json")["config"],
        "backend": backend,
        "passes": passes,
        "resolution": resolution,
        "binary": binary,
        "clustre_mode": clustre_mode,
        "algorithm_version": 1,
    }
    destination = prepared.parent / ("cluster-" + signature(config)[:20])
    if (destination / "manifest.json").exists():
        return destination
    with artifact_directory(destination) as out:
        with Monitor(out) as monitor:
            if backend == "streaming":
                labels, history = native_cluster(prepared, passes, resolution, resources)
                algorithm = (
                    "semi-external sequential modularity local moving; not CluStRE or Leiden"
                )
            elif backend == "clustre":
                if clustre_binary is None:
                    raise ValueError("CluStRE backend requires --clustre-binary")
                labels, history = clustre_cluster(
                    prepared, out, clustre_binary, clustre_mode, resources
                )
                algorithm = "CluStRE external binary"
            else:
                raise ValueError("Unknown clustering backend")
            np.save(out / "labels.npy", labels)
            write_assignments(out / "assignments.parquet", labels, resources.batch_rows)
            quality = modularity(prepared, labels, resolution, resources.batch_rows)
        write_json(
            out / "manifest.json",
            {
                "kind": "clustering",
                "config": config,
                "algorithm": algorithm,
                "communities": int(labels.max(initial=0)) + 1,
                "history": history,
                "modularity": quality,
                "metrics": monitor.stats,
                "resources": resource_dict(resources),
                "environment": environment(),
                "guarantees": "heuristic partition; no connectivity or optimality guarantee",
            },
        )
    return destination
