#!/usr/bin/env python3
"""Inspect dependencies and storage without network access or modifying the machine."""

import argparse
import importlib.util
import json
import shutil
from pathlib import Path

import _bootstrap  # noqa: F401

from largegraph_viz.runtime import environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--workspace", type=Path, default=Path("."))
parser.add_argument("--target-scale", action="store_true")
args = parser.parse_args()
modules = [
    "numpy",
    "duckdb",
    "pyarrow",
    "matplotlib",
    "scipy",
    "igraph",
    "leidenalg",
    "numba",
    "psutil",
]
found = {name: importlib.util.find_spec(name) is not None for name in modules}
free = shutil.disk_usage(args.workspace).free
result = {
    "environment": environment(),
    "modules": found,
    "free_workspace_bytes": free,
    "optional_sfdp": shutil.which("sfdp"),
    "all_required_modules_found": all(found.values()),
}
if args.target_scale:
    result["target_scale_disk_estimate_bytes"] = 100_000_000_000
    result["provisional_disk_check"] = free >= 100_000_000_000
print(json.dumps(result, indent=2))
raise SystemExit(0 if all(found.values()) and result.get("provisional_disk_check", True) else 1)
