"""Portable exact quotient exports; no expansion to original edges."""

from __future__ import annotations

import shutil
from pathlib import Path

from .artifacts import cached_directory, restart_partial
from .prepare import batches, copy_query
from .runtime import Resources, literal, read_json, write_json


def export_quotient(quotient: Path, output: Path, resources: Resources, format="parquet") -> Path:
    if format not in {"parquet", "csv", "graphml"}:
        raise ValueError("format must be parquet, csv or graphml")
    config = {"source": read_json(quotient / "manifest.json"), "format": format}
    with cached_directory(output) as out:
        if out is None:
            if read_json(output / "manifest.json")["config"] != config:
                raise ValueError("Export output already contains a different summary/format")
            return output
        restart_partial(out)
        if format == "parquet":
            for name in ("nodes.parquet", "edges.parquet"):
                shutil.copyfile(quotient / name, out / name)
        elif format == "csv":
            con = resources.connect(out)
            try:
                for name in ("nodes", "edges"):
                    copy_query(
                        con,
                        f"SELECT * FROM read_parquet({literal(quotient / (name + '.parquet'))})",
                        out / (name + ".csv"),
                        csv=True,
                    )
            finally:
                con.close()
            from .runtime import cleanup_scratch

            cleanup_scratch(out)
        else:
            with (out / "summary.graphml").open("w", encoding="utf-8") as stream:
                stream.write(
                    '<?xml version="1.0" encoding="utf-8"?>\n<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n'
                )
                stream.write(
                    '<key id="size" for="node" attr.name="node_count" attr.type="long"/>\n<key id="weight" for="edge" attr.name="weight" attr.type="long"/>\n<graph edgedefault="undirected">\n'
                )
                for batch in batches(
                    quotient / "nodes.parquet", resources.batch_rows, ["community", "node_count"]
                ):
                    for node, size in zip(
                        batch.column(0).to_pylist(), batch.column(1).to_pylist(), strict=True
                    ):
                        stream.write(f'<node id="c{node}"><data key="size">{size}</data></node>\n')
                for batch in batches(quotient / "edges.parquet", resources.batch_rows):
                    for source, target, weight in zip(
                        *(batch.column(i).to_pylist() for i in range(3)), strict=True
                    ):
                        stream.write(
                            f'<edge source="c{source}" target="c{target}"><data key="weight">{weight}</data></edge>\n'
                        )
                stream.write("</graph>\n</graphml>\n")
        write_json(
            out / "manifest.json",
            {
                "kind": "export",
                "config": config,
                "semantics": "Weighted community quotient; one diagonal self-loop per internal undirected edge count. Counts include the entire canonical input.",
            },
        )
    return output
