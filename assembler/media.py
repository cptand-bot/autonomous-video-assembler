from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image


class MediaError(ValueError):
    pass


def add_manifest_metadata(root: Path, sid: str, metadata: dict) -> None:
    path = root / "images" / "manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if str(sid) not in manifest:
        return
    for key in ("license", "creator", "title", "full"):
        if metadata.get(key):
            manifest[str(sid)]["url" if key == "full" else key] = metadata[key]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_image(data: bytes, minimum: int = 200) -> tuple[bytes, int, int, str]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width < minimum or height < minimum:
                raise MediaError(f"image is too small: {width}x{height}")
            converted = image.convert("RGB")
            output = io.BytesIO(); converted.save(output, format="JPEG", quality=92)
            return output.getvalue(), width, height, "jpeg"
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError(f"unsupported or invalid image: {exc}") from exc


def download_image(url: str, timeout: int = 30) -> tuple[bytes, int, int, str]:
    request = Request(url, headers={"User-Agent": "autonomous-video-assembler/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return normalize_image(response.read())


def write_image(root: Path, sid: str, data: bytes, target: str = "scene", source: str = "") -> dict:
    folder = root / ("overlays" if target == "overlay" else "images")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (f"scene_{int(sid):03d}.jpg" if target == "overlay" else f"{int(sid):03d}.jpg")
    path.write_bytes(data)
    digest = hashlib.md5(data).hexdigest()
    if target == "overlay":
        return {"path": str(path.relative_to(root)).replace("\\", "/"), "md5": digest, "source": source, "target": target, "status": "ok"}
    manifest_path = root / "images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest[str(sid)] = {"path": str(path.relative_to(root)).replace("\\", "/"), "md5": digest, "source": source, "target": target, "status": "ok"}
    manifest_path.parent.mkdir(exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest[str(sid)]


def download_video(url: str, root: Path, sid: str, source: str = "remote") -> dict:
    request = Request(url, headers={"User-Agent": "autonomous-video-assembler/0.1"})
    folder = root / "videos"; folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{int(sid):03d}.mp4"
    with urlopen(request, timeout=60) as response:
        data = response.read()
    path.write_bytes(data)
    digest = hashlib.md5(data).hexdigest()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(path)], capture_output=True, text=True)
    if probe.returncode:
        path.unlink(missing_ok=True); raise MediaError("invalid video: " + probe.stderr[-500:])
    info = json.loads(probe.stdout or "{}")
    duration = float(info.get("format", {}).get("duration", 0))
    if duration <= 0:
        path.unlink(missing_ok=True); raise MediaError("video has no duration")
    manifest_path = root / "images" / "manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest[str(sid)] = {"path": str(path.relative_to(root)).replace("\\", "/"), "md5": digest, "source": source, "kind": "video", "duration": duration, "status": "ok"}
    manifest_path.parent.mkdir(exist_ok=True); manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest[str(sid)]
