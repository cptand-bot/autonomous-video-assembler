from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collectors import search_sources_detailed


def fetch_job(root: Path, limit: int = 8) -> dict:
    payload = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    options: dict[str, list[dict]] = {}
    errors: list[dict] = []
    for scene in payload.get("scenes", []):
        sid = str(scene["id"])
        query = scene.get("source_query", "").strip()
        if not query or str(scene.get("source", "")).startswith("card:"):
            options[sid] = []
            continue
        result = search_sources_detailed(query, limit)
        options[sid] = result["options"]
        errors.extend({"scene": sid, **error} for error in result["errors"])
    (root / "search_options.json").write_text(json.dumps(options, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"scenes": len(payload.get("scenes", [])), "with_options": sum(bool(v) for v in options.values()), "errors": errors}
    (root / "fetch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch media candidates for a storyboard")
    parser.add_argument("--root", type=Path, default=Path("build"))
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    report = fetch_job(args.root, args.limit)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
