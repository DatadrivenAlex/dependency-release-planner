"""JSON-in / JSON-out command line interface."""

import argparse
import json
import sys
from pathlib import Path

from .core import GraphError, plan


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan affected-service rebuild/test batches")
    parser.add_argument("graph", type=Path)
    parser.add_argument("--changed", nargs="*", default=[])
    args = parser.parse_args(argv)
    try:
        result = plan(json.loads(args.graph.read_text()), args.changed)
    except (OSError, UnicodeError, json.JSONDecodeError, GraphError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
