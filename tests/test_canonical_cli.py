"""The public CLI, research benchmarks and API share a single current workflow."""

import json
import subprocess
import sys

import numpy as np
import pytest

from largegraph import Analysis, Resources, analyze
from largegraph.runtime import read_json, write_json


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, "-m", "largegraph", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    return result


def test_cli_generation_analysis_and_independent_validation(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("leidenalg")
    data, output = tmp_path / "data", tmp_path / "analysis"
    config = tmp_path / "generation.json"
    write_json(config, {"nodes": 64, "edges": 96, "communities": 4, "threads": 1})
    run_cli("generate", "--config", config, "--output", data, "--nodes", 32, "--memory", "128MB")
    angles = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    coordinates = tmp_path / "coordinates.npy"
    np.save(coordinates, np.column_stack((np.cos(angles), np.sin(angles))))
    analysis_args = (
        "analyze",
        data / "edges.csv",
        "--output",
        output,
        "--nodes-file",
        data / "nodes.csv",
        "--truth",
        data / "nodes.csv",
        "--reference",
        "--images",
        "--coordinates",
        coordinates,
        "--layout",
        "igraph",
        "--hierarchy-targets",
        2,
        4,
        "--max-groups",
        8,
        "--pixels",
        64,
        "--memory",
        "128MB",
        "--threads",
        1,
    )
    run_cli(*analysis_args)
    result = Analysis.open(output)
    report = result.report.parent
    assert read_json(report / "report.json")["graph"]["nodes"] == 32
    assert read_json(report / "report.json")["graph"]["edges"] == 96
    checks = read_json(report / "validation" / "validation.json")
    assert checks["all_checks_pass"]
    assert "adjusted_rand_index" in checks["planted_recovery"]
    assert checks["leiden_reference"]["status"] == "completed"
    assert list((report / "images" / "coordinates").glob("*.png"))
    validation = tmp_path / "validation"
    run_cli("validate", output, "--output", validation, "--truth", data / "nodes.csv")
    assert read_json(validation / "validation.json")["all_checks_pass"]
    # A changed auxiliary input must not silently reuse a completed report.
    np.save(coordinates, np.column_stack((np.sin(angles), np.cos(angles))))
    changed = subprocess.run(
        [sys.executable, "-m", "largegraph", *map(str, analysis_args)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert changed.returncode == 2
    assert "different input/configuration" in changed.stderr


def test_research_benchmark_retains_a_verifiable_analysis(tmp_path):
    pytest.importorskip("matplotlib")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "largegraph.benchmark",
            "--output",
            str(tmp_path),
            "--sizes",
            "32",
            "--mean-degree",
            "6",
            "--communities",
            "4",
            "--hierarchy-targets",
            "2",
            "4",
            "--pixels",
            "64",
            "--memory",
            "128MB",
            "--threads",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    case = tmp_path / "n32-communities-s42"
    analysis = Analysis.open(case / "analysis")
    assert analysis.report.is_file()
    assert read_json(case / "report.json")["validation"]["all_checks_pass"]
    run_cli("verify", analysis.output, "--deep")


def test_superseded_analysis_format_is_rejected_without_migration(tmp_path):
    edges = tmp_path / "edges.csv"
    edges.write_text("source,target\na,b\nb,c\n")
    result = analyze(edges, tmp_path / "run", resources=Resources(memory="128MB", threads=1))
    original = result.report.read_bytes()
    state_path = result.output / "analysis.json"
    state = json.loads(state_path.read_text())
    state["config"]["version"] = 1
    write_json(state_path, state)
    with pytest.raises(ValueError, match="Unsupported analysis format"):
        Analysis.open(result.output)
    with pytest.raises(ValueError, match="Unsupported analysis format"):
        analyze(edges, result.output, resources=Resources(memory="128MB", threads=1))
    assert result.report.read_bytes() == original
