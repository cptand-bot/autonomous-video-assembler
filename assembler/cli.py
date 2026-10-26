from __future__ import annotations

import argparse
from pathlib import Path

from .dashboard import write_outputs
from .srt import parse_srt
from .storyboard import build_scenes
from .validate import assert_valid


def main() -> None:
    parser = argparse.ArgumentParser(description="Build storyboard dashboard from SRT")
    parser.add_argument("srt", type=Path)
    parser.add_argument("--channel", default="ПЛАНЕТА")
    parser.add_argument("--output", type=Path, default=Path("build"))
    parser.add_argument("--topic", default="")
    args = parser.parse_args()
    payload = build_scenes(parse_srt(args.srt.read_text(encoding="utf-8-sig")), args.channel, args.topic)
    assert_valid(payload)
    write_outputs(payload, args.output)
    print(f"Created {len(payload['scenes'])} scenes in {args.output}")


if __name__ == "__main__":
    main()
