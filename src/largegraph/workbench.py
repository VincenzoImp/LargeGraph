"""User-facing commands sharing the typed analysis API."""

from __future__ import annotations

import dataclasses
import json
import logging
from importlib.resources import as_file, files
from pathlib import Path

from .api import Analysis, analyze, read_analysis_state
from .artifacts import verify_artifact
from .budget import default_resources, preflight
from .config import AnalysisOptions
from .runtime import Resources, configure_threads, environment, read_json


def resource_options(parser, memory="3GB"):
    parser.add_argument("--memory", default=memory, help="DuckDB buffer budget, not total RSS")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--batch-rows", type=int, default=250_000)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--temp-limit", default="80GB")


def command_resources(args, memory=None):
    return Resources(
        memory=args.memory or memory or "3GB",
        threads=args.threads,
        batch_rows=args.batch_rows,
        temp_dir=str(Path(args.temp_dir).resolve()) if args.temp_dir else None,
        temp_limit=args.temp_limit,
    )


def config_values(path, raw_args, values):
    if path:
        for name, value in read_json(path).items():
            if name not in values:
                raise ValueError(f"Unknown configuration key: {name}")
            option = "--" + name.replace("_", "-")
            if not any(item == option or item.startswith(option + "=") for item in raw_args):
                values[name] = value
    return values


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
    resource_options(run, memory=None)
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
    run.add_argument(
        "--backend", choices=["streaming", "clustre", "leiden", "networkit"], default="streaming"
    )
    run.add_argument("--clustre-binary", type=Path)
    run.add_argument("--clustre-mode", choices=["light", "light_plus"], default="light")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument(
        "--max-groups",
        type=int,
        default=128,
        help="Static-figure and large-forest display cap; interactive hierarchy has a safety cap of 1024 per level",
    )
    run.add_argument("--max-edges", type=int, default=1200)
    run.add_argument("--hierarchy-targets", nargs="+", type=int, default=[16, 64, 256])
    run.add_argument("--pixels", type=int, default=512)
    run.add_argument("--layout", choices=["auto", "sfdp", "igraph"], default="auto")
    run.add_argument(
        "--coordinates", type=Path, help="N x 2 .npy in prepared-node order; requires --images"
    )
    run.add_argument("--truth", type=Path, help="CSV with original node IDs and planted labels")
    run.add_argument("--truth-node", default="node_id")
    run.add_argument("--truth-label", default="planted_community")
    run.add_argument("--reference", action="store_true", help="Bounded Leiden quality comparison")
    for name in ("images", "hash-input", "ignore-extra-columns"):
        run.add_argument("--" + name, action="store_true")
    run.add_argument(
        "--dry-run", action="store_true", help="Inspect headers/resources without preparing data"
    )
    run.add_argument("--open", action="store_true", help="Open the portable report in a browser")
    gen = sub.add_parser("generate", help="Generate a fixed-edge-count synthetic graph")
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--config", type=Path, help="Generation defaults; explicit flags override")
    for name, default in (("nodes", 10_000), ("edges", 100_000), ("communities", 12), ("seed", 42)):
        gen.add_argument("--" + name, type=int, default=default)
    gen.add_argument("--mixing", type=float, default=0.08)
    gen.add_argument("--exponent", type=float, default=2.5)
    gen.add_argument(
        "--scenario",
        choices=["communities", "weak", "bridges", "core-periphery", "null"],
        default="communities",
    )
    resource_options(gen)
    prep = sub.add_parser("prepare", help="Build reusable on-disk graph artifacts")
    prep.add_argument("input", type=Path)
    prep.add_argument("--work-dir", type=Path, required=True)
    prep.add_argument("--nodes-file", type=Path)
    for name, default in (
        ("source", "source"),
        ("target", "target"),
        ("delimiter", ","),
        ("node-column", "node_id"),
    ):
        prep.add_argument("--" + name, default=default)
    for name in ("hash-input", "ignore-extra-columns"):
        prep.add_argument("--" + name, action="store_true")
    prep.add_argument("--export-metis", type=Path)
    resource_options(prep)
    validation = sub.add_parser("validate", help="Run scientific checks on a completed analysis")
    validation.add_argument("run", type=Path)
    validation.add_argument("--output", type=Path, required=True)
    validation.add_argument("--truth", type=Path)
    validation.add_argument("--truth-node", default="node_id")
    validation.add_argument("--truth-label", default="planted_community")
    validation.add_argument("--reference", action="store_true")
    validation.add_argument("--seed", type=int, default=42)
    resource_options(validation)
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


def dispatch(args, raw_args: list[str]) -> None:
    def emit(value):
        print(json.dumps(value, indent=2, allow_nan=False))

    if args.command == "generate":
        names = (
            "nodes",
            "edges",
            "communities",
            "mixing",
            "exponent",
            "seed",
            "scenario",
            "memory",
            "threads",
            "batch_rows",
            "temp_dir",
            "temp_limit",
        )
        values = config_values(args.config, raw_args, {name: getattr(args, name) for name in names})
        for name, value in values.items():
            setattr(args, name, value)
        resources = command_resources(args)
        configure_threads(resources.threads)
        from .generate import generate_graph

        print(
            generate_graph(
                args.output,
                **{name: values[name] for name in names[:7]},
                resources=resources,
            )
        )
        return
    if args.command == "prepare":
        resources = command_resources(args)
        from .prepare import export_metis, prepare_graph

        options = AnalysisOptions(
            **{
                name: getattr(args, name)
                for name in (
                    "source",
                    "target",
                    "delimiter",
                    "node_column",
                    "nodes_file",
                    "hash_input",
                    "ignore_extra_columns",
                )
            }
        )
        prepared = prepare_graph(args.input, args.work_dir, resources, **options.prepare_kwargs())
        if args.export_metis:
            export_metis(prepared, args.export_metis, resources.batch_rows * 4)
        print(prepared)
        return
    if args.command == "validate":
        resources = command_resources(args)
        from .validate import validate_graph

        result = Analysis.open(args.run)
        if args.output.exists():
            raise FileExistsError(f"Validation output already exists: {args.output}")
        emit(
            validate_graph(
                result.prepared,
                result.clustering,
                result.quotient,
                args.output,
                resources,
                args.truth,
                args.reference,
                args.seed,
                args.truth_node,
                args.truth_label,
            )
        )
        return
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
        state = read_analysis_state(args.run)
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
        assets = files("largegraph").joinpath("assets")
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
        values = config_values(args.config, raw_args, values)
        for name in ("nodes_file", "clustre_binary", "coordinates", "truth"):
            if values[name] is not None:
                values[name] = Path(values[name])
        values["hierarchy_targets"] = tuple(values["hierarchy_targets"])
        options = AnalysisOptions(**values)
        defaults = default_resources(args.ram, args.threads)
        resources = command_resources(args, defaults.memory)
        if options.images:
            import importlib.util

            for package in ("matplotlib", "scipy"):
                if importlib.util.find_spec(package) is None:
                    raise ValueError("Static figures require largegraph[images]")
        if args.dry_run:
            emit(
                preflight(
                    args.input,
                    args.work_dir or args.output,
                    resources,
                    args.ram,
                    options.delimiter,
                    options,
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
    print(f"Explore original nodes: largegraph serve {result.output}")
    logging.getLogger(__name__).info("Completed. Repeating the command reuses verified artifacts.")
    if args.open:
        import webbrowser

        webbrowser.open(result.report.as_uri())
