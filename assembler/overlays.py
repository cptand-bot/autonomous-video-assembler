from __future__ import annotations

import re
from pathlib import Path

_VISUAL_MARKERS = re.compile(r"\b(карта|маршрут|границ|дальность|скорость|процент|километр|миллион|дата|направлени)\w*\b", re.I)
_PROPER_NAME = re.compile(r"\b[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]{2,})?\b")


def _quote(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")]
    for sentence in sentences:
        if 60 <= len(sentence) <= 140:
            return sentence
    clean = " ".join((text or "").split())
    if len(clean) <= 140:
        return clean
    return clean[:137].rsplit(" ", 1)[0] + "…"


def plan_overlays(scenes: list[dict], existing: dict | None = None, channel: str = "") -> tuple[dict, dict]:
    """Select only semantically justified overlay candidates.

    This is deliberately a proposal step: it never tries to reach a target
    density and records why each candidate was rejected.
    """
    result = dict(existing or {})
    result.setdefault("anchor", "top")
    stats = {"proposed": 0, "accepted": 0, "rejected": 0, "rejected_by_subtype": {}}
    chosen: list[dict] = []
    for scene in scenes:
        if str(scene.get("source", "")).startswith("card:"):
            continue
        stats["proposed"] += 1
        text = str(scene.get("text", ""))
        query = str(scene.get("source_query", ""))
        if not query or len(text.strip()) < 60:
            reason = "no_concrete_scene_subject"
        elif _VISUAL_MARKERS.search(text) or _PROPER_NAME.search(text):
            reason = ""
        else:
            reason = "no_answer_to_what_it_illustrates"
        if reason:
            stats["rejected"] += 1
            stats["rejected_by_subtype"][reason] = stats["rejected_by_subtype"].get(reason, 0) + 1
            continue
        if chosen and int(scene["id"]) - int(chosen[-1]["id"]) < 9:
            stats["rejected"] += 1
            stats["rejected_by_subtype"]["same_layer_or_too_close"] = stats["rejected_by_subtype"].get("same_layer_or_too_close", 0) + 1
            continue
        chosen.append(scene)
    for index, scene in enumerate(chosen):
        stats["accepted"] += 1
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
                {"kind": "text", "words": _quote(str(scene.get("text", ""))), "selected": channel != "ПЛАНЕТА"},
                {"kind": "photo", "status": "optional_candidate", "selected": False},
            ],
        }
        if channel == "ПЛАНЕТА":
            result[sid]["text"] = {"words": "", "disabled": True, "reason": "channel_disallows_text_overlays"}
    selected_ids = {str(scene["id"]) for scene in chosen}
    for sid in list(result):
        if sid != "anchor" and isinstance(result[sid], dict) and result[sid].get("planned") and sid not in selected_ids and not result[sid].get("approved"):
            del result[sid]
    return result, stats


def write_overlay_plan(root: Path, scenes: list[dict], channel: str = "") -> tuple[dict, dict]:
    import json
    path = root / "overlays.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    planned, stats = plan_overlays(scenes, existing, channel)
    path.write_text(json.dumps(planned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "overlay_report.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return planned, stats
