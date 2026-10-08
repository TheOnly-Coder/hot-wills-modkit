"""`hw` command line: one entry point for every tool, so skills can say `hw <group> <cmd>`."""
from __future__ import annotations

import argparse
import importlib
import sys

from hw import __doc__ as DOC, __version__

GROUPS = ["scan", "bridge", "composite", "capture", "asset", "backup", "publish", "kb"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hw", description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"hot-wills-modkit {__version__}")
    sub = ap.add_subparsers(dest="group", metavar="<group>")
    for g in GROUPS:
        importlib.import_module(f"hw.{g}").register(sub)
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        # a group without a command: show that group's help
        if args.group:
            ap.parse_args([args.group, "--help"])
        ap.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
