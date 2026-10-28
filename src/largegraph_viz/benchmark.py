"""Subprocess-isolated resource benchmarks and an explicit spill experiment."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

from .runtime import (
    Monitor,
    Resources,
    configure_threads,
    environment,
    literal,
    read_json,
    write_json,
)


def run_stage(command: list[str], directory: Path, rss_limit_gb: float | None = None):
    """Enforce a sampled process-tree RSS stop, without promising a hard OS cap."""
    import psutil

    log_path = directory / "stages.log"
    directory.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    peak = 0
    killed = False
    with log_path.open("a") as log:
        log.write("\nCOMMAND " + repr(command) + "\n")
        log.flush()
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        root = psutil.Process(process.pid)
        while process.poll() is None:
            rss = 0
            try:
                tree = [root, *root.children(recursive=True)]
            except psutil.NoSuchProcess:
                tree = []
            for child in tree:
                try:
                    rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            peak = max(peak, rss)
            if rss_limit_gb is not None and rss > rss_limit_gb * 1_000_000_000:
                import signal

                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                killed = True
                break
            time.sleep(0.1)
        returncode = process.wait()
    result = {
        "command": command,
        "exit_code": returncode,
        "wall_seconds": time.perf_counter() - t0,
        "sampled_peak_process_tree_rss_bytes": peak,
        "sample_interval_seconds": 0.1,
        "rss_guard_triggered": killed,
    }
    if returncode != 0:
        write_json(directory / "failed_stage.json", result)
        raise RuntimeError(f"Benchmark stage failed; inspect {log_path}")
    return result


def spill_experiment(destination: Path, rows=4_000_000, memory="64MB", threads=1):
    """Sorting random keys under a small buffer budget must demonstrably spill."""
    destination.mkdir(parents=True, exist_ok=False)
    resources = Resources(memory=memory, threads=threads, temp_limit="20GB")
    with Monitor(destination, interval=0.02) as monitor:
        con = resources.connect(destination)
        try:
            con.execute("SET enable_profiling='json'")
            con.execute(f"SET profiling_output={literal(destination / 'duckdb-profile.json')}")
            # Deterministic hash order avoids both materializing rows in Python and already-sorted input.
            con.execute(
                f"COPY (SELECT i, hash(i) AS h, repeat('x', 80) AS payload FROM range({int(rows)}) t(i) ORDER BY h) TO {literal(destination / 'sorted.parquet')} (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        finally:
            con.close()
    profile = read_json(destination / "duckdb-profile.json")
    peak_spill = max(
        monitor.stats["peak_spill_bytes"], int(profile.get("system_peak_temp_dir_size", 0))
    )
    report = {
        "rows": rows,
        "memory": memory,
        "threads": threads,
        "metrics": monitor.stats,
        "profile_peak_temp_dir_bytes": profile.get("system_peak_temp_dir_size"),
        "verified_disk_spill": peak_spill > 0,
        "environment": environment(),
    }
    write_json(destination / "spill-report.json", report)
    if not report["verified_disk_spill"]:
        raise RuntimeError(
            "No spill observed; increase --spill-rows. This run does not prove out-of-core execution."
        )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10_000, 100_000])
    parser.add_argument("--mean-degree", type=int, default=20)
    parser.add_argument("--communities", type=int, default=12)
    parser.add_argument("--levels", type=int, nargs="+", default=[16, 64])
    parser.add_argument("--pixels", type=int, default=512)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=["communities", "weak", "bridges", "core-periphery", "null"],
        default=["communities"],
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--memory", default="3GB")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--batch-rows", type=int, default=250_000)
    parser.add_argument("--rss-limit-gb", type=float, default=6)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--spill-only", action="store_true")
    parser.add_argument("--spill-rows", type=int, default=4_000_000)
    parser.add_argument("--spill-memory", default="64MB")
    args = parser.parse_args(argv)
    if args.mean_degree < 0 or any(n < 2 for n in args.sizes) or args.rss_limit_gb <= 0:
        parser.error("Need nonnegative mean degree, at least two nodes and a positive RSS limit")
    configure_threads(args.threads)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.spill_only:
        spill_experiment(args.output / "spill", args.spill_rows, args.spill_memory)
        return
    reports = []
    for n in args.sizes:
        m = n * args.mean_degree // 2
        for scenario in args.scenarios:
            for seed in args.seeds:
                case = args.output / f"n{n}-{scenario}-s{seed}"
                data, work, figures = case / "data", case / "work", case / "figures"
                common = [
                    "--memory",
                    args.memory,
                    "--threads",
                    str(args.threads),
                    "--batch-rows",
                    str(args.batch_rows),
                ]
                prefix = [sys.executable, "-m", "largegraph_viz.cli"]
                stages = []
                stages.append(
                    run_stage(
                        prefix
                        + [
                            "generate",
                            "--output",
                            str(data),
                            "--nodes",
                            str(n),
                            "--edges",
                            str(m),
                            "--seed",
                            str(seed),
                            "--scenario",
                            scenario,
                            "--communities",
                            str(min(n, args.communities)),
                        ]
                        + common,
                        case,
                        args.rss_limit_gb,
                    )
                )
                command = (
                    prefix
                    + [
                        "all",
                        str(data / "edges.csv"),
                        "--nodes-file",
                        str(data / "nodes.csv"),
                        "--truth",
                        str(data / "nodes.csv"),
                        "--work-dir",
                        str(work),
                        "--output",
                        str(figures),
                        "--seed",
                        str(seed),
                        "--hash-input",
                        "--pixels",
                        str(args.pixels),
                        "--levels",
                        *[str(level) for level in args.levels],
                    ]
                    + common
                )
                if args.reference:
                    command.append("--reference")
                stages.append(run_stage(command, case, args.rss_limit_gb))
                pipeline = read_json(figures / "pipeline.json")
                prepared = read_json(Path(pipeline["prepared"]) / "manifest.json")
                report = {
                    "nodes": n,
                    "edges": m,
                    "scenario": scenario,
                    "seed": seed,
                    "stages": stages,
                    "validation": read_json(figures / "validation" / "validation.json"),
                    "prepare_metrics": prepared["metrics"],
                    "edge_rows_per_second_prepare": m
                    / max(prepared["metrics"]["wall_seconds"], 1e-9),
                    "cluster_metrics": read_json(Path(pipeline["clustering"]) / "manifest.json")[
                        "metrics"
                    ],
                }
                reports.append(report)
                write_json(case / "report.json", report)
                write_json(
                    args.output / "benchmark.json",
                    {
                        "cases": reports,
                        "environment": environment(),
                        "limitations": "Sampled RSS is not a hard OS limit. Timing includes cold imports/JIT. Extrapolation is not a full-scale benchmark.",
                    },
                )
    with (args.output / "summary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "nodes",
                "edges",
                "scenario",
                "seed",
                "wall_seconds",
                "peak_rss_bytes",
                "prepare_edges_per_second",
                "ARI",
                "AMI",
            ]
        )
        for report in reports:
            scores = report["validation"]["planted_recovery"]
            writer.writerow(
                [
                    report["nodes"],
                    report["edges"],
                    report["scenario"],
                    report["seed"],
                    sum(s["wall_seconds"] for s in report["stages"]),
                    max(s["sampled_peak_process_tree_rss_bytes"] for s in report["stages"]),
                    report["edge_rows_per_second_prepare"],
                    scores["adjusted_rand_index"],
                    scores["adjusted_mutual_information"],
                ]
            )


if __name__ == "__main__":
    main()
