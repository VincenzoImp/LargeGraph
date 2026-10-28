"""Cheap, explicit resource estimates; no estimate is a hard process limit."""

from __future__ import annotations

import contextlib
import csv
import io
import re
import shutil
from pathlib import Path

from .config import AnalysisOptions
from .runtime import Resources


def size_bytes(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)(MB|GB|MiB|GiB)", value)
    if not match:
        raise ValueError("Sizes require positive integer MB, GB, MiB or GiB")
    return int(match[1]) * {"MB": 10**6, "GB": 10**9, "MiB": 2**20, "GiB": 2**30}[match[2]]


def available_memory() -> int:
    import psutil

    available = psutil.virtual_memory().available
    # cgroup v2 can constrain a process even when host memory is plentiful.
    try:
        path = next(
            line.split(":", 2)[2]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        )
        root = Path("/sys/fs/cgroup") / path.lstrip("/")
        limit = (root / "memory.max").read_text().strip()
        current = int((root / "memory.current").read_text())
        if limit != "max":
            inactive_file = 0
            with contextlib.suppress(OSError, ValueError):
                statistics = dict(
                    line.split() for line in (root / "memory.stat").read_text().splitlines()
                )
                inactive_file = int(statistics.get("inactive_file", 0))
            # A full input hash can populate the cgroup with reclaimable file
            # pages. Treating that cache as live arrays falsely reports no RAM.
            available = min(available, int(limit), max(0, int(limit) - current + inactive_file))
    except (OSError, ValueError, StopIteration):
        pass
    return available


def default_resources(ram: str = "8GB", threads: int = 2) -> Resources:
    budget = size_bytes(ram)
    if budget < 1_000_000_000:
        raise ValueError("Use a RAM target of at least 1GB")
    # Leave room for arrays, Arrow batches, JIT compilation and renderer memory.
    memory_mb = min(3000, max(128, int(budget * 0.375 / 10**6)))
    return Resources(memory=f"{memory_mb}MB", threads=threads)


def preflight(
    input_path: Path,
    output: Path,
    resources: Resources,
    ram: str = "8GB",
    delimiter=",",
    options: AnalysisOptions | None = None,
) -> dict:
    """Inspect at most 1 MiB of CSV, or Parquet metadata; do not load graph arrays."""
    input_path = input_path.resolve(strict=True)
    input_bytes = input_path.stat().st_size
    if input_path.suffix.lower() in {".parquet", ".pq"}:
        import pyarrow.parquet as pq

        metadata = pq.ParquetFile(input_path)
        rows = metadata.metadata.num_rows
        columns = metadata.schema.names
        basis = "Parquet metadata (input rows, before canonicalization)"
    else:
        with input_path.open("rb") as stream:
            raw = stream.read(1024 * 1024)
        text = raw.decode("utf-8-sig", errors="replace")
        # Ignore a potentially incomplete last record in a truncated sample.
        if input_bytes > len(raw):
            text = text.rsplit("\n", 1)[0]
        records = csv.reader(io.StringIO(text), delimiter=delimiter)
        columns = next(records, [])
        sample_rows = sum(1 for _ in records)
        rows = round(sample_rows * input_bytes / max(1, len(raw)))
        basis = "CSV byte sample; multiline records and ID lengths can change the estimate"
    if options is not None:
        if options.source not in columns or options.target not in columns:
            raise ValueError(
                f"Input columns {columns} do not contain {options.source!r}, {options.target!r}"
            )
        if len(columns) != 2 and not options.ignore_extra_columns:
            raise ValueError(
                "Extra input columns require --ignore-extra-columns; weights/directions are not inferred"
            )
        if options.nodes_file:
            node_path = options.nodes_file.resolve(strict=True)
            if node_path.suffix.lower() in {".parquet", ".pq"}:
                import pyarrow.parquet as pq

                node_columns = pq.ParquetFile(node_path).schema.names
            else:
                with node_path.open(encoding="utf-8-sig", newline="") as stream:
                    node_columns = next(csv.reader(stream, delimiter=delimiter), [])
            if options.node_column not in node_columns:
                raise ValueError(f"Node file lacks column {options.node_column!r}")
    location = output.resolve()
    while not location.exists():
        parent = location.parent
        if parent == location:
            raise ValueError(f"Workspace volume is not available: {output}")
        location = parent
    free = shutil.disk_usage(location).free
    # Scratch tables + final symmetric uint32 adjacency + input. Deliberately rough.
    estimated_disk = max(input_bytes * 5, rows * 100)
    warnings = []
    if free < estimated_disk:
        warnings.append("Estimated workspace exceeds free disk; use a larger SSD/work directory")
    available = available_memory()
    target = size_bytes(ram)
    if target > available * 1.1:
        warnings.append(
            "RAM target exceeds currently available memory; lower --ram or close other jobs"
        )
    if size_bytes(resources.memory) > target // 2:
        warnings.append(
            "DuckDB budget exceeds half the RAM target; other stages need additional memory"
        )
    return {
        "input": str(input_path),
        "input_bytes": input_bytes,
        "columns": columns,
        "estimated_input_rows": rows,
        "estimate_basis": basis,
        "estimated_workspace_bytes": estimated_disk,
        "free_workspace_bytes": free,
        "ram_target_bytes": target,
        "available_memory_bytes": available,
        "duckdb_budget_bytes": size_bytes(resources.memory),
        "warnings": warnings,
        "hard_limit": False,
        "limits": "RAM target guides configuration, not an OS limit; use the Linux cgroup runner for enforcement. Estimates are not guarantees.",
    }
