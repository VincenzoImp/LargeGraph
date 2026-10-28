"""Single command-line interface for the graph workbench."""

from __future__ import annotations

import argparse
import logging
import sys

from .runtime import configure_threads


def build_parser():
    from . import __version__
    from .workbench import add_commands

    parser = argparse.ArgumentParser(description="Disk-backed large graph visualization")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    add_commands(parser.add_subparsers(dest="command", required=True))
    return parser


def main(argv=None):
    from .workbench import dispatch

    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(raw_args)
    configure_threads(getattr(args, "threads", 2))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    try:
        dispatch(args, raw_args)
    except KeyboardInterrupt:
        parser.exit(130, "Interrupted. Repeat the same analyze command to resume an analysis.\n")
    except Exception as exc:
        if args.verbose:
            logging.getLogger(__name__).exception("Command failed")
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
