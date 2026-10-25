from __future__ import annotations

import argparse
import json
from pathlib import Path


def check_job(root: Path) -> list[str]:
    errors: list[str] = []
    scenes = json.loads((root / "scenes.json").read_text(encoding="utf-8")).get("scenes", [])
    manifest_path = root / "images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for scene in scenes:
        sid = str(scene["id"])
        if str(scene.get("source", "")).startswith("card:"):
            continue
        if sid not in manifest:
            errors.append(f"scene {sid}: missing manifest entry")
            continue
        path = root / manifest[sid].get("path", "")
        if not path.is_file(): errors.append(f"scene {sid}: missing file {path}")
    overlays_path = root / "overlays.json"
    if overlays_path.exists():
        overlays = json.loads(overlays_path.read_text(encoding="utf-8"))
        for sid, overlay in overlays.items():
            if sid == "anchor": continue
            text = overlay.get("text", {})
            if str(text.get("pos", "")).startswith("b"): errors.append(f"overlay {sid}: bottom text position is reserved for subtitles")
            if not 0.4 <= float(overlay.get("scale", 1)) <= 2.4: errors.append(f"overlay {sid}: scale out of range")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path("build")); args = parser.parse_args()
    errors = check_job(args.root)
    if errors:
        print("\n".join(errors)); raise SystemExit(1)
    print("selfcheck: ok")


if __name__ == "__main__": main()
