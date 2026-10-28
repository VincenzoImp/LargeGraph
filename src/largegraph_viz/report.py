"""Bounded, portable HTML reports. No CDN, telemetry, web server or GPU required."""

from __future__ import annotations

import base64
import json
import shutil
from importlib.resources import files
from pathlib import Path

import numpy as np

from .aggregate import display_reduction
from .layout import layout, selected_edges
from .runtime import Resources, read_json, write_json


def report_data(
    quotient: Path,
    hierarchy: Path,
    profile: Path,
    clustering: Path,
    resources: Resources,
    max_groups=128,
    max_edges=1200,
    seed=42,
) -> dict:
    meta = read_json(quotient / "manifest.json")
    if meta["edge_count"] * 2 > 2**53:
        raise ValueError(
            "Browser counts would exceed exact JavaScript integers; use Parquet exports"
        )
    tree = read_json(hierarchy / "manifest.json")
    entries = [
        (
            hierarchy / cut["directory"],
            np.load(hierarchy / cut["directory"] / "mapping.npy"),
            "hierarchy",
        )
        for cut in tree["cuts"]
        if cut["groups"] < meta["communities"] or meta["communities"] > 1024
    ]
    fine_count = meta["communities"]
    if fine_count <= 1024:
        entries.append((quotient, np.arange(fine_count, dtype=np.uint32), "detected"))
    elif not entries:
        entries.append((quotient, np.arange(fine_count, dtype=np.uint32), "display"))
    levels, previous_global = [], None
    for path, fine_mapping, kind in entries:
        size = read_json(path / "manifest.json")["communities"]
        # Genuine cuts are shown in full up to the browser safety cap. A large
        # disconnected forest is explicitly reduced with an artificial Other.
        cap = size if 2 <= size <= 1024 else max_groups
        reduction = display_reduction(path, max(2, cap), resources)
        global_mapping = reduction["mapping"][fine_mapping]
        count = len(reduction["sizes"])
        if (
            levels
            and count == len(levels[-1]["nodes"])
            and np.array_equal(global_mapping, previous_global)
        ):
            continue
        coords, engine = layout(reduction["weights"], seed)
        parents = np.full(count, -1, dtype=int)
        if previous_global is not None:
            # One O(k) reduction, rather than scanning all fine groups once for
            # each child. Fragmented large graphs can have millions of groups.
            lower = np.full(count, len(levels[-1]["nodes"]), dtype=np.uint32)
            upper = np.zeros(count, dtype=np.uint32)
            np.minimum.at(lower, global_mapping, previous_global)
            np.maximum.at(upper, global_mapping, previous_global)
            unique_parent = lower == upper
            parents[unique_parent] = lower[unique_parent]
        # Overview geometry uses this level's topology. Navigation carries exact
        # parent IDs; forcing every child close to a giant single-linkage parent
        # would obscure its structure and create artificial visual overlap.
        coords -= coords.mean(axis=0)
        coords /= max(1, float(np.linalg.norm(coords, axis=1).max(initial=0)))
        mass = np.bincount(global_mapping, minlength=count)
        first = np.full(count, fine_count, dtype=np.uint32)
        np.minimum.at(first, global_mapping, np.arange(fine_count, dtype=np.uint32))
        nodes = []
        for i in range(count):
            artificial = bool(reduction["artificial_other"] and i == count - 1)
            original = int(reduction["retained_communities"][i]) if not artificial else None
            nodes.append(
                {
                    "id": i,
                    "label": (
                        f"C{original}" if kind == "detected" else f"H{len(levels)}:{original}"
                    )
                    if not artificial
                    else reduction["names"][i],
                    "size": int(reduction["sizes"][i]),
                    "volume": int(reduction["volumes"][i]),
                    "internal": int(reduction["weights"][i, i]),
                    "groups": int(mass[i]),
                    "parent": int(parents[i]),
                    "leaf": int(first[i]) if mass[i] == 1 and not artificial else None,
                    "artificial": artificial,
                    "x": float(coords[i, 0]),
                    "y": float(coords[i, 1]),
                }
            )
        a, b, w, filtering = selected_edges(reduction["weights"], max_edges)
        dtype = "u32" if int(reduction["weights"].max(initial=0)) < 2**32 else "f64"
        values = reduction["weights"].astype("<u4" if dtype == "u32" else "<f8")
        levels.append(
            {
                "label": f"{count:,} groups · {kind}",
                "kind": kind,
                "nodes": nodes,
                "matrix": base64.b64encode(values.tobytes()).decode("ascii"),
                "dtype": dtype,
                "edges": [
                    [int(u), int(v), int(weight)] for u, v, weight in zip(a, b, w, strict=True)
                ],
                "edge_cap": max_edges,
                "filtering": filtering,
                "layout": engine,
                "artificial_other": reduction["artificial_other"],
            }
        )
        previous_global = global_mapping
    return {
        "schema": 1,
        "graph": {
            "nodes": meta["node_count"],
            "edges": meta["edge_count"],
            "communities": fine_count,
        },
        "profile": read_json(profile / "profile.json"),
        "clustering": {
            key: read_json(clustering / "manifest.json")[key]
            for key in ("algorithm", "modularity", "guarantees")
        },
        "hierarchy": {"method": tree["method"], "disconnected_policy": tree["disconnected_policy"]},
        "levels": levels,
        "semantics": "All canonical edges contribute to counts. Communities and hierarchy are heuristic. Distances depend on the layout. Display filtering only affects drawn links. A matrix diagonal counts each internal undirected edge twice.",
    }


def write_report(output: Path, data: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    template = files("largegraph_viz").joinpath("assets/report.html").read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False)
    # JSON embedded in a script must not be able to close that script element.
    payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    (output / "index.html").write_text(
        template.replace("__REPORT_DATA__", payload), encoding="utf-8"
    )
    write_json(output / "report.json", data)


def copy_provenance(output: Path, artifacts: dict[str, Path]) -> None:
    provenance = output / "provenance"
    provenance.mkdir()
    for name, artifact in artifacts.items():
        shutil.copyfile(artifact / "manifest.json", provenance / f"{name}.json")
