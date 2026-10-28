"""Run shared production numerical rules with only NumPy and unittest."""

import unittest

import numpy as np

from largegraph_viz.numerics import (
    adjusted_rand,
    block_probabilities,
    matrix_arrays,
    move_block,
    raster_edges,
    raster_points,
)


class NumericalTests(unittest.TestCase):
    def test_local_moves_against_exact_modularity(self):
        # Test many graphs, degree skews and resolutions. Use independent dense Q.
        rng = np.random.default_rng(39)
        for n in [2, 7, 20, 40]:
            for gamma in [0.1, 1.0, 3.0]:
                for _ in range(5):
                    upper = np.triu(rng.random((n, n)) < 0.15, 1)
                    adjacency = upper + upper.T
                    degree = adjacency.sum(axis=1).astype(np.uint64)
                    total = float(degree.sum())
                    offsets = np.r_[0, np.cumsum(degree)].astype(np.uint64)
                    neighbors = np.concatenate([np.flatnonzero(row) for row in adjacency]).astype(
                        np.uint32
                    )
                    labels = np.arange(n, dtype=np.uint32)
                    volumes = degree.copy()
                    scores = np.zeros(n)
                    marks = np.zeros(n, dtype=np.uint32)
                    touched = np.zeros(max(1, int(degree.max())), dtype=np.uint32)

                    def quality(
                        total=total, degree=degree, adjacency=adjacency, gamma=gamma, labels=labels
                    ):
                        if not total:
                            return 0.0
                        null = np.outer(degree.astype(float), degree.astype(float)) / total
                        return float(
                            (
                                (adjacency - gamma * null) * (labels[:, None] == labels[None, :])
                            ).sum()
                            / total
                        )

                    before = quality()
                    for _pass in range(4):
                        marks.fill(0)
                        move_block(
                            0,
                            n,
                            offsets,
                            neighbors,
                            labels,
                            degree,
                            volumes,
                            scores,
                            marks,
                            touched,
                            total,
                            gamma,
                        )
                        after = quality()
                        self.assertGreaterEqual(after + 1e-12, before)
                        independently_counted = np.zeros(n, dtype=np.uint64)
                        np.add.at(independently_counted, labels, degree)
                        np.testing.assert_array_equal(volumes, independently_counted)
                        before = after

    def test_batched_moves_equal_whole_pass(self):
        adjacency = np.array([[0, 1, 1, 0], [1, 0, 1, 0], [1, 1, 0, 1], [0, 0, 1, 0]])
        degrees = adjacency.sum(axis=1).astype(np.uint64)
        offsets = np.r_[0, np.cumsum(degrees)].astype(np.uint64)
        data = np.concatenate([np.flatnonzero(row) for row in adjacency]).astype(np.uint32)

        def run(split):
            labels = np.arange(4, dtype=np.uint32)
            volumes, scores = degrees.copy(), np.zeros(4)
            marks, touched = np.zeros(4, dtype=np.uint32), np.zeros(4, dtype=np.uint32)
            for start, end in split:
                lo, hi = int(offsets[start]), int(offsets[end])
                move_block(
                    start,
                    end,
                    offsets[start : end + 1] - lo,
                    data[lo:hi],
                    labels,
                    degrees,
                    volumes,
                    scores,
                    marks,
                    touched,
                    float(degrees.sum()),
                    1.0,
                )
            return labels

        np.testing.assert_array_equal(run([(0, 4)]), run([(0, 1), (1, 3), (3, 4)]))

    def test_block_models_are_probabilities(self):
        np.testing.assert_array_equal(
            block_probabilities(np.array([10]), 1.0, "communities"), [[1.0]]
        )
        for scenario in ["communities", "weak", "bridges", "core-periphery", "null"]:
            probabilities = block_probabilities(np.array([10, 20, 5, 40]), 0.12, scenario)
            self.assertAlmostEqual(float(probabilities.sum()), 1.0)
            self.assertTrue(np.all(probabilities >= 0))
            np.testing.assert_allclose(probabilities, probabilities.T)
        null = block_probabilities(np.array([10, 20]), 0.12, "null")
        np.testing.assert_allclose(null, np.outer([1 / 3, 2 / 3], [1 / 3, 2 / 3]))

    def test_matrix_counts_and_density(self):
        reduced = {
            "weights": np.array([[3, 4], [0, 1]], dtype=np.uint64),
            "sizes": np.array([3, 2]),
            "volumes": np.array([10, 6]),
        }
        adjacency, expected, _, density = matrix_arrays(reduced)
        np.testing.assert_array_equal(adjacency.sum(axis=1), reduced["volumes"])
        self.assertEqual(int(adjacency.sum()), 16)
        np.testing.assert_allclose(expected, np.outer([10, 6], [10, 6]) / 16)
        self.assertEqual(density[0, 0], 1.0)
        self.assertEqual(density[0, 1], 4 / 6)

    def test_raster_mass_and_pixel_line_counts(self):
        xy = np.array([[0.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
        image = raster_points(xy, np.array([3, 8, 9], dtype=np.uint64), 64, [0, 1, 0, 1])
        self.assertEqual(int(image.sum()), 20)
        self.assertEqual(int(image[0, 0]), 12)
        lines = raster_edges(xy, [0], [1], [7], 64, [0, 1, 0, 1])
        self.assertEqual(int(lines.sum()), 64 * 7)

    def test_ari_permutations(self):
        self.assertEqual(adjusted_rand([1, 1, 2, 2], [8, 8, 3, 3]), 1.0)
        self.assertAlmostEqual(adjusted_rand([1, 1, 2, 2], [0, 1, 0, 1]), -0.5)


if __name__ == "__main__":
    unittest.main()
