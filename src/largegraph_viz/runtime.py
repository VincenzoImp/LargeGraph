"""Resource policy, atomic artifacts, fingerprints and process-tree monitoring."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

LOG = logging.getLogger("largegraph_viz")


def literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


@dataclass(frozen=True)
class Resources:
    memory: str = "3GB"
    threads: int = 2
    batch_rows: int = 250_000
    temp_dir: str | None = None
    temp_limit: str = "80GB"

    def __post_init__(self):
        for value in (self.memory, self.temp_limit):
            if not re.fullmatch(r"[1-9][0-9]*(?:MB|GB|MiB|GiB)", value):
                raise ValueError("Memory sizes must be positive integer MB, GB, MiB or GiB")
        if self.threads < 1 or self.batch_rows < 1:
            raise ValueError("threads and batch_rows must be positive")

    def connect(self, directory: Path):
        import duckdb

        directory.mkdir(parents=True, exist_ok=True)
        spill = Path(self.temp_dir).resolve() if self.temp_dir else directory / "spill"
        spill.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(directory / "scratch.duckdb"))
        for key, value in {
            "memory_limit": self.memory,
            "threads": self.threads,
            "temp_directory": str(spill),
            "max_temp_directory_size": self.temp_limit,
            "preserve_insertion_order": False,
        }.items():
            con.execute(f"SET {key} = {literal(value) if isinstance(value, str) else value}")
        con.execute("SET enable_progress_bar = false")
        return con


def configure_threads(threads: int):
    # Call before importing NumPy/igraph/Numba in CLI entry points.
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[key] = str(threads)
    os.environ.setdefault("MPLBACKEND", "Agg")


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text())


def signature(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def fingerprint(path: Path, full_hash: bool = False) -> dict:
    path = path.resolve(strict=True)
    stat = path.stat()
    result = {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if full_hash:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        result["sha256"] = digest.hexdigest()
    return result


def environment() -> dict:
    versions = {}
    for package in (
        "largegraph-viz",
        "numpy",
        "duckdb",
        "pyarrow",
        "matplotlib",
        "scipy",
        "igraph",
        "leidenalg",
        "numba",
        "psutil",
        "scikit-learn",
    ):
        with contextlib.suppress(importlib.metadata.PackageNotFoundError):
            versions[package] = importlib.metadata.version(package)
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "versions": versions,
    }


@contextlib.contextmanager
def artifact_directory(destination: Path):
    """Never replace an existing artifact, including partially finished work."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / (destination.name + ".lock")
    with lock.open("a") as handle:
        # POSIX advisory lock releases on process death, unlike lock-file existence.
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_EX)
        if destination.exists():
            raise FileExistsError(f"Artifact already exists: {destination}")
        temporary = destination.parent / (destination.name + ".inprogress")
        if temporary.exists():
            raise FileExistsError(
                f"Interrupted artifact exists: {temporary}; inspect/move it first"
            )
        temporary.mkdir()
        try:
            yield temporary
            temporary.rename(destination)
        except BaseException:
            LOG.error("Incomplete work retained at %s", temporary)
            raise


class Monitor:
    """Sample summed RSS of process and children; not a hard RAM limiter."""

    def __init__(
        self, directory: Path | None = None, interval: float = 0.2, spill_dir: Path | None = None
    ):
        self.directory, self.interval = directory.resolve() if directory else None, interval
        self.spill_dir = (
            spill_dir.resolve()
            if spill_dir
            else (self.directory / "spill" if self.directory else None)
        )
        self.stop_event = threading.Event()
        self.stats = {
            "peak_process_tree_rss_bytes": 0,
            "peak_working_disk_bytes": 0,
            "peak_spill_bytes": 0,
            "samples": 0,
        }

    def sample(self):
        import psutil

        process = psutil.Process()
        total = 0
        for item in [process, *process.children(recursive=True)]:
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                total += item.memory_info().rss
        self.stats["peak_process_tree_rss_bytes"] = max(
            self.stats["peak_process_tree_rss_bytes"], total
        )
        if self.directory and self.directory.exists():
            disk = spill = 0
            for root, _, files in os.walk(self.directory):
                for filename in files:
                    with contextlib.suppress(FileNotFoundError):
                        path = Path(root) / filename
                        size = path.stat().st_size
                        disk += size
                        if (
                            self.spill_dir and path.is_relative_to(self.spill_dir)
                        ) or "duckdb_temp_storage" in filename:
                            spill += size
            if self.spill_dir and not self.spill_dir.is_relative_to(self.directory):
                for root, _, files in os.walk(self.spill_dir):
                    for filename in files:
                        with contextlib.suppress(FileNotFoundError):
                            size = (Path(root) / filename).stat().st_size
                            disk += size
                            spill += size
            self.stats["peak_working_disk_bytes"] = max(self.stats["peak_working_disk_bytes"], disk)
            self.stats["peak_spill_bytes"] = max(self.stats["peak_spill_bytes"], spill)
        self.stats["samples"] += 1

    def __enter__(self):
        self.start = time.perf_counter()
        self.sample()

        def run():
            while not self.stop_event.wait(self.interval):
                self.sample()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def snapshot(self):
        self.sample()
        return {**self.stats, "wall_seconds": time.perf_counter() - self.start}

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join()
        self.sample()
        self.stats["wall_seconds"] = time.perf_counter() - self.start


def cleanup_scratch(directory: Path):
    for name in ("scratch.duckdb", "scratch.duckdb.wal"):
        (directory / name).unlink(missing_ok=True)
    shutil.rmtree(directory / "spill", ignore_errors=True)


def resource_dict(resources: Resources):
    return asdict(resources)
