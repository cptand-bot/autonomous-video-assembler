from __future__ import annotations

from .srt import Cue


def build_scenes(cues: list[Cue], channel: str) -> dict:
    if not cues:
        return {"channel": channel, "scenes": []}
    total = cues[-1].end
    target = max(1, round(total / 11.5))
    groups: list[list[Cue]] = []
    current: list[Cue] = []
    for cue in cues:
        current.append(cue)
        elapsed = current[-1].end - current[0].start
        remaining = len(cues) - sum(len(g) for g in groups) - len(current)
        if (total <= 12 and len(current) == 1) or (len(groups) + 1 < target and elapsed >= 9 and remaining >= 1) or (len(groups) + 1 == target):
            groups.append(current); current = []
    if current:
        groups.append(current)
    scenes = []
    for index, group in enumerate(groups, start=1):
        start = 0.0 if index == 1 else scenes[-1]["start_sec"] + scenes[-1]["duration_sec"]
        duration = round(group[-1].end - group[0].start, 3)
        text = " ".join(c.text.strip() for c in group).strip()
        scenes.append(
            {
                "id": index,
                "text": text,
                "start_sec": round(start, 3),
                "duration_sec": duration,
                "visual_prompt": f"Реальный новостной кадр по предмету: {text[:180]}",
                "source": "press_photo",
                "source_query": text[:180],
            }
        )
    return {"channel": channel, "scenes": scenes}
