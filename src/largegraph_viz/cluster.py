"""Semi-external modularity local moving and an explicit CluStRE adapter."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from numba import njit

from .artifacts import cached_directory, restart_partial
from .numerics import move_block
from .prepare import export_metis, neighbor_blocks, write_assignments
from .runtime import (
    Monitor,
    Resources,
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


def native_cluster(
    prepared: Path,
    passes: int,
    resolution: float,
    resources: Resources,
    checkpoint: Path | None = None,
):
    degrees = np.load(prepared / "degrees.npy")
    n = len(degrees)
    labels = np.arange(n, dtype=np.uint32)
    history = []
    if checkpoint and (checkpoint / "pass.json").exists():
        state = read_json(checkpoint / "pass.json")
        labels = np.load(checkpoint / state["labels"])
        if labels.shape != (n,) or labels.dtype != np.uint32 or labels.max(initial=0) >= n:
            raise ValueError("Invalid clustering checkpoint")
        history = state["history"]
        LOG.info("Resuming after clustering pass %d", len(history))
    volumes = np.zeros(n, dtype=np.uint64)
    np.add.at(volumes, labels, degrees)
    scores = np.zeros(n)
    marks = np.zeros(n, dtype=np.uint32)
    touched = np.empty(max(1, int(degrees.max(initial=0))), dtype=np.uint32)
    total_degree = float(degrees.sum())
    for iteration in range(len(history), passes):
        if history and history[-1]["moved_nodes"] == 0:
            break
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
        if checkpoint:
            checkpoint.mkdir(exist_ok=True)
            filename = f"labels-{iteration + 1}.npy"
            np.save(checkpoint / filename, labels)
            write_json(checkpoint / "pass.json", {"labels": filename, "history": history})
            for previous in checkpoint.glob("labels-*.npy"):
                if previous.name != filename:
                    previous.unlink()
        if moved == 0:
            break
    _, labels = np.unique(labels, return_inverse=True)
    return labels.astype(np.uint32), history


def clustre_cluster(
    prepared: Path, out: Path, binary: Path, mode: str, resources: Resources, seed=42
):
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
        f"--seed={seed}",
        f"--output_path={results.resolve()}{os.sep}",
    ]
    with (out / "clustre.log").open("w") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, "OMP_NUM_THREADS": str(resources.threads)},
        )
        _, status, usage = os.wait4(process.pid, 0)
        process.returncode = os.waitstatus_to_exitcode(status)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
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
        "child_peak_rss_bytes": int(usage.ru_maxrss) * 1024,
        "child_cpu_user_seconds": usage.ru_utime,
        "child_cpu_system_seconds": usage.ru_stime,
    }


def cluster_graph(
    prepared: Path,
    resources: Resources,
    backend="streaming",
    passes=5,
    resolution=1.0,
    clustre_binary: Path | None = None,
    clustre_mode="light",
    seed=42,
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
        "algorithm_version": 2,
    }
    if backend == "clustre":
        config["seed"] = seed
        config["adapter_version"] = 2
    if backend in {"leiden", "networkit"}:
        config["seed"] = seed
    destination = prepared.parent / ("cluster-" + signature(config)[:20])
    with cached_directory(destination) as out:
        if out is None:
            return destination
        if backend != "streaming":
            restart_partial(out)
        with Monitor(out) as monitor:
            if backend == "streaming":
                labels, history = native_cluster(
                    prepared, passes, resolution, resources, out / "passes"
                )
                algorithm = (
                    "semi-external sequential modularity local moving; not CluStRE or Leiden"
                )
            elif backend == "clustre":
                if clustre_binary is None:
                    raise ValueError("CluStRE backend requires --clustre-binary")
                labels, history = clustre_cluster(
                    prepared, out, clustre_binary, clustre_mode, resources, seed
                )
                algorithm = "CluStRE external binary"
            elif backend == "networkit":
                meta = read_json(prepared / "manifest.json")
                if meta["nodes"] > 100_000 or meta["edges"] > 2_000_000:
                    raise ValueError(
                        "NetworKit backend is bounded to 100,000 nodes and 2,000,000 edges; choose streaming for larger inputs"
                    )
                import json

                run = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "largegraph_viz._networkit_worker",
                        str(prepared),
                        str(out / "labels.npy"),
                        "--seed",
                        str(seed),
                        "--threads",
                        str(resources.threads),
                        "--passes",
                        str(passes),
                        "--resolution",
                        str(resolution),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                labels = np.load(out / "labels.npy")
                history = json.loads(run.stdout)
                algorithm = "NetworKit parallel Louvain with refinement (bounded worker)"
            elif backend == "leiden":
                meta = read_json(prepared / "manifest.json")
                if meta["nodes"] > 100_000 or meta["edges"] > 2_000_000:
                    raise ValueError(
                        "Leiden backend is bounded to 100,000 nodes and 2,000,000 edges; choose streaming for larger inputs"
                    )
                try:
                    import igraph as ig
                    import leidenalg as la
                except ImportError as exc:
                    raise ValueError("Leiden backend requires largegraph-viz[leiden]") from exc
                from .prepare import batches

                edges = []
                for batch in batches(prepared / "edges.parquet", resources.batch_rows):
                    edges.extend(
                        zip(batch.column(0).to_pylist(), batch.column(1).to_pylist(), strict=True)
                    )
                graph = ig.Graph(n=meta["nodes"], edges=edges, directed=False)
                partition = la.find_partition(
                    graph,
                    la.RBConfigurationVertexPartition,
                    resolution_parameter=resolution,
                    seed=seed,
                    n_iterations=passes,
                )
                labels = np.asarray(partition.membership, dtype=np.uint32)
                history = {
                    "seed": seed,
                    "iterations": passes,
                    "mode": "bounded in-memory reference backend",
                }
                algorithm = "Leiden (leidenalg RBConfigurationVertexPartition)"
            else:
                raise ValueError("Unknown clustering backend")
            np.save(out / "labels.npy", labels)
            write_assignments(out / "assignments.parquet", labels, resources.batch_rows)
            quality = modularity(prepared, labels, resolution, resources.batch_rows)
        import shutil

        shutil.rmtree(out / "passes", ignore_errors=True)
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
