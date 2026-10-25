from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fetch_job import fetch_job
from .render import render_video
from .selfcheck import check_job


def run_pipeline(root: Path, output: Path, approve: bool = False, audio: Path | None = None, captions: bool = False) -> dict:
    fetch = fetch_job(root)
    result = {"status": "review_required", "fetch": fetch, "approved": approve}
    (root / "pipeline_state.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not approve:
        return result
    errors = check_job(root)
    if errors:
        result["status"] = "blocked"
        result["errors"] = errors
        (root / "pipeline_state.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    rendered = render_video(root, output, audio, captions)
    result.update(rendered); result["status"] = "rendered"
    (root / "pipeline_state.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fetch/review/render pipeline")
    parser.add_argument("--root", type=Path, default=Path("build")); parser.add_argument("--output", type=Path, default=Path("build/output.mp4")); parser.add_argument("--audio", type=Path); parser.add_argument("--captions", action="store_true"); parser.add_argument("--approve", action="store_true")
    args = parser.parse_args(); audio = args.audio if args.audio and args.audio.is_file() else None
    result = run_pipeline(args.root, args.output, args.approve, audio, args.captions)
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") == "blocked":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
