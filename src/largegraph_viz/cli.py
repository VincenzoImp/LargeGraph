"""Command line entry points. Each view accepts the original edge CSV."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .runtime import Resources, configure_threads, read_json, write_json


def resource_options(parser):
    parser.add_argument(
        "--memory", default="3GB", help="DuckDB memory budget; not total process RSS"
    )
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--batch-rows", type=int, default=250_000)
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--temp-limit", default="80GB")


def input_options(parser, clustering=True):
    parser.add_argument("input", type=Path, help="CSV with source,target header")
    parser.add_argument("--work-dir", type=Path, default=Path("work"))
    parser.add_argument("--nodes-file", type=Path, help="Optional node CSV, including isolates")
    parser.add_argument("--node-column", default="node_id")
    parser.add_argument("--source", default="source")
    parser.add_argument("--target", default="target")
    parser.add_argument("--delimiter", default=",")
    parser.add_argument("--ignore-extra-columns", action="store_true")
    parser.add_argument(
        "--hash-input",
        action="store_true",
        help="Extra full SHA-256 scan, recommended for paper runs",
    )
    if clustering:
        parser.add_argument(
            "--backend",
            choices=["streaming", "clustre", "leiden", "networkit"],
            default="streaming",
        )
        parser.add_argument("--passes", type=int, default=5)
        parser.add_argument("--resolution", type=float, default=1)
        parser.add_argument("--clustre-binary", type=Path)
        parser.add_argument("--clustre-mode", choices=["light", "light_plus"], default="light")
    resource_options(parser)


def build_parser():
    parser = argparse.ArgumentParser(description="Disk-backed large graph visualization")
    parser.add_argument("--verbose", action="store_true")
    from . import __version__
    from .workbench import add_commands

    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    add_commands(sub)
    gen = sub.add_parser("generate", help="Generate a fixed-m simple degree-corrected block graph")
    gen.add_argument(
        "--config",
        type=Path,
        help="JSON generation/resource defaults; explicit flags take precedence",
    )
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--nodes", type=int, default=10_000)
    gen.add_argument("--edges", type=int, default=100_000)
    gen.add_argument("--communities", type=int, default=12)
    gen.add_argument("--mixing", type=float, default=0.08)
    gen.add_argument("--exponent", type=float, default=2.5)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument(
        "--scenario",
        choices=["communities", "weak", "bridges", "core-periphery", "null"],
        default="communities",
    )
    resource_options(gen)
    prep = sub.add_parser("prepare", help="Canonicalize CSV and build adjacency on disk")
    input_options(prep, clustering=False)
    prep.add_argument("--export-metis", type=Path)
    for command in ("community", "matrix", "density", "validate", "all"):
        view = sub.add_parser(command)
        input_options(view)
        view.add_argument("--output", type=Path, required=True)
        view.add_argument("--max-groups", type=int, default=128)
        view.add_argument(
            "--max-edges",
            type=int,
            default=1200,
            help="Image filtering only; exact quotient is retained",
        )
        view.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Layout/reference and CluStRE seed; native clustering is deterministic",
        )
        view.add_argument("--layout", choices=["auto", "sfdp", "igraph"], default="auto")
        view.add_argument("--levels", type=int, nargs="+", default=[32, 128])
        view.add_argument("--pixels", type=int, default=1024)
        view.add_argument(
            "--coordinates",
            type=Path,
            help="Numeric N x 2 .npy in prepared node order (density only)",
        )
        view.add_argument("--truth", type=Path)
        view.add_argument("--truth-node", default="node_id")
        view.add_argument("--truth-label", default="planted_community")
        view.add_argument(
            "--reference", action="store_true", help="Run Leiden only below documented safety caps"
        )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    raw_args = list(sys.argv[1:] if argv is None else argv)
    from .workbench import COMMANDS, dispatch

    if args.command in COMMANDS:
        configure_threads(getattr(args, "threads", 2))
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        logging.getLogger("fontTools").setLevel(logging.WARNING)
        try:
            dispatch(args, raw_args)
        except KeyboardInterrupt:
            parser.exit(130, "Interrupted. Rerun the same analyze command to resume.\n")
        except Exception as exc:
            if args.verbose:
                logging.getLogger(__name__).exception("Command failed")
            parser.exit(2, f"error: {exc}\n")
        return
    if args.command == "generate" and args.config:
        config = read_json(args.config)
        allowed = {
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
            "temp_limit",
            "temp_dir",
        }
        for key, value in config.items():
            if key.startswith("estimated_") or key == "estimate_is_not_a_guarantee":
                continue
            if key not in allowed:
                parser.error(f"Unknown configuration key: {key}")
            option = "--" + key.replace("_", "-")
            if not any(item == option or item.startswith(option + "=") for item in raw_args):
                setattr(
                    args, key, Path(value) if key == "temp_dir" and value is not None else value
                )
    if args.threads < 1 or args.batch_rows < 1:
        parser.error("--threads and --batch-rows must be positive")
    if args.command not in {"generate", "prepare"}:
        from .config import AnalysisOptions

        try:
            AnalysisOptions(
                passes=args.passes,
                resolution=args.resolution,
                backend=args.backend,
                clustre_binary=args.clustre_binary,
                clustre_mode=args.clustre_mode,
                max_groups=args.max_groups,
                max_edges=args.max_edges,
                pixels=args.pixels,
                hierarchy_targets=tuple(args.levels),
            )
        except ValueError as exc:
            parser.error(str(exc))
        if args.coordinates and args.command not in {"density", "all"}:
            parser.error("--coordinates is only valid for density/all")
    configure_threads(args.threads)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    try:
        resources = Resources(
            memory=args.memory,
            threads=args.threads,
            batch_rows=args.batch_rows,
            temp_dir=str(args.temp_dir.resolve()) if args.temp_dir else None,
            temp_limit=args.temp_limit,
        )
    except ValueError as exc:
        parser.error(str(exc))
    try:
        if args.command == "generate":
            from .generate import generate_graph

            result = generate_graph(
                args.output,
                args.nodes,
                args.edges,
                args.communities,
                args.mixing,
                args.exponent,
                args.seed,
                args.scenario,
                resources,
            )
            print(result)
            return
        from .prepare import export_metis, prepare_graph

        prepared = prepare_graph(
            args.input,
            args.work_dir,
            resources,
            source=args.source,
            target=args.target,
            delimiter=args.delimiter,
            nodes_path=args.nodes_file,
            node_column=args.node_column,
            hash_input=args.hash_input,
            ignore_extra_columns=args.ignore_extra_columns,
        )
        if args.command == "prepare":
            if args.export_metis:
                export_metis(prepared, args.export_metis, resources.batch_rows * 4)
            print(prepared)
            return
        if args.coordinates and args.command not in {"density", "all"}:
            parser.error("--coordinates is only valid for density/all")
        if args.command == "density" and args.coordinates:
            from .views import render_coordinates

            render_coordinates(args.coordinates, prepared, args.output, resources, args.pixels)
            print(args.output.resolve())
            return
        from .aggregate import aggregate_graph
        from .cluster import cluster_graph

        clustering = cluster_graph(
            prepared,
            resources,
            args.backend,
            args.passes,
            args.resolution,
            args.clustre_binary,
            args.clustre_mode,
            seed=args.seed,
        )
        quotient = aggregate_graph(prepared, clustering, resources)
        args.output.mkdir(parents=True, exist_ok=True)
        if args.command in {"community", "all"}:
            from .views import render_community

            render_community(
                quotient,
                args.output / "community" if args.command == "all" else args.output,
                resources,
                args.max_groups,
                args.max_edges,
                args.seed,
                args.layout,
            )
        if args.command in {"matrix", "all"}:
            from .views import render_matrix

            render_matrix(
                quotient,
                args.output / "matrix" if args.command == "all" else args.output,
                resources,
                args.max_groups,
            )
        if args.command in {"density", "all"}:
            from .views import render_coordinates, render_density

            target = args.output / "density" if args.command == "all" else args.output
            if args.coordinates:
                render_coordinates(args.coordinates, prepared, target, resources, args.pixels)
            else:
                render_density(
                    quotient,
                    target,
                    resources,
                    args.levels,
                    args.pixels,
                    args.max_edges,
                    args.seed,
                    args.layout,
                )
        if args.command in {"validate", "all"}:
            from .validate import validate_graph

            validate_graph(
                prepared,
                clustering,
                quotient,
                args.output / "validation" if args.command == "all" else args.output,
                resources,
                args.truth,
                args.reference,
                args.seed,
                args.truth_node,
                args.truth_label,
            )
        write_json(
            args.output / "pipeline.json",
            {
                "prepared": str(prepared),
                "clustering": str(clustering),
                "quotient": str(quotient),
                "command": vars(args)
                | {key: str(value) for key, value in vars(args).items() if isinstance(value, Path)},
            },
        )
        print(args.output.resolve())
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
