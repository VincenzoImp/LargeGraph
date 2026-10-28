"""Validated public configuration. Invalid jobs fail before reading the graph."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysisOptions:
    source: str = "source"
    target: str = "target"
    delimiter: str = ","
    nodes_file: Path | None = None
    node_column: str = "node_id"
    ignore_extra_columns: bool = False
    hash_input: bool = False
    backend: str = "streaming"
    passes: int = 5
    resolution: float = 1.0
    clustre_binary: Path | None = None
    clustre_mode: str = "light"
    max_groups: int = 128
    max_edges: int = 1200
    pixels: int = 512
    seed: int = 42
    hierarchy_targets: tuple[int, ...] = (16, 64, 256)
    images: bool = False

    def __post_init__(self) -> None:
        if not self.source or not self.target or self.source == self.target:
            raise ValueError("source and target must be distinct nonempty column names")
        if len(self.delimiter.encode()) != 1:
            raise ValueError("delimiter must be one ASCII byte")
        if self.passes < 1 or not math.isfinite(self.resolution) or self.resolution <= 0:
            raise ValueError("passes and resolution must be positive")
        if not 2 <= self.max_groups <= 1024:
            raise ValueError("max_groups must be between 2 and 1024")
        if self.max_edges < 0 or not 64 <= self.pixels <= 4096:
            raise ValueError("max_edges must be nonnegative and pixels must be between 64 and 4096")
        if not self.hierarchy_targets or any(
            not 2 <= item <= 1024 for item in self.hierarchy_targets
        ):
            raise ValueError("hierarchy_targets must contain values between 2 and 1024")
        if self.backend not in {"streaming", "clustre", "leiden"}:
            raise ValueError("Unknown clustering backend")
        if self.backend == "clustre":
            if not self.clustre_binary or not self.clustre_binary.is_file():
                raise ValueError("CluStRE requires an installed --clustre-binary")
            if self.resolution != 1 or self.clustre_mode not in {"light", "light_plus"}:
                raise ValueError("CluStRE supports light/light_plus and resolution=1")

    def prepare_kwargs(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "delimiter": self.delimiter,
            "nodes_path": self.nodes_file,
            "node_column": self.node_column,
            "hash_input": self.hash_input,
            "ignore_extra_columns": self.ignore_extra_columns,
        }
