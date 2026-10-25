from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collectors import search_sources_detailed
from .media import download_image, download_video, write_image, MediaError


def fetch_job(root: Path, limit: int = 8, download: bool = False) -> dict:
    payload = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    options: dict[str, list[dict]] = {}
    errors: list[dict] = []
    downloaded = 0
    manifest = root / "images" / "manifest.json"
    scenes = payload.get("scenes", [])
    total_scenes = len(scenes)
    for position, scene in enumerate(scenes, start=1):
        sid = str(scene["id"])
        query = scene.get("source_query", "").strip()
        if not query or str(scene.get("source", "")).startswith("card:"):
            options[sid] = []
            continue
        result = search_sources_detailed(query, limit)
        options[sid] = result["options"]
        errors.extend({"scene": sid, **error} for error in result["errors"])
        if download:
            for candidate in options[sid]:
                url = candidate.get("full")
                if not url or candidate.get("src") == "web_search":
                    continue
                try:
                    if candidate.get("kind") == "video":
                        download_video(url, root, sid, candidate.get("src", "remote"))
                    else:
                        data, *_ = download_image(url)
                        write_image(root, sid, data, source=candidate.get("src", "remote"))
                    downloaded += 1
                    break
                except Exception as exc:
                    errors.append({"scene": sid, "source": candidate.get("src", "unknown"), "error": str(exc)})
            if not any(str(sid) == str(k) for k in (json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {})):
                (root / "images").mkdir(parents=True, exist_ok=True)
                current = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
                current[sid] = {"status": "FAILED", "source": "none"}
                manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"PROGRESS {position}/{total_scenes} scene={sid} downloaded={downloaded}", flush=True)
    (root / "search_options.json").write_text(json.dumps(options, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {"scenes": len(payload.get("scenes", [])), "with_options": sum(bool(v) for v in options.values()), "downloaded": downloaded, "errors": errors}
    (root / "fetch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch media candidates for a storyboard")
    parser.add_argument("--root", type=Path, default=Path("build"))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    report = fetch_job(args.root, args.limit, args.download)
    if args.download and report["downloaded"] < report["scenes"]:
        print(json.dumps(report, ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
