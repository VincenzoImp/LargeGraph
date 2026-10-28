"""Fixed-edge-count degree-corrected block proposals, conditioned on simplicity."""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .numerics import block_probabilities
from .prepare import copy_query
from .runtime import (
    Monitor,
    Resources,
    artifact_directory,
    cleanup_scratch,
    environment,
    literal,
    resource_dict,
    write_json,
)

LOG = logging.getLogger(__name__)


def generate_graph(
    destination: Path,
    nodes: int = 10_000,
    edges: int = 100_000,
    communities: int = 12,
    mixing: float = 0.08,
    exponent: float = 2.5,
    seed: int = 42,
    scenario: str = "communities",
    resources: Resources | None = None,
):
    resources = resources or Resources()
    if not 2 <= nodes < 2**32 or not 1 <= communities <= min(nodes, 2048):
        raise ValueError("Need 2..2^32-1 nodes and 1..min(nodes,2048) communities")
    if not 0 <= edges <= nodes * (nodes - 1) // 2:
        raise ValueError("Requested edges exceed the simple undirected graph capacity")
    if not 0 < mixing <= 1 or exponent <= 2:
        raise ValueError("mixing must be in (0,1]; exponent must exceed 2")
    if scenario not in {"communities", "weak", "bridges", "core-periphery", "null"}:
        raise ValueError("Unknown generation scenario")
    if scenario == "weak":
        mixing = max(mixing, 0.65)
    with artifact_directory(destination) as out:
        with Monitor(
            out, spill_dir=Path(resources.temp_dir) if resources.temp_dir else None
        ) as monitor:
            rng = np.random.default_rng(seed)
            # Unequal positive block sizes. Randomize IDs so node order does not reveal blocks.
            fractions = rng.lognormal(0, 0.65, communities)
            remaining = nodes - communities
            allocation = remaining * fractions / fractions.sum()
            sizes = np.floor(allocation).astype(np.int64) + 1
            remainder = nodes - int(sizes.sum())
            if remainder:
                sizes[np.argsort(-(allocation - np.floor(allocation)))[:remainder]] += 1
            assert sizes.sum() == nodes
            boundaries = np.r_[0, np.cumsum(sizes)]
            permutation = rng.permutation(nodes).astype(np.uint32)
            labels = np.empty(nodes, dtype=np.uint32)
            grouped_labels = np.repeat(np.arange(communities, dtype=np.uint32), sizes)
            labels[permutation] = grouped_labels
            theta = np.minimum(1 + rng.pareto(exponent - 1, nodes), 100.0)
            cdf = np.empty(nodes)
            for a, b in zip(boundaries[:-1], boundaries[1:], strict=True):
                cdf[a:b] = np.cumsum(theta[a:b])
                cdf[a:b] /= cdf[b - 1]
                cdf[b - 1] = 1.0
            pair_probabilities = block_probabilities(sizes, mixing, scenario)
            support_capacity = sum(
                int(sizes[a]) * (int(sizes[a]) - 1) // 2
                for a in range(communities)
                if pair_probabilities[a, a] > 0
            )
            support_capacity += sum(
                int(sizes[a]) * int(sizes[b])
                for a in range(communities)
                for b in range(a + 1, communities)
                if pair_probabilities[a, b] + pair_probabilities[b, a] > 0
            )
            if edges > support_capacity:
                raise ValueError("Requested edges exceed the supported block-pair capacity")
            pair_cdf = np.cumsum(pair_probabilities.ravel())
            pair_cdf[-1] = 1.0
            np.save(out / "planted_labels.npy", labels)
            np.save(out / "block_probabilities.npy", pair_probabilities)
            with (out / "nodes.csv").open("w", buffering=1024 * 1024) as stream:
                stream.write("node_id,planted_community\n")
                for start in range(0, nodes, resources.batch_rows):
                    end = min(start + resources.batch_rows, nodes)
                    values = np.column_stack([np.arange(start, end), labels[start:end]])
                    np.savetxt(stream, values, fmt="%d", delimiter=",")
            candidate_dir = out / "candidates"
            candidate_dir.mkdir()
            sequence, files, unique = 0, 0, 0
            con = resources.connect(out)
            rounds = 0
            try:
                while unique < edges:
                    rounds += 1
                    if rounds > 30:
                        raise RuntimeError(
                            "Generation has not converged; lower density or change parameters. Incomplete artifacts retained."
                        )
                    # First-occurrence sampling without replacement. Never keep the edge set in RAM.
                    proposed = max(1, math.ceil((edges - unique) * (1.15 if rounds == 1 else 1.6)))
                    LOG.info(
                        "Generation round %d: %d proposals, %d unique accepted so far",
                        rounds,
                        proposed,
                        unique,
                    )
                    for begin in range(0, proposed, resources.batch_rows):
                        count = min(resources.batch_rows, proposed - begin)
                        pairs = np.searchsorted(pair_cdf, rng.random(count))
                        groups_a, groups_b = pairs // communities, pairs % communities
                        endpoints = []
                        for groups in (groups_a, groups_b):
                            sampled = np.empty(count, dtype=np.uint32)
                            order = np.argsort(groups, kind="stable")
                            sorted_groups = groups[order]
                            cuts = np.r_[
                                0,
                                np.flatnonzero(sorted_groups[1:] != sorted_groups[:-1]) + 1,
                                count,
                            ]
                            for lo, hi in zip(cuts[:-1], cuts[1:], strict=True):
                                group = sorted_groups[lo]
                                a, b = boundaries[group : group + 2]
                                local = np.searchsorted(cdf[a:b], rng.random(hi - lo))
                                sampled[order[lo:hi]] = permutation[a + local]
                            endpoints.append(sampled)
                        u, v = endpoints
                        keep = u != v
                        table = pa.table(
                            {
                                "source": np.minimum(u, v)[keep],
                                "target": np.maximum(u, v)[keep],
                                "sequence": np.arange(sequence, sequence + count, dtype=np.uint64)[
                                    keep
                                ],
                            }
                        )
                        pq.write_table(
                            table, candidate_dir / f"part-{files:08d}.parquet", compression="zstd"
                        )
                        sequence += count
                        files += 1
                    con.execute("DROP TABLE IF EXISTS unique_edges")
                    con.execute(
                        f"CREATE TABLE unique_edges AS SELECT source,target,min(sequence) AS first_seen FROM read_parquet({literal(candidate_dir / '*.parquet')}) GROUP BY source,target"
                    )
                    unique = int(con.execute("SELECT count(*) FROM unique_edges").fetchall()[0][0])
                if edges == 0:
                    con.execute(
                        "CREATE TABLE unique_edges(source UINTEGER,target UINTEGER,first_seen UBIGINT)"
                    )
                copy_query(
                    con,
                    f"SELECT source,target FROM unique_edges ORDER BY first_seen LIMIT {int(edges)}",
                    out / "edges.csv",
                    csv=True,
                )
            finally:
                con.close()
            import shutil

            shutil.rmtree(candidate_dir)
            cleanup_scratch(out)
        write_json(
            out / "manifest.json",
            {
                "kind": "synthetic",
                "model": "fixed-m weighted block proposals conditioned on no loops/duplicate edges; first unique arrivals",
                "not_canonical_bernoulli_dcsbm": True,
                "nodes": nodes,
                "unique_edges": edges,
                "proposal_rows": sequence,
                "rounds": rounds,
                "communities": communities,
                "scenario": scenario,
                "proposal_mixing": mixing,
                "degree_exponent": exponent,
                "theta_cap": 100,
                "seed": seed,
                "block_sizes": sizes.tolist(),
                "randomized_node_ids": True,
                "resources": resource_dict(resources),
                "environment": environment(),
                "metrics": monitor.stats,
                "limitations": [
                    "Realized degrees and mixing differ from proposal parameters after conditioning on simplicity.",
                    "Triangle clustering and other social-network properties are not enforced.",
                ],
            },
        )
    return destination.resolve()
