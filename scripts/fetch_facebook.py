"""Fetch the SNAP Facebook combined edge list; record source and checksum.

The original data retains its upstream terms. It is never committed to this
repository. Citation: J. McAuley and J. Leskovec, NIPS 2012.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import urllib.request
from pathlib import Path

URL = "https://snap.stanford.edu/data/facebook_combined.txt.gz"
SHA256 = "125e84db872eeba443d270c70315c256b0af43a502fcfe51f50621166ad035d7"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/facebook"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / "edges.csv"
    if destination.exists():
        raise FileExistsError(f"Refusing to replace {destination}")
    raw = urllib.request.urlopen(URL, timeout=30).read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SHA256:
        raise ValueError(f"Upstream content changed: SHA-256 {digest}; review the source")
    with (
        gzip.open(io.BytesIO(raw), "rt", encoding="utf-8") as source,
        destination.open("w", encoding="utf-8", newline="") as target,
    ):
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(["source", "target"])
        for line in source:
            if line.strip() and not line.startswith("#"):
                writer.writerow(line.split())
    (args.output / "source.json").write_text(
        json.dumps(
            {
                "url": URL,
                "sha256": digest,
                "dataset_page": "https://snap.stanford.edu/data/ego-Facebook.html",
                "citation": "J. McAuley and J. Leskovec. Learning to Discover Social Circles in Ego Networks. NIPS 2012.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
