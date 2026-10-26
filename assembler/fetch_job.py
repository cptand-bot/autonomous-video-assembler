from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .collectors import search_sources_detailed, search_pexels_video
from .media import download_image, download_video, write_image, MediaError
from .dashboard import write_static_review


def fetch_job(root: Path, limit: int = 8, download: bool = False) -> dict:
    payload = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    options: dict[str, list[dict]] = {}
    errors: list[dict] = []
    downloaded = 0
    used_urls: set[str] = set()
    used_md5: set[str] = set()
    scene_results: dict[str, dict] = {}
    manifest = root / "images" / "manifest.json"
    scenes = payload.get("scenes", [])
    total_scenes = len(scenes)
    for position, scene in enumerate(scenes, start=1):
        sid = str(scene["id"])
        query = scene.get("source_query", "").strip()
        if not query or str(scene.get("source", "")).startswith("card:"):
            options[sid] = []
            scene_results[sid] = {"status": "card" if str(scene.get("source", "")).startswith("card:") else "FAILED", "query": query, "candidates": 0, "rejections": []}
            continue
        result = search_sources_detailed(query, limit)
        options[sid] = result["options"]
        scene_results[sid] = {"status": "FAILED", "query": query, "candidates": len(options[sid]), "sources": sorted({str(c.get("src", "unknown")) for c in options[sid]}), "rejections": []}
        errors.extend({"scene": sid, **error} for error in result["errors"])
        if download:
            candidates = list(options[sid])
            for candidate in candidates:
                url = candidate.get("full")
                if not url or candidate.get("kind") == "web":
                    scene_results[sid]["rejections"].append("not_direct_media")
                    continue
                if candidate.get("kind") == "photo" and not re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)", url, re.I):
                    scene_results[sid]["rejections"].append("url_has_no_image_extension")
                    continue
                if url in used_urls:
                    scene_results[sid]["rejections"].append("duplicate_url")
                    continue
                try:
                    if candidate.get("kind") == "video":
                        entry = download_video(url, root, sid, candidate.get("src", "remote"))
                    else:
                        data, *_ = download_image(url, minimum=1600)
                        entry = write_image(root, sid, data, source=candidate.get("src", "remote"))
                    if entry.get("md5") in used_md5:
                        Path(root / entry["path"]).unlink(missing_ok=True)
                        current = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
                        current.pop(str(sid), None)
                        manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        continue
                    used_md5.add(entry.get("md5", ""))
                    used_urls.add(url)
                    downloaded += 1
                    scene_results[sid].update({"status": "ok", "source": entry.get("source"), "path": entry.get("path"), "width_checked": 1600})
                    break
                except Exception as exc:
                    errors.append({"scene": sid, "source": candidate.get("src", "unknown"), "error": str(exc)})
                    scene_results[sid]["rejections"].append(f"{candidate.get('src', 'unknown')}: {type(exc).__name__}: {exc}")
            # Pexels is never an implicit fallback. It is allowed only when the
            # storyboard explicitly opted this scene into video stock.
            if scene.get("source") == "pexels_video" and not any(str(sid) == str(k) for k in (json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {})):
                try:
                    fallback = search_pexels_video(query, limit=3)
                    for candidate in fallback:
                        try:
                            if candidate.get("full") in used_urls:
                                continue
                            download_video(candidate["full"], root, sid, candidate.get("src", "pexels"))
                            used_urls.add(candidate["full"])
                            downloaded += 1
                            break
                        except Exception as exc:
                            errors.append({"scene": sid, "source": "pexels_fallback", "error": str(exc)})
                except Exception as exc:
                    errors.append({"scene": sid, "source": "pexels_fallback", "error": str(exc)})
            if not any(str(sid) == str(k) for k in (json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {})):
                (root / "images").mkdir(parents=True, exist_ok=True)
                current = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
                current[sid] = {"status": "FAILED", "source": "none"}
                manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if scene_results[sid]["status"] != "ok":
                scene_results[sid]["status"] = "FAILED"
        print(f"PROGRESS {position}/{total_scenes} scene={sid} downloaded={downloaded}", flush=True)
    (root / "search_options.json").write_text(json.dumps(options, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    failed = sum(1 for scene in scenes if not str(scene.get("source", "")).startswith("card:") and manifest_data.get(str(scene["id"]), {}).get("status") != "ok")
    report = {"scenes": len(payload.get("scenes", [])), "with_options": sum(bool(v) for v in options.values()), "downloaded": downloaded, "failed": failed, "errors": errors, "scene_results": scene_results}
    (root / "fetch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if download:
        write_static_review(root)
    if download and scenes and failed / max(1, len([s for s in scenes if not str(s.get("source", "")).startswith("card:")])) > 0.25:
        raise MediaError(f"too many failed scenes: {failed}/{len(scenes)}")
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
