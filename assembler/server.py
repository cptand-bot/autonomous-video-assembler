from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .storage import JobStore
from .collectors import search_sources_detailed
from .media import MediaError, download_image, download_video, normalize_image, write_image


class ReviewHandler(BaseHTTPRequestHandler):
    store: JobStore

    def _json(self, status: int, data: dict) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "autonomous-video-assembler-review", "root": str(self.store.root)})
            return
        if parsed.path == "/state":
            self._json(200, self.store.state())
            return
        if parsed.path in ("/review.html", "/"):
            page = (self.store.root / "review.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(page)
            return
        if parsed.path.startswith("/images/") or parsed.path.startswith("/overlays/") or parsed.path.startswith("/videos/"):
            file_path = self.store.root / parsed.path.lstrip("/")
            if file_path.is_file():
                content_type = "video/mp4" if file_path.suffix.lower() == ".mp4" else ("video/webm" if file_path.suffix.lower() == ".webm" else "image/jpeg")
                size = file_path.stat().st_size; range_header = self.headers.get("Range")
                if range_header and range_header.startswith("bytes="):
                    start_text, _, end_text = range_header[6:].partition("-"); start = int(start_text or 0); end = int(end_text) if end_text else size - 1; end = min(end, size - 1)
                    if start <= end:
                        data = file_path.read_bytes()[start:end + 1]; self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}"); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
                self.send_response(200); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(size)); self.end_headers(); self.wfile.write(file_path.read_bytes()); return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        sid = query.get("id", [""])[0]
        if parsed.path == "/search_opts" and sid:
            body = self._body(); query = body.get("q", "")
            options = self.store.candidates(sid, query)
            if not options and query:
                result = search_sources_detailed(query)
                self._json(200, result); return
            self._json(200, {"options": options, "errors": []}); return
        if parsed.path == "/pick_opt" and sid:
            body = self._body()
            try:
                target = body.get("target", "scene")
                if body.get("kind") == "web":
                    self._json(422, {"ok": False, "error": "web_search result is a page reference; choose or upload a verified media file"}); return
                if body.get("kind") == "video" and body.get("full", "").startswith(("http://", "https://")):
                    info = download_video(body["full"], self.store.root, sid, body.get("src", "remote"))
                    path = self.store.root / info["path"]
                elif body.get("full", "").startswith(("http://", "https://")):
                    data, width, height, _ = download_image(body["full"])
                    info = write_image(self.store.root, sid, data, target, body.get("src", "remote"))
                    path = self.store.root / info["path"]
                else:
                    path = self.store.pick_candidate(sid, body, target)
                if target == "overlay":
                    overlays = self.store.overlays()
                    record = overlays.setdefault(str(sid), {})
                    record["photo"] = str(path.relative_to(self.store.root)).replace("\\", "/")
                    self.store._write("overlays.json", overlays)
            except (KeyError, FileNotFoundError, MediaError, OSError) as exc:
                self._json(400, {"ok": False, "error": str(exc)}); return
            self.store.mark_need(sid)
            self._json(200, {"ok": True, "path": str(path.relative_to(self.store.root)).replace("\\", "/")}); return
        if parsed.path == "/upload" and sid:
            filename = self.headers.get("X-Filename", f"{int(sid):03d}.jpg").replace("/", "_").replace("\\", "_")
            length = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(length)
            try:
                data, width, height, _ = normalize_image(raw)
                info = write_image(self.store.root, sid, data, "scene", "upload")
            except MediaError as exc:
                self._json(400, {"ok": False, "error": str(exc)}); return
            self.store.mark_need(sid); self._json(200, {"ok": True, "filename": filename, "width": width, "height": height, "manifest": info}); return
        if parsed.path == "/overlay_photo" and sid:
            filename = self.headers.get("X-Filename", "overlay.jpg").replace("/", "_").replace("\\", "_")
            length = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(length)
            try:
                data, width, height, _ = normalize_image(raw)
                info = write_image(self.store.root, sid, data, "overlay", "overlay_upload")
                overlays = self.store.overlays(); record = overlays.setdefault(str(sid), {}); record["photo"] = info["path"]; self.store._write("overlays.json", overlays)
                self.store.append_log("layout_journal.jsonl", {"scene": sid, "patch": {"photo": info["path"]}})
            except MediaError as exc:
                self._json(400, {"ok": False, "error": str(exc)}); return
            self._json(200, {"ok": True, "filename": filename, "width": width, "height": height, "manifest": info}); return
        if parsed.path == "/mirror" and sid:
            source = self.store.root / "images" / f"{int(sid):03d}.jpg"
            if source.is_file():
                source.write_bytes(source.read_bytes())
            self._json(200, {"ok": True}); return
        if parsed.path == "/zoomimg" and sid:
            self._json(200, {"ok": True, "factor": query.get("f", ["1"])[0]}); return
        if parsed.path == "/overlay" and sid:
            body = self._body(); overlays = self.store.overlays(); record = overlays.get(sid, {})
            if query.get("clear") == ["1"]:
                self.store.remove_overlay(sid)
            else:
                body = self.store.validate_overlay_patch(body)
                record.update({k: body[k] for k in ("sound", "at", "shape", "scale", "style", "anchor", "approved") if k in body})
                overlays[sid] = record; self.store._write("overlays.json", overlays)
                self.store.append_log("layout_journal.jsonl", {"scene": sid, "patch": body})
            self._json(200, {"ok": True}); return
        if parsed.path == "/approve" and not sid:
            body = self._body(); approved = bool(body.get("approved", False)); self.store._write("approval.json", {"approved": approved, "at": __import__("time").time()}); self._json(200, {"ok": True, "approved": approved}); return
        if parsed.path in ("/overlay_text", "/ticker") and sid:
            body = self._body(); overlays = self.store.overlays(); record = overlays.setdefault(sid, {})
            key = "text" if parsed.path == "/overlay_text" else "ticker"
            if body.get("clear"):
                record.pop(key, None)
            else:
                record[key] = self.store.validate_overlay_patch(body)
            self.store._write("overlays.json", overlays); self._json(200, {"ok": True}); return
        if parsed.path == "/reject" and sid:
            body = self._body(); self.store.append_log("rejections.jsonl", {"scene": sid, **body}); self._json(200, {"ok": True}); return
        if parsed.path == "/ban_asset" and sid:
            body = self._body(); digest = self.store.ban_image(sid, body.get("days")); self._json(200, {"ok": True, "md5": digest}); return
        if parsed.path == "/keepimg" and sid:
            self.store.mark_need(sid); self._json(200, {"ok": True}); return
        self.send_error(404)


def serve(root: Path, host: str = "127.0.0.1", port: int = 8790) -> None:
    ReviewHandler.store = JobStore(root)
    server = ThreadingHTTPServer((host, port), ReviewHandler)
    print(f"Review server: http://{host}:{port}/review.html")
    server.serve_forever()
