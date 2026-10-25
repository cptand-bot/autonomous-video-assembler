from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any


class JobStore:
    """File-backed state for one review job."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "images").mkdir(exist_ok=True)
        (self.root / "overlays").mkdir(exist_ok=True)

    def _read(self, name: str, default: Any) -> Any:
        path = self.root / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, name: str, value: Any) -> None:
        path = self.root / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def scenes(self) -> list[dict]:
        return self._read("scenes.json", {}).get("scenes", [])

    def overlays(self) -> dict:
        return self._read("overlays.json", {"anchor": "top"})

    @staticmethod
    def validate_overlay_patch(body: dict) -> dict:
        allowed_shapes = {"rect", "rounded", "square", "circle"}
        allowed_styles = {"left", "right", "up-center", "up-left", "up-right"}
        allowed_anchors = {"top", "middle", "bottom"}
        allowed_sounds = {"whoosh", "zatvor", "pop", "ding", "mashinka", "pshik", ""}
        patch = dict(body)
        if "shape" in patch and patch["shape"] not in allowed_shapes: patch["shape"] = "rect"
        if "style" in patch and patch["style"] not in allowed_styles: patch["style"] = "left"
        if "anchor" in patch and patch["anchor"] not in allowed_anchors: patch["anchor"] = "top"
        if "sound" in patch and patch["sound"] not in allowed_sounds: patch["sound"] = "pop"
        if "scale" in patch:
            patch["scale"] = min(2.4, max(0.4, round(float(patch["scale"]), 2)))
        if "at" in patch:
            patch["at"] = max(0.0, round(float(patch["at"]), 2))
        if isinstance(patch.get("text"), dict):
            text = dict(patch["text"])
            if text.get("pos", "mc").startswith("b"): text["pos"] = "mc"
            if text.get("color") not in {"white", "yellow", "red", "green", "orange"}: text["color"] = "white"
            if text.get("font") not in {"default", "arial", "times", "oswald", "montserrat", "roboto"}: text["font"] = "default"
            patch["text"] = text
        return patch

    def state(self) -> dict:
        scenes = []
        manifest = self._read("images/manifest.json", {})
        labels = {"press": "ПРЕСС-ФОТО", "openverse": "OPENVERSE", "wikimedia": "WIKIMEDIA", "archive": "АРХИВ", "dvids": "DVIDS", "flickr": "FLICKR", "pexels": "PEXELS", "upload": "ЗАГРУЗКА", "library": "МЕДИАТЕКА"}
        for scene in self.scenes():
            sid = str(scene["id"])
            item = {"id": scene["id"]}
            entry = manifest.get(sid, {})
            image = self.root / entry.get("path", f"images/{int(scene['id']):03d}.jpg")
            if entry.get("status") == "FAILED":
                item["status"] = "failed"
            elif image.exists():
                source = entry.get("source", "press")
                kind = manifest.get(sid, {}).get("kind", "photo")
                item.update({"thumb": entry.get("thumb", f"images/{image.name}") if kind != "video" else entry.get("thumb"), "video": str(image.relative_to(self.root)).replace("\\", "/") if kind == "video" else None, "v": image.stat().st_mtime_ns, "badge": source, "badge_label": labels.get(source, source.upper()), "is_video": kind == "video"})
            else:
                item["status"] = "failed"
            scenes.append(item)
        needs = self._read("needs_upload.json", {})
        overlays = self.overlays()
        for sid, record in overlays.items():
            if sid == "anchor" or not isinstance(record, dict):
                continue
            if record.get("photo") and "pos" not in record:
                style = record.get("style", "left")
                width, height = (500, 333) if record.get("size", "m") == "m" else ((360, 240) if record.get("size") == "s" else (700, 467))
                x = 80 if style in ("left", "up-left") else (1340 if style == "right" else 710)
                y = 90 if overlays.get("anchor", "top") == "top" else (390 if overlays.get("anchor") == "middle" else 700)
                record["pos"] = {"x": x, "y": y, "w": width, "h": height}
        approval = self._read("approval.json", {"approved": False})
        return {"scenes": scenes, "failed": sum(1 for s in scenes if s.get("status") == "failed"),
                "fetch_done": True, "needs": needs, "overlays": overlays, "approval": approval, "stale_code": False}

    def append_log(self, name: str, value: dict) -> None:
        with (self.root / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": time.time(), **value}, ensure_ascii=False) + "\n")

    def mark_need(self, sid: str, reason: str = "") -> None:
        needs = self._read("needs_upload.json", {})
        if reason:
            needs[str(sid)] = reason
        else:
            needs.pop(str(sid), None)
        self._write("needs_upload.json", needs)
        approval = self._read("approval.json", {"approved": False})
        if approval.get("approved"):
            self._write("approval.json", {"approved": False, "invalidated_by": str(sid), "at": time.time()})

    def remove_overlay(self, sid: str) -> None:
        overlays = self.overlays()
        overlays.pop(str(sid), None)
        self._write("overlays.json", overlays)
        path = self.root / "overlays" / f"scene_{int(sid):03d}.jpg"
        if path.exists():
            path.unlink()

    def ban_image(self, sid: str, days: int | None = None) -> str:
        path = next(iter((self.root / "images").glob(f"{int(sid):03d}.*")), None)
        if path is None:
            return ""
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        bans = self._read(".banned_md5.json", {})
        bans[digest] = {"days": days, "created": time.time()}
        self._write(".banned_md5.json", bans)
        path.unlink()
        self.mark_need(sid, "кадр заблокирован")
        return digest

    def candidates(self, sid: str, query: str) -> list[dict]:
        all_items = self._read("search_options.json", {})
        items = all_items.get(str(sid), [])
        if query:
            q = query.casefold()
            items = [item for item in items if q in json.dumps(item, ensure_ascii=False).casefold()]
        return items

    def pick_candidate(self, sid: str, candidate: dict, target: str = "scene") -> Path:
        source = Path(candidate["path"])
        if not source.is_file():
            raise FileNotFoundError(source)
        folder = self.root / ("overlays" if target == "overlay" else "images")
        suffix = ".jpg"
        destination = folder / (f"scene_{int(sid):03d}{suffix}" if target == "overlay" else f"{int(sid):03d}{suffix}")
        shutil.copyfile(source, destination)
        return destination
