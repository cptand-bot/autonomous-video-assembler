from __future__ import annotations

import re
from pathlib import Path


def _quote(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")]
    for sentence in sentences:
        if 60 <= len(sentence) <= 140:
            return sentence
    clean = " ".join((text or "").split())
    if len(clean) <= 140:
        return clean
    return clean[:137].rsplit(" ", 1)[0] + "…"


def plan_overlays(scenes: list[dict], existing: dict | None = None) -> dict:
    """Create review-first overlay proposals without changing scene media."""
    result = dict(existing or {})
    result.setdefault("anchor", "top")
    eligible = [s for s in scenes if not str(s.get("source", "")).startswith("card:")]
    target = max(1, round(len(eligible) / 15))
    chosen: list[dict] = []
    for scene in eligible:
        if len(chosen) >= target:
            break
        if not chosen or int(scene["id"]) - int(chosen[-1]["id"]) >= 9:
            chosen.append(scene)
    for index, scene in enumerate(chosen):
        sid = str(scene["id"])
        old = result.get(sid, {})
        if old.get("approved"):
            continue
        side = "left" if index % 2 == 0 else "right"
        result[sid] = {
            **old,
            "planned": True,
            "approved": False,
            "at": round(min(0.7, max(0.25, float(scene.get("duration_sec", 10)) * 0.04)), 2),
            "shape": old.get("shape", "rounded"),
            "style": old.get("style", side),
            "size": old.get("size", "m"),
            "scale": float(old.get("scale", 1.0)),
            "sound": old.get("sound", "pop"),
            "anchor": old.get("anchor", "top"),
            "text": {
                "words": _quote(str(scene.get("text", ""))),
                "color": "white",
                "font": "default",
                "pos": "tl" if side == "left" else "tr",
                "at": round(min(0.7, max(0.25, float(scene.get("duration_sec", 10)) * 0.04)), 2),
                "scale": 1.0,
                "sound": old.get("sound", "pop"),
            },
            "variants": [
                {"kind": "text", "words": _quote(str(scene.get("text", ""))), "selected": True},
                {"kind": "photo", "status": "optional_candidate", "selected": False},
            ],
        }
    return result


def write_overlay_plan(root: Path, scenes: list[dict]) -> dict:
    import json
    path = root / "overlays.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    planned = plan_overlays(scenes, existing)
    path.write_text(json.dumps(planned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return planned
