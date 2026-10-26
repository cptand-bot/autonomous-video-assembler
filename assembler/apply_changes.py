"""Применить решения человека с дашборда к сборке.

Было: решения умирали на диске у человека. `render.py` не читал `approval.json`
вообще, а джоб `render` в workflow скачивал артефакт ТОГО ЖЕ прогона — то есть
рендерил до того, как человек что-то увидел. Третьего пути не было: либо нет
рендера, либо рендер без просмотра.

Теперь путь есть: человек открывает скачанный артефакт, жмёт кнопки, нажимает
«💾 Скачать правки» и отдаёт `review_changes.json` сюда.

    python -m assembler.apply_changes --root build --changes review_changes.json
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import time
from pathlib import Path


class ChangesError(RuntimeError):
    pass


_DATA_URL = re.compile(r"^data:image/(?P<kind>jpeg|jpg|png|webp);base64,(?P<body>.+)$", re.S)


def _decode_upload(value: str) -> bytes:
    match = _DATA_URL.match(str(value).strip())
    if not match:
        raise ChangesError("upload is not a data URL of an image")
    try:
        return base64.b64decode(match.group("body"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ChangesError(f"upload is not valid base64: {exc}") from exc


def apply_changes(root: Path, changes: dict) -> dict:
    manifest_path = root / "images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    overlay_path = root / "overlays.json"
    overlays = json.loads(overlay_path.read_text(encoding="utf-8")) if overlay_path.exists() else {}
    report = {"replaced": [], "banned": [], "overlays": [], "notes": [], "errors": []}

    for sid, item in (changes.get("scenes") or {}).items():
        sid = str(sid)
        verdict = str(item.get("verdict", ""))
        if item.get("upload"):
            try:
                data = _decode_upload(item["upload"])
            except ChangesError as exc:
                report["errors"].append(f"scene {sid}: {exc}")
            else:
                folder = root / "images"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{int(sid):03d}.jpg"
                path.write_bytes(data)
                import hashlib

                manifest[sid] = {
                    "path": f"images/{int(sid):03d}.jpg",
                    "md5": hashlib.md5(data).hexdigest(),
                    "source": "upload",
                    "target": "scene",
                    "status": "ok",
                }
                report["replaced"].append(sid)
        elif verdict == "ban":
            entry = manifest.get(sid)
            if entry:
                (root / str(entry.get("path", ""))).unlink(missing_ok=True)
                entry["status"] = "FAILED"
                entry["reason"] = item.get("note") or "забраковано человеком"
            report["banned"].append(sid)
        if item.get("note"):
            report["notes"].append({"scene": sid, "note": item["note"]})
        overlay = item.get("overlay")
        if isinstance(overlay, dict) and overlay:
            if overlay.get("cleared"):
                overlays.pop(sid, None)
            else:
                record = overlays.get(sid) if isinstance(overlays.get(sid), dict) else {}
                record = dict(record)
                record.update({k: v for k, v in overlay.items() if k != "cleared"})
                record["approved_by_human"] = True
                overlays[sid] = record
            report["overlays"].append(sid)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overlay_path.write_text(json.dumps(overlays, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    approved = bool(changes.get("approved"))
    blockers = [sid for sid, entry in manifest.items() if entry.get("status") in {"FAILED", "placeholder"}]
    if approved and blockers:
        approved = False
        report["errors"].append(
            "утверждение снято: сцены без кадра " + ", ".join(sorted(blockers, key=lambda x: int(x)))
        )
    (root / "approval.json").write_text(
        json.dumps({"approved": approved, "at": time.time(), "source": "review_changes.json"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report["approved"] = approved
    (root / "changes_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply human review decisions to the build")
    parser.add_argument("--root", type=Path, default=Path("build"))
    parser.add_argument("--changes", type=Path, required=True)
    args = parser.parse_args()
    if not args.changes.is_file():
        raise SystemExit(f"файла правок нет: {args.changes}")
    report = apply_changes(args.root, json.loads(args.changes.read_text(encoding="utf-8")))
    print(json.dumps(report, ensure_ascii=False))
    if report["errors"]:
        # Ошибки не прячем, но и сборку не валим: решения уже применены.
        for line in report["errors"]:
            print("WARNING " + line, flush=True)


if __name__ == "__main__":
    main()
