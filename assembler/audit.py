from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FORBIDDEN = ("документальный кадр", "общий план", "сцена№")
MINE_WORDS = ("окоп", "траншея", "блиндаж", "землянка", "наблюдательный пункт", "полевой лагерь", "авария", "взрыв", "сгоревший", "топливо", "валюта", "доллары", "конвейер", "assembly line", "флаг у здания")
ANCHOR_WORDS = ("росси", "украин", "сша", "американ", "европ", "москв", "киев", "донецк", "луган", "одесс", "берлин", "лондон", "кремл", "мид", "парламент", "министер", "порт", "аэропорт", "станци", "терминал", "завод", "бундестаг", "маск", "starlink")


def audit_storyboard(root: Path) -> list[str]:
    payload = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    scenes = payload.get("scenes", [])
    errors: list[str] = []
    warnings: list[str] = []
    if not scenes:
        return ["no scenes"]
    total = sum(float(s.get("duration_sec", 0)) for s in scenes)
    expected = total / 11.5
    if total >= 20 and (len(scenes) < expected * 0.9 or len(scenes) > expected * 1.1):
        errors.append(f"scene count {len(scenes)} outside formula range {expected * .9:.1f}-{expected * 1.1:.1f}")
    durations = [float(s.get("duration_sec", 0)) for s in scenes]
    if total >= 20 and min(durations) < 5:
        errors.append("scene shorter than 5 seconds")
    if max(durations) > 15:
        errors.append("scene longer than 15 seconds")
    cards = [s for s in scenes if str(s.get("source", "")).startswith("card:")]
    if cards and len(cards) > max(1, len(scenes) // 15 + 1):
        errors.append(f"too many cards: {len(cards)}")
    queries = [str(s.get("source_query", "")).strip().lower() for s in scenes if not str(s.get("source", "")).startswith("card:")]
    if len(queries) != len(set(queries)):
        errors.append("duplicate source_query")
    heads = [" ".join(q.split()[:3]) for q in queries]
    if len(heads) != len(set(heads)):
        errors.append("duplicate first three query words")
    for scene in scenes:
        query = str(scene.get("source_query", "")).lower()
        if any(word in query for word in FORBIDDEN) or re.search(r"\bсцена\s*\d+\b", query):
            errors.append(f"scene {scene.get('id')}: service wording in source_query")
        if any(word in query for word in MINE_WORDS):
            errors.append(f"scene {scene.get('id')}: dangerous search term in source_query")
        if not str(scene.get("source", "")).startswith("card:") and not any(word in query for word in ANCHOR_WORDS):
            warnings.append(f"scene {scene.get('id')}: query has no geographic, institutional, or named anchor")
    return errors + [f"WARNING: {x}" for x in warnings]


def main() -> None:
    parser = argparse.ArgumentParser(description="Machine audit gate for storyboard")
    parser.add_argument("--root", type=Path, default=Path("build"))
    args = parser.parse_args()
    findings = audit_storyboard(args.root)
    errors = [x for x in findings if not x.startswith("WARNING:")]
    warnings = [x for x in findings if x.startswith("WARNING:")]
    (args.root / "audit_report.json").write_text(json.dumps({"status": "blocked" if errors else "ok", "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "blocked" if errors else "ok", "errors": errors, "warnings": warnings}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
