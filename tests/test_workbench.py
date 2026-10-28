"""Public workflows, exact new operations, recovery and corruption detection."""

import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from largegraph_viz import Analysis, AnalysisOptions, Resources, analyze
from largegraph_viz.artifacts import Checkpoints, verify_artifact
from largegraph_viz.cluster import native_cluster
from largegraph_viz.prepare import prepare_graph
from largegraph_viz.runtime import read_json

R = Resources(memory="128MB", threads=1, batch_rows=3)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "edges.csv"
    path.write_text("source,target\n001,b\nb,c\nc,001\nc,d\nx,y\nx,z\ny,z\n")
    return path


def test_complete_analysis_portable_report_and_index(source, tmp_path):
    result = analyze(
        source, tmp_path / "run", resources=R, options=AnalysisOptions(hierarchy_targets=(2, 4))
    )
    assert result.report.is_file()
    assert "__REPORT_DATA__" not in result.report.read_text(encoding="utf-8")
    assert "https://cdn" not in result.report.read_text(encoding="utf-8")
    assert Analysis.open(result.output) == result
    query = result.neighbors("001", limit=1)
    assert query["node"]["original_id"] == "001"
    assert query["degree"] == 2
    assert query["returned"] == 1 and query["truncated"]
    profile = read_json(result.profile / "profile.json")
    assert profile["components"] == 2
    assert profile["largest_component_nodes"] == 4
    assert profile["edges"] == 7
    data = read_json(result.report.parent / "report.json")
    for level in data["levels"]:
        assert sum(node["size"] for node in level["nodes"]) == 7
        assert sum(node["volume"] for node in level["nodes"]) == 14
    assert data["levels"][-1]["kind"] == "detected"
    assert all(node["leaf"] is not None for node in data["levels"][-1]["nodes"])
    times = {path: path.stat().st_mtime_ns for path in result.output.rglob("manifest.json")}
    assert (
        analyze(
            source, result.output, resources=R, options=AnalysisOptions(hierarchy_targets=(2, 4))
        )
        == result
    )
    assert all(path.stat().st_mtime_ns == modified for path, modified in times.items())
    assert verify_artifact(result.prepared)["valid"]


def test_parquet_and_csv_are_semantically_identical(source, tmp_path):
    table = pa.table(
        {
            "source": ["001", "b", "c", "c", "x", "x", "y"],
            "target": ["b", "c", "001", "d", "y", "z", "z"],
        }
    )
    parquet = tmp_path / "input.parquet"
    pq.write_table(table, parquet)
    a, b = (prepare_graph(path, tmp_path / "cache", R) for path in (source, parquet))
    assert pq.read_table(a / "nodes.parquet").equals(pq.read_table(b / "nodes.parquet"))
    assert (a / "neighbors.u32").read_bytes() == (b / "neighbors.u32").read_bytes()


def test_preparation_restarts_only_interrupted_phase(source, tmp_path, monkeypatch):
    original = Checkpoints.commit

    def fail(self, name, value=True):
        original(self, name, value)
        if name == "canonical_edges":
            raise KeyboardInterrupt("simulated process interruption")

    monkeypatch.setattr(Checkpoints, "commit", fail)
    with pytest.raises(KeyboardInterrupt):
        prepare_graph(source, tmp_path / "cache", R)
    partial = next((tmp_path / "cache").glob("*.inprogress"))
    modified = (partial / "edges.parquet").stat().st_mtime_ns
    monkeypatch.setattr(Checkpoints, "commit", original)

    def no_csv_scan(*args, **kwargs):
        raise AssertionError("Completed ingestion must not scan CSV again")

    monkeypatch.setattr("largegraph_viz.prepare.read_csv_query", no_csv_scan)
    completed = prepare_graph(source, tmp_path / "cache", R)
    assert (completed / "edges.parquet").stat().st_mtime_ns == modified
    assert read_json(completed / "manifest.json")["edges"] == 7


def test_native_pass_recovery_reproduces_uninterrupted_result(source, tmp_path, monkeypatch):
    from largegraph_viz import cluster

    prepared = prepare_graph(source, tmp_path / "cache", R)
    expected, expected_history = native_cluster(prepared, 5, 1, R)
    original = cluster.modularity
    calls = 0

    def fail_after_first_pass(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("interrupted second pass")
        return original(*args, **kwargs)

    monkeypatch.setattr(cluster, "modularity", fail_after_first_pass)
    checkpoint = tmp_path / "passes"
    with pytest.raises(KeyboardInterrupt):
        native_cluster(prepared, 5, 1, R, checkpoint)
    assert len(read_json(checkpoint / "pass.json")["history"]) == 1
    monkeypatch.setattr(cluster, "modularity", original)
    actual, history = native_cluster(prepared, 5, 1, R, checkpoint)
    np.testing.assert_array_equal(expected, actual)
    assert expected_history == history


def test_failed_report_preserves_expensive_completed_work(source, tmp_path, monkeypatch):
    from largegraph_viz import report

    original = report.write_report

    def disk_full(*args):
        raise OSError(28, "Simulated disk full")

    monkeypatch.setattr(report, "write_report", disk_full)
    run = tmp_path / "run"
    with pytest.raises(OSError, match="disk full"):
        analyze(source, run, resources=R)
    assert read_json(run / "analysis.json")["status"] == "failed"
    assert not (run / "report").exists()
    preparation = next(path for path in (run / "cache").glob("prepared-*") if path.is_dir())
    modified = (preparation / "manifest.json").stat().st_mtime_ns
    monkeypatch.setattr(report, "write_report", original)
    result = analyze(source, run, resources=R)
    assert result.report.exists()
    assert (result.prepared / "manifest.json").stat().st_mtime_ns == modified


def test_truncated_cache_is_rejected(source, tmp_path):
    prepared = prepare_graph(source, tmp_path / "cache", R)
    (prepared / "neighbors.u32").write_bytes(b"bad")
    assert not verify_artifact(prepared)["valid"]
    with pytest.raises(ValueError, match="Invalid cache"):
        prepare_graph(source, tmp_path / "cache", R)


def test_exports_include_internal_edges_and_isolated_groups(source, tmp_path):
    result = analyze(source, tmp_path / "run", resources=R)
    export = result.export(tmp_path / "graphml", "graphml", R)
    root = ET.parse(export / "summary.graphml").getroot()
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    assert (
        len(root.findall("g:graph/g:node", ns))
        == read_json(result.quotient / "manifest.json")["communities"]
    )
    assert (
        sum(int(edge.find("g:data", ns).text) for edge in root.findall("g:graph/g:edge", ns)) == 7
    )
    csv_export = result.export(tmp_path / "csv", "csv", R)
    assert (csv_export / "edges.csv").read_text().startswith("source,target,weight")


def test_config_rejected_before_input_is_opened(tmp_path):
    with pytest.raises(ValueError, match="max_groups"):
        AnalysisOptions(max_groups=2000)
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "largegraph_viz",
            "analyze",
            str(tmp_path / "missing.csv"),
            "--output",
            str(tmp_path / "run"),
            "--max-groups",
            "2000",
        ],
        text=True,
        capture_output=True,
    )
    assert process.returncode == 2
    assert "max_groups" in process.stderr
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize(
    "settings",
    [
        {"seed": -1},
        {"passes": 1.5},
        {"max_edges": 1.5},
        {"images": "false"},
        {"hierarchy_targets": (2.5, 4)},
    ],
)
def test_invalid_json_types_and_seed_fail_before_a_job(settings):
    with pytest.raises(ValueError):
        AnalysisOptions(**settings)


@pytest.mark.parametrize("settings", [{"threads": 1.5}, {"batch_rows": 2.5}, {"threads": True}])
def test_invalid_resource_types_fail_at_configuration(settings):
    with pytest.raises(ValueError):
        Resources(**settings)


def test_preflight_checks_custom_headers_and_optional_node_file(source, tmp_path):
    from largegraph_viz.budget import preflight

    with pytest.raises(ValueError, match="do not contain"):
        preflight(source, tmp_path / "out", R, options=AnalysisOptions(source="missing"))
    with pytest.raises(FileNotFoundError):
        preflight(
            source,
            tmp_path / "out",
            R,
            options=AnalysisOptions(nodes_file=tmp_path / "missing.csv"),
        )
    assert not (tmp_path / "out").exists()


def test_changed_configuration_does_not_replace_report(source, tmp_path):
    result = analyze(source, tmp_path / "run", resources=R)
    original = result.report.read_bytes()
    with pytest.raises(ValueError, match="different input/configuration"):
        analyze(source, result.output, resources=R, options=AnalysisOptions(resolution=2))
    assert result.report.read_bytes() == original


def test_member_cursor_never_duplicates_rows(source, tmp_path):
    result = analyze(source, tmp_path / "run", resources=R)
    first = result.neighbors("001")["node"]
    page1 = result.members(first["community"], limit=1)
    assert page1["has_more"]
    page2 = result.members(first["community"], limit=1, after=page1["next_after"])
    assert page2["members"][0]["node_id"] > page1["members"][0]["node_id"]
