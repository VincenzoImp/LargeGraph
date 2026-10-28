"""These checks run without scientific dependencies."""

import json
import tempfile
import unittest
from pathlib import Path

from largegraph_viz.runtime import (
    Resources,
    artifact_directory,
    fingerprint,
    identifier,
    literal,
    signature,
    write_json,
)


class RuntimeTests(unittest.TestCase):
    def test_sql_quoting(self):
        self.assertEqual(literal("a'b"), "'a''b'")
        self.assertEqual(identifier('a"b'), '"a""b"')

    def test_resource_validation(self):
        for memory in ("-3GB", "3GB; DROP TABLE x", "0GB"):
            with self.assertRaises(ValueError):
                Resources(memory=memory)
        with self.assertRaises(ValueError):
            Resources(threads=0)

    def test_artifacts_do_not_replace_completed_or_interrupted_work(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "artifact"
            with artifact_directory(destination) as stage:
                write_json(stage / "manifest.json", {"done": True})
                self.assertFalse(destination.exists())
            self.assertEqual(
                json.loads((destination / "manifest.json").read_text()), {"done": True}
            )
            with self.assertRaises(FileExistsError), artifact_directory(destination):
                pass
            failed = Path(temp) / "failed"
            with self.assertRaises(RuntimeError), artifact_directory(failed) as stage:
                (stage / "work").write_text("retained")
                raise RuntimeError("simulated interruption")
            self.assertTrue((Path(temp) / "failed.inprogress" / "work").exists())
            with self.assertRaises(FileExistsError), artifact_directory(failed):
                pass

    def test_fingerprint_and_signature(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input"
            path.write_text("abc")
            self.assertEqual(
                fingerprint(path, True)["sha256"],
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )
        self.assertEqual(signature({"a": 1, "b": 2}), signature({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
