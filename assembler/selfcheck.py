from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from .guards import banned_files, load_bans, quality_warnings


def check_job(root: Path) -> list[str]:
    errors: list[str] = []
    scenes = json.loads((root / "scenes.json").read_text(encoding="utf-8")).get("scenes", [])
    manifest_path = root / "images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    seen: dict[str, str] = {}
    for scene in scenes:
        sid = str(scene["id"])
        if str(scene.get("source", "")).startswith("card:"):
            continue
        if sid not in manifest:
            errors.append(f"scene {sid}: missing manifest entry")
            continue
        if manifest[sid].get("status") in {"FAILED", "placeholder"}:
            errors.append(f"scene {sid}: manifest status {manifest[sid].get('status')}")
            continue
        path = root / manifest[sid].get("path", "")
        if not path.is_file():
            errors.append(f"scene {sid}: missing file {path}")
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".mp4", ".webm", ".mov", ".mkv"}:
            errors.append(f"scene {sid}: unsupported media extension {path.suffix}")
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        previous = seen.get(digest)
        if previous:
            errors.append(f"scene {sid}: duplicate media with scene {previous}")
        else:
            seen[digest] = sid
    overlays_path = root / "overlays.json"
    if overlays_path.exists():
        overlays = json.loads(overlays_path.read_text(encoding="utf-8"))
        for sid, overlay in overlays.items():
            if sid == "anchor": continue
            text = overlay.get("text", {})
            if str(text.get("pos", "")).startswith("b"): errors.append(f"overlay {sid}: bottom text position is reserved for subtitles")
            if not 0.4 <= float(overlay.get("scale", 1)) <= 2.4: errors.append(f"overlay {sid}: scale out of range")
    # FINAL GATE, deliberately last: the ban list changes while a build is in
    # flight. With several assemblers running in parallel one of them bans a
    # frame another one is already holding, and only a sweep right before the
    # send catches it.
    ban_path = os.environ.get("BANNED_MD5_FILE", str(root / "banned_md5.json"))
    bans = load_bans(ban_path)
    if bans:
        for path, meta in banned_files(root, bans):
            errors.append(f"banned frame in build: {path} ({meta.get('reason', 'no reason recorded')})")

    frames = [p for p in sorted((root / "images").glob("scene_*")) if p.suffix not in {".json", ".png"}]
    for warning in quality_warnings(frames):
        errors.append("quality: " + warning)
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path("build")); args = parser.parse_args()
    errors = check_job(args.root)
    if errors:
        print("\n".join(errors)); raise SystemExit(1)
    print("selfcheck: ok")


if __name__ == "__main__": main()
