#!/usr/bin/env python3
import sys

import _bootstrap  # noqa: F401

from largegraph_viz.cli import main

if __name__ == "__main__":
    main(["matrix", *sys.argv[1:]])
