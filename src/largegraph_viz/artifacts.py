"""Locked, immutable artifacts with bounded integrity checks and phase recovery."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from .runtime import read_json, write_json

LOG = logging.getLogger(__name__)
INVENTORY_VERSION = 1


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """An OS advisory lock, released even after process termination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seal(directory: Path) -> None:
    """Record a baseline SHA-256 for every file before committing an artifact."""
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name not in {"inventory.json", "owner.json", "checkpoint.json"}:
            size = path.stat().st_size
            files[path.relative_to(directory).as_posix()] = {
                "size": size,
                "sha256": sha256(path),
            }
    write_json(directory / "inventory.json", {"version": INVENTORY_VERSION, "files": files})


def verify_artifact(directory: Path, deep: bool = False) -> dict:
    """Check lengths and available hashes; deep additionally scans large files."""
    inventory = directory / "inventory.json"
    if not inventory.exists():
        return {"valid": False, "errors": ["Missing inventory; legacy artifact requires rebuild"]}
    try:
        record = read_json(inventory)
        errors = []
        if record["version"] != INVENTORY_VERSION:
            errors.append("Unsupported inventory version")
        for name, entry in record["files"].items():
            path = directory / name
            if not path.resolve().is_relative_to(directory.resolve()):
                errors.append(f"Invalid inventory path: {name}")
            elif not path.is_file() or path.stat().st_size != entry["size"]:
                errors.append(f"Missing or truncated file: {name}")
            elif (deep or entry["size"] <= 8 * 1024 * 1024) and entry["sha256"]:
                if sha256(path) != entry["sha256"]:
                    errors.append(f"Checksum mismatch: {name}")
        hashes = (
            {name: entry["sha256"] for name, entry in record["files"].items()}
            if deep and not errors
            else {}
        )
        return {"valid": not errors, "errors": errors, "deep_hashes": hashes}
    except (KeyError, TypeError, ValueError) as exc:
        return {"valid": False, "errors": [f"Malformed inventory: {exc}"]}


@contextlib.contextmanager
def cached_directory(destination: Path) -> Iterator[Path | None]:
    """Check the cache *inside* the lock; resume only owned partial directories.

    A None result means a verified completed artifact already exists. Callers
    return immediately in that case. Completed artifacts are never overwritten.
    """
    destination = destination.resolve()
    with file_lock(destination.with_name(destination.name + ".lock")):
        if destination.exists():
            check = verify_artifact(destination)
            if not check["valid"]:
                raise ValueError(
                    f"Invalid cache at {destination}: {check['errors']}; move it aside to rebuild"
                )
            LOG.info("Reusing verified %s", destination.name)
            yield None
            return
        partial = destination.with_name(destination.name + ".inprogress")
        if partial.exists():
            if partial.is_symlink() or not (partial / "owner.json").is_file():
                raise ValueError(
                    f"Unrecognized partial artifact: {partial}; move it aside before retrying"
                )
            owner = read_json(partial / "owner.json")
            if owner != {"artifact": destination.name, "schema": 1}:
                raise ValueError(f"Partial artifact ownership mismatch: {partial}")
        partial.mkdir(exist_ok=True)
        write_json(partial / "owner.json", {"artifact": destination.name, "schema": 1})
        try:
            yield partial
            if not (partial / "manifest.json").is_file():
                raise RuntimeError("Artifact builder did not write its manifest")
            seal(partial)
            partial.rename(destination)
        except BaseException:
            LOG.warning("Recoverable work retained at %s; rerun the same command", partial)
            raise


class Checkpoints:
    """A phase commits only after all of its outputs are durable to the application."""

    def __init__(self, directory: Path):
        self.path = directory / "checkpoint.json"
        self.data = read_json(self.path) if self.path.exists() else {}

    def done(self, name: str) -> bool:
        return name in self.data

    def commit(self, name: str, value=True) -> None:
        self.data[name] = value
        write_json(self.path, self.data)
        LOG.info("Completed phase: %s", name)


def restart_partial(directory: Path) -> None:
    """For single-phase derived artifacts, restart only their private partial data."""
    for item in directory.iterdir():
        if item.name == "owner.json":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
