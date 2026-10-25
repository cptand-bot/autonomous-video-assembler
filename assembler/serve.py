from __future__ import annotations

import argparse
from pathlib import Path

from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run review backend")
    parser.add_argument("--root", type=Path, default=Path("build"))
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    serve(args.root, port=args.port)


if __name__ == "__main__":
    main()
