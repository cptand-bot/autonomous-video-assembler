from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .collectors import search_sources_detailed, search_pexels_video
from .media import download_image, download_video, write_image, MediaError
from .dashboard import write_static_review, render_review
from .overlays import write_overlay_plan


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
    overlay_plan, overlay_stats = write_overlay_plan(root, scenes, payload.get("channel", ""))
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
            for minimum, warning in ((1600, None), (900, "below_threshold")):
                if scene_results[sid]["status"] == "ok":
                    break
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
                            data, width, height, _ = download_image(url, minimum=minimum)
                            entry = write_image(root, sid, data, source=candidate.get("src", "remote"))
                            if warning:
                                entry["warning"] = warning
                                entry["width"] = width
                                entry["height"] = height
                                current = json.loads(manifest.read_text(encoding="utf-8"))
                                current[str(sid)].update({"warning": warning, "width": width, "height": height})
                                manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        if entry.get("md5") in used_md5:
                            Path(root / entry["path"]).unlink(missing_ok=True)
                            current = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
                            current.pop(str(sid), None)
                            manifest.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                            continue
                        used_md5.add(entry.get("md5", ""))
                        used_urls.add(url)
                        downloaded += 1
                        scene_results[sid].update({"status": "ok", "source": entry.get("source"), "path": entry.get("path"), "url": url, "width_checked": minimum, "warning": warning})
                        break
                    except Exception as exc:
                        errors.append({"scene": sid, "source": candidate.get("src", "unknown"), "error": str(exc), "minimum": minimum})
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
    overlay_path = root / "overlays.json"
    overlays = json.loads(overlay_path.read_text(encoding="utf-8")) if overlay_path.exists() else {}
    scene_manifest = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    scene_md5 = {str(k): str(v.get("md5", "")) for k, v in scene_manifest.items()}
    used_overlay_md5: set[str] = set()
    for sid, record in overlays.items():
        if sid == "anchor" or not isinstance(record, dict) or not record.get("planned"):
            continue
        photo = None
        rejected_duplicates = []
        for item in options.get(sid, []):
            if item.get("kind") != "photo" or not item.get("full"):
                continue
            if item.get("full") == scene_results.get(sid, {}).get("url"):
                rejected_duplicates.append("same_source_url")
                continue
            overlay_query = str(record.get("query", "")).strip().lower()
            scene_query = str(next((s.get("source_query", "") for s in scenes if str(s.get("id")) == str(sid)), "")).strip().lower()
            if overlay_query and overlay_query in scene_query:
                rejected_duplicates.append("same_subject_as_scene")
                continue
            photo = item
            break
        if photo:
            record["photo_candidate"] = {"full": photo["full"], "src": photo.get("src", "remote"), "selected": False, "role": "additional_context"}
            for variant in record.get("variants", []):
                if variant.get("kind") == "photo":
                    variant.update({"status": "ready", "src": photo.get("src", "remote"), "full": photo["full"]})
            try:
                data, width, height, _ = download_image(photo["full"], minimum=800)
                entry = write_image(root, sid, data, target="overlay", source=photo.get("src", "remote"))
                # Дубль проверяется по ВСЕМ кадрам ролика и по уже взятым
                # всплывашкам, а не только по базе своей сцены: кадр, который
                # зритель видит полноэкранным на ЛЮБОЙ сцене, не может всплывать
                # в рамке, и одна всплывашка не повторяется дважды.
                digest = entry.get("md5", "")
                clash = [s for s, m in scene_md5.items() if m and m == digest]
                if digest and (clash or digest in used_overlay_md5):
                    Path(root / entry["path"]).unlink(missing_ok=True)
                    record["photo_candidate"]["status"] = "rejected_duplicate_of_scene"
                    record["photo_candidate"]["error"] = (
                        f"overlay image is identical to the frame of scene(s) {', '.join(clash)}"
                        if clash else "overlay image repeats another overlay"
                    )
                    record["photo"] = ""
                    continue
                if digest:
                    used_overlay_md5.add(digest)
                record["photo"] = entry["path"]
                record["photo_width"] = width
                record["photo_height"] = height
                record["photo_candidate"]["path"] = entry["path"]
            except Exception as exc:
                record["photo_candidate"]["status"] = "download_failed"
                record["photo_candidate"]["error"] = str(exc)
    overlay_path.write_text(json.dumps(overlays, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["overlays"] = overlays
    # Кадры вшиваются в страницу ОТНОСИТЕЛЬНЫМИ путями (images/001.jpg,
    # videos/007.mp4), чтобы скачанный артефакт показывал их без сервера.
    frames = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    assets: dict[str, dict] = {}
    for sid, item in frames.items():
        path = str(item.get("path", ""))
        asset: dict[str, object] = {"status": "failed" if item.get("status") in {"FAILED", "placeholder"} else "ok"}
        if path.lower().endswith((".mp4", ".webm", ".mov", ".mkv")):
            asset["video"] = path
        elif path:
            asset["image"] = path
        assets[str(sid)] = asset
    payload["assets"] = assets
    (root / "review.html").write_text(render_review(payload), encoding="utf-8")
    manifest_data = frames
    failed = sum(1 for scene in scenes if not str(scene.get("source", "")).startswith("card:") and manifest_data.get(str(scene["id"]), {}).get("status") != "ok")
    report = {"scenes": len(payload.get("scenes", [])), "with_options": sum(bool(v) for v in options.values()), "downloaded": downloaded, "failed": failed, "errors": errors, "scene_results": scene_results, "overlays": overlay_stats}
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
    print(json.dumps(report, ensure_ascii=False))
    # Падаем только если кадра нет у сцены, которая его ЖДАЛА. Сцена с
    # пометкой «нужен ручной запрос» в фетч не идёт и провалом не является:
    # иначе честная пометка валит весь прогон и человек снова без дашборда.
    if args.download and report.get("failed"):
        raise SystemExit(2)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
