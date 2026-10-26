from __future__ import annotations

import re
from pathlib import Path

from .storyboard import _stem, scene_subjects

_VISUAL_MARKERS = re.compile(r"\b(карта|маршрут|границ|дальность|скорость|процент|километр|миллион|дата|направлени)\w*\b", re.I)
_PROPER_NAME = re.compile(r"\b[А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ][а-яё]{2,})?\b")


_NUMBER = re.compile(
    r"\b(\d[\d\s.,]*|один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|"
    r"одиннадцать|двенадцать|двадцать|тридцать|сорок|пятьдесят|шестьдесят|семьдесят|восемьдесят|девяносто|сто|двести|триста|тысяч\w*|миллион\w*|миллиард\w*|процент\w*|десятк\w*|год\w*|часов|суток|дней|дня)\b", re.I
)
MAX_CAPTION_WORDS = 5


def short_fact(text: str) -> str:
    """Короткая надпись: ЧИСЛО или ФАКТ, 3-5 слов капсом. Не пересказ.

    Было: в надпись уезжала дословная копия фразы, которая в эту же секунду
    звучит — целое предложение на 60-140 знаков. Всплывашка обязана ДОБАВЛЯТЬ,
    а повтор закадрового текста не добавляет ничего. Нет числа или факта —
    надписи на этой сцене нет вовсе.
    """
    words = " ".join((text or "").split()).split()
    for index, word in enumerate(words):
        if not _NUMBER.fullmatch(word.strip(".,;:!?»«()")):
            continue
        chunk = words[index:index + MAX_CAPTION_WORDS]
        phrase = " ".join(w.strip(".,;:!?»«()") for w in chunk).strip()
        if 2 <= len(phrase.split()) <= MAX_CAPTION_WORDS:
            return phrase.upper()
    return ""


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

        def reject(reason: str) -> None:
            stats["rejected"] += 1
            stats["rejected_by_subtype"][reason] = stats["rejected_by_subtype"].get(reason, 0) + 1

        if not query or len(text.strip()) < 60:
            reject("no_concrete_scene_subject")
            continue
        # ЧТО ОНО ИЛЛЮСТРИРУЕТ: предмет должен быть НАЗВАН В ЭТОЙ СЦЕНЕ и
        # ОТСУТСТВОВАТЬ В БАЗЕ. Содержимое базы берём из её запроса — иначе
        # правило «добавляет то, чего в базе нет» вообще нереализуемо.
        base = _stem(query.split()[0]) if query.split() else ""
        addition = next((s for s in scene_subjects(text) if _stem(s) != base), "")
        fact = short_fact(text)
        if not addition and not fact:
            reject("no_answer_to_what_it_illustrates")
            continue
        if addition and _stem(addition) == base:
            reject("same_semantic_layer")
            continue
        # Разрежение — служебное ограничение, и причина у него СВОЯ: смешивать
        # его с «тот же смысловой слой» нельзя, иначе цифра отчёта врёт.
        if chosen and int(scene["id"]) - int(chosen[-1]["id"]) < 9:
            reject("too_close_to_previous")
            continue
        scene = {**scene, "_addition": addition, "_fact": fact}
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
            "query": scene.get("_addition") or "",
            "text": {
                "words": scene.get("_fact", ""),
                "color": "white",
                "font": "default",
                "pos": "tl" if side == "left" else "tr",
                "at": round(min(0.7, max(0.25, float(scene.get("duration_sec", 10)) * 0.04)), 2),
                "scale": 1.0,
                "sound": old.get("sound", "pop"),
            },
            "variants": [
                {"kind": "text", "words": scene.get("_fact", ""), "selected": bool(scene.get("_fact")) and channel != "ПЛАНЕТА"},
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
