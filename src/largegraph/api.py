"""Public Python API for the local graph workbench.

Heavy numerical imports are deferred until a job starts. Importing the package
or showing CLI help does not start the JIT or initialize a plotting backend.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from pathlib import Path

from .artifacts import cached_directory, file_lock, restart_partial, verify_artifact
from .budget import default_resources, preflight
from .config import AnalysisOptions
from .runtime import Resources, fingerprint, read_json, signature, write_json

LOG = logging.getLogger(__name__)
ANALYSIS_SCHEMA_VERSION = 2


def read_analysis_state(output: Path) -> dict:
    state = read_json(output / "analysis.json")
    if state.get("config", {}).get("version") != ANALYSIS_SCHEMA_VERSION:
        raise ValueError("Unsupported analysis format; recompute in a new output directory")
    return state


@dataclass(frozen=True)
class Analysis:
    """A completed analysis, its reusable cache artifacts and portable report."""

    output: Path
    prepared: Path
    clustering: Path
    quotient: Path
    profile: Path
    hierarchy: Path
    index: Path

    @property
    def report(self) -> Path:
        return self.output / "report" / "index.html"

    @classmethod
    def open(cls, output: str | Path) -> Analysis:
        output = Path(output).resolve()
        state = read_analysis_state(output)
        if state["status"] != "complete":
            raise ValueError("Analysis is incomplete; rerun its analyze command")
        paths = {name: (output / value).resolve() for name, value in state["artifacts"].items()}
        return cls(output=output, **paths)

    def neighbors(self, node: str, limit: int = 100) -> dict:
        from .query import neighbors

        return neighbors(self.prepared, self.index, node, limit)

    def members(self, community: int, limit: int = 100, after: int = -1) -> dict:
        from .query import members

        return members(self.index, community, limit, after)

    def export(
        self, output: str | Path, format: str = "parquet", resources: Resources | None = None
    ) -> Path:
        from .export import export_quotient

        return export_quotient(self.quotient, Path(output), resources or Resources(), format)


def analyze(
    input_path: str | Path,
    output: str | Path,
    *,
    work_dir: str | Path | None = None,
    options: AnalysisOptions | None = None,
    resources: Resources | None = None,
    ram: str = "8GB",
) -> Analysis:
    """Prepare, partition, profile and explore an undirected simple edge list.

    Repeating the same call resumes interrupted phases. A different input or
    analysis configuration requires a different output directory. Resource
    settings can change on retry without changing the graph's meaning.
    """
    import importlib.util
    import os

    from .aggregate import aggregate_graph
    from .cluster import cluster_graph
    from .hierarchy import build_hierarchy
    from .prepare import prepare_graph
    from .profile import profile_graph
    from .query import build_index
    from .report import copy_provenance, report_data, write_report
    from .validate import validate_graph

    options, resources = options or AnalysisOptions(), resources or default_resources(ram)
    for package, extra, needed in (
        ("matplotlib", "images", options.images),
        ("scipy", "images", options.images),
        ("leidenalg", "leiden", options.backend == "leiden" or options.reference),
        ("networkit", "networkit", options.backend == "networkit"),
    ):
        if needed and importlib.util.find_spec(package) is None:
            raise ValueError(f"This analysis requires largegraph[{extra}]")
    output = Path(output).resolve()
    work_dir = Path(work_dir).resolve() if work_dir else output / "cache"
    config = {
        "input": fingerprint(Path(input_path), options.hash_input),
        "nodes": fingerprint(options.nodes_file, options.hash_input)
        if options.nodes_file
        else None,
        "options": {
            key: str(value.resolve()) if isinstance(value, Path) else value
            for key, value in dataclasses.asdict(options).items()
        },
        "truth": fingerprint(options.truth, options.hash_input) if options.truth else None,
        "coordinates": fingerprint(options.coordinates, options.hash_input)
        if options.coordinates
        else None,
        "version": ANALYSIS_SCHEMA_VERSION,
    }
    job_id = signature(config)
    output.mkdir(parents=True, exist_ok=True)
    with file_lock(output / ".analysis.lock"):
        state_path = output / "analysis.json"
        if state_path.exists():
            state = read_analysis_state(output)
            if state["job_id"] != job_id:
                raise ValueError(
                    "Output belongs to a different input/configuration; choose a new --output"
                )
            if state["status"] == "complete":
                result = Analysis.open(output)
                for path in [
                    result.prepared,
                    result.clustering,
                    result.quotient,
                    result.profile,
                    result.hierarchy,
                    result.index,
                    output / "report",
                ]:
                    check = verify_artifact(path)
                    if not check["valid"]:
                        raise ValueError(f"Invalid artifact {path}: {check['errors']}")
                LOG.info("Analysis is complete; reusing %s", result.report)
                return result
        plan = preflight(Path(input_path), work_dir, resources, ram, options.delimiter, options)
        for warning in plan["warnings"]:
            LOG.warning("Preflight: %s", warning)
        write_json(output / "preflight.json", plan)
        artifacts: dict[str, Path] = {}

        def stage(name):
            LOG.info("Analysis phase: %s", name)
            write_json(
                state_path,
                {
                    "job_id": job_id,
                    "config": config,
                    "status": "running",
                    "phase": name,
                    "artifacts": {
                        key: os.path.relpath(value, output) for key, value in artifacts.items()
                    },
                },
            )

        try:
            stage("prepare")
            prepared = artifacts["prepared"] = prepare_graph(
                Path(input_path), work_dir, resources, **options.prepare_kwargs()
            )
            stage("cluster")
            clustering = artifacts["clustering"] = cluster_graph(
                prepared,
                resources,
                options.backend,
                options.passes,
                options.resolution,
                options.clustre_binary,
                options.clustre_mode,
                options.seed,
            )
            stage("aggregate")
            quotient = artifacts["quotient"] = aggregate_graph(prepared, clustering, resources)
            stage("profile")
            profile = artifacts["profile"] = profile_graph(prepared, resources)
            stage("hierarchy")
            hierarchy = artifacts["hierarchy"] = build_hierarchy(
                quotient, resources, options.hierarchy_targets
            )
            stage("index")
            index = artifacts["index"] = build_index(prepared, clustering, profile, resources)
            stage("report")
            with cached_directory(output / "report") as report:
                if report is not None:
                    restart_partial(report)
                    validation = validate_graph(
                        prepared,
                        clustering,
                        quotient,
                        report / "validation",
                        resources,
                        options.truth,
                        options.reference,
                        options.seed,
                        options.truth_node,
                        options.truth_label,
                    )
                    data = report_data(
                        quotient,
                        hierarchy,
                        profile,
                        clustering,
                        resources,
                        options.max_groups,
                        options.max_edges,
                        options.seed,
                        options.layout,
                    )
                    write_report(report, data)
                    copy_provenance(report, artifacts)
                    export_dir = report / "summary"
                    export_dir.mkdir()
                    import shutil

                    for filename in ("nodes.parquet", "edges.parquet"):
                        shutil.copyfile(quotient / filename, export_dir / filename)
                    if options.images:
                        try:
                            from .views import render_community, render_density, render_matrix
                        except ImportError as exc:
                            raise ValueError("Static figures require largegraph[images]") from exc
                        render_community(
                            quotient,
                            report / "images" / "community",
                            resources,
                            options.max_groups,
                            options.max_edges,
                            options.seed,
                            options.layout,
                        )
                        render_matrix(
                            quotient, report / "images" / "matrix", resources, options.max_groups
                        )
                        render_density(
                            quotient,
                            report / "images" / "density",
                            resources,
                            options.hierarchy_targets,
                            options.pixels,
                            options.max_edges,
                            options.seed,
                            options.layout,
                        )
                        if options.coordinates:
                            from .views import render_coordinates

                            render_coordinates(
                                options.coordinates,
                                prepared,
                                report / "images" / "coordinates",
                                resources,
                                options.pixels,
                            )
                    write_json(
                        report / "manifest.json",
                        {
                            "kind": "report",
                            "job_id": job_id,
                            "schema": 1,
                            "validation_passed": validation["all_checks_pass"],
                            "config": config,
                        },
                    )
            write_json(
                state_path,
                {
                    "job_id": job_id,
                    "config": config,
                    "status": "complete",
                    "phase": "complete",
                    "artifacts": {
                        key: os.path.relpath(value, output) for key, value in artifacts.items()
                    },
                },
            )
            return Analysis(output, prepared, clustering, quotient, profile, hierarchy, index)
        except BaseException as exc:
            state = read_json(state_path)
            state.update(
                status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                error=str(exc),
            )
            write_json(state_path, state)
            raise
