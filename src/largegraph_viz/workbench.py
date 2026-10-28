"""User-facing commands sharing the typed analysis API."""

from __future__ import annotations

import dataclasses
import json
import logging
from importlib.resources import as_file, files
from pathlib import Path

from .api import Analysis, analyze
from .artifacts import verify_artifact
from .budget import default_resources, preflight
from .config import AnalysisOptions
from .runtime import Resources, environment, read_json


def add_commands(sub) -> None:
    run = sub.add_parser(
        "analyze", help="Analyze CSV/Parquet and build a portable interactive report"
    )
    run.add_argument("input", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--work-dir", type=Path)
    run.add_argument(
        "--config", type=Path, help="AnalysisOptions JSON; explicit CLI flags override"
    )
    run.add_argument(
        "--ram", default="8GB", help="RAM planning target; use cgroup runner for hard limits"
    )
    run.add_argument("--memory", help="Override DuckDB memory budget (not total RAM)")
    run.add_argument("--threads", type=int, default=2)
    run.add_argument("--batch-rows", type=int, default=250_000)
    run.add_argument("--temp-dir", type=Path)
    run.add_argument("--temp-limit", default="80GB")
    for name, default in (
        ("source", "source"),
        ("target", "target"),
        ("node-column", "node_id"),
        ("delimiter", ","),
    ):
        run.add_argument("--" + name, default=default)
    run.add_argument("--nodes-file", type=Path)
    run.add_argument("--passes", type=int, default=5)
    run.add_argument("--resolution", type=float, default=1)
    run.add_argument("--backend", choices=["streaming", "clustre", "leiden"], default="streaming")
    run.add_argument("--clustre-binary", type=Path)
    run.add_argument("--clustre-mode", choices=["light", "light_plus"], default="light")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--max-groups", type=int, default=128)
    run.add_argument("--max-edges", type=int, default=1200)
    run.add_argument("--hierarchy-targets", nargs="+", type=int, default=[16, 64, 256])
    run.add_argument("--pixels", type=int, default=512)
    for name in ("images", "hash-input", "ignore-extra-columns"):
        run.add_argument("--" + name, action="store_true")
    run.add_argument(
        "--dry-run", action="store_true", help="Inspect headers/resources without preparing data"
    )
    run.add_argument("--open", action="store_true", help="Open the portable report in a browser")
    demo = sub.add_parser("demo", help="Run the bundled reproducible graph, without downloads")
    demo.add_argument("--output", type=Path, default=Path("largegraph-demo"))
    demo.add_argument("--open", action="store_true")
    demo.add_argument("--images", action="store_true")
    viewer = sub.add_parser("serve", help="Serve an analysis locally with indexed node queries")
    viewer.add_argument("run", type=Path)
    viewer.add_argument("--port", type=int, default=8765)
    for command in ("neighbors", "members"):
        query = sub.add_parser(command, help="Query the on-disk analysis index")
        query.add_argument("run", type=Path)
        query.add_argument("--limit", type=int, default=100)
        if command == "neighbors":
            query.add_argument("--node", required=True, help="Original ID, preserved as text")
        else:
            query.add_argument("--community", type=int, required=True)
            query.add_argument("--after", type=int, default=-1)
    export = sub.add_parser("export", help="Export the exact weighted quotient")
    export.add_argument("run", type=Path)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--format", choices=["parquet", "csv", "graphml"], default="parquet")
    inspect = sub.add_parser("inspect", help="Inspect analysis status, profile and provenance")
    inspect.add_argument("run", type=Path)
    verify = sub.add_parser("verify", help="Verify cached file sizes/hashes and report integrity")
    verify.add_argument("run", type=Path)
    verify.add_argument(
        "--deep",
        action="store_true",
        help="Also scan large files and return archive SHA-256 hashes",
    )
    sub.add_parser("doctor", help="Show installed versions and available memory/disk")


COMMANDS = {
    "analyze",
    "demo",
    "serve",
    "neighbors",
    "members",
    "export",
    "inspect",
    "verify",
    "doctor",
}


def dispatch(args, raw_args: list[str]) -> None:
    def emit(value):
        print(json.dumps(value, indent=2, allow_nan=False))

    if args.command == "doctor":
        import shutil

        from .budget import available_memory

        emit(
            environment()
            | {
                "available_memory_bytes": available_memory(),
                "free_disk_bytes": shutil.disk_usage(Path.cwd()).free,
            }
        )
        return
    if args.command == "serve":
        from .server import serve

        serve(args.run, args.port)
        return
    if args.command == "inspect":
        state = read_json(args.run / "analysis.json")
        if state["status"] == "complete":
            result = Analysis.open(args.run)
            state["profile"] = read_json(result.profile / "profile.json")
            state["report"] = str(result.report)
        emit(state)
        return
    if args.command in {"neighbors", "members", "export", "verify"}:
        result = Analysis.open(args.run)
        if args.command == "neighbors":
            emit(result.neighbors(args.node, args.limit))
        elif args.command == "members":
            emit(result.members(args.community, args.limit, args.after))
        elif args.command == "export":
            print(result.export(args.output, args.format))
        else:
            checks = {
                name: verify_artifact(getattr(result, name), args.deep)
                for name in ("prepared", "clustering", "quotient", "profile", "hierarchy", "index")
            }
            checks["report"] = verify_artifact(result.report.parent, args.deep)
            emit(checks)
            if not all(item["valid"] for item in checks.values()):
                raise ValueError("Artifact verification failed")
        return
    if args.command == "demo":
        assets = files("largegraph_viz").joinpath("assets")
        with (
            as_file(assets.joinpath("demo_edges.csv")) as edges,
            as_file(assets.joinpath("demo_nodes.csv")) as nodes,
        ):
            result = analyze(
                edges,
                args.output,
                options=AnalysisOptions(
                    nodes_file=nodes, images=args.images, hierarchy_targets=(4, 16, 64)
                ),
                resources=Resources(memory="256MB", threads=2, batch_rows=10_000),
            )
    else:
        values = {
            field.name: getattr(args, field.name) for field in dataclasses.fields(AnalysisOptions)
        }
        if args.config:
            defaults = read_json(args.config)
            for name, value in defaults.items():
                if name not in values:
                    raise ValueError(f"Unknown AnalysisOptions configuration key: {name}")
                option = "--" + name.replace("_", "-")
                if not any(item == option or item.startswith(option + "=") for item in raw_args):
                    values[name] = value
        for name in ("nodes_file", "clustre_binary"):
            if values[name] is not None:
                values[name] = Path(values[name])
        values["hierarchy_targets"] = tuple(values["hierarchy_targets"])
        options = AnalysisOptions(**values)
        defaults = default_resources(args.ram, args.threads)
        resources = Resources(
            memory=args.memory or defaults.memory,
            threads=args.threads,
            batch_rows=args.batch_rows,
            temp_dir=str(args.temp_dir.resolve()) if args.temp_dir else None,
            temp_limit=args.temp_limit,
        )
        if args.images:
            import importlib.util

            for package in ("matplotlib", "scipy"):
                if importlib.util.find_spec(package) is None:
                    raise ValueError("Static figures require largegraph-viz[images]")
        if args.dry_run:
            emit(
                preflight(
                    args.input, args.work_dir or args.output, resources, args.ram, options.delimiter
                )
            )
            return
        result = analyze(
            args.input,
            args.output,
            work_dir=args.work_dir,
            options=options,
            resources=resources,
            ram=args.ram,
        )
    print(f"Report: {result.report}")
    print(f"Explore original nodes: largegraph-viz serve {result.output}")
    logging.getLogger(__name__).info("Completed. Repeating the command reuses verified artifacts.")
    if args.open:
        import webbrowser

        webbrowser.open(result.report.as_uri())
