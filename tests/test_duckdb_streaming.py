"""Sorted CSR data must retain query order across DuckDB/Arrow batch boundaries."""

import numpy as np

from largegraph_viz.prepare import prepare_graph
from largegraph_viz.runtime import Resources


def test_sorted_csr_survives_multiple_arrow_batches(tmp_path):
    count, reach = 8192, 7
    source = tmp_path / "ring.csv"
    with source.open("w") as stream:
        stream.write("source,target\n")
        for node in range(count):
            for offset in range(1, reach + 1):
                stream.write(f"n{node:04d},n{(node + offset) % count:04d}\n")
    prepared = prepare_graph(
        source, tmp_path / "work", Resources(memory="128MB", threads=2, batch_rows=4096)
    )
    # Independently known ring neighborhoods; compact IDs match the fixed-width IDs.
    expected = np.array(
        [
            neighbor
            for node in range(count)
            for neighbor in sorted(
                {(node + delta) % count for delta in range(-reach, reach + 1) if delta}
            )
        ],
        dtype="<u4",
    )
    actual = np.fromfile(prepared / "neighbors.u32", dtype="<u4")
    assert np.all(np.load(prepared / "degrees.npy") == 2 * reach)
    np.testing.assert_array_equal(actual, expected)
