from __future__ import annotations

from .srt import Cue


def build_scenes(cues: list[Cue], channel: str) -> dict:
    scenes = []
    for index, cue in enumerate(cues, start=1):
        start = 0.0 if index == 1 else scenes[-1]["start_sec"] + scenes[-1]["duration_sec"]
        duration = round(cue.end - cue.start, 3)
        scenes.append(
            {
                "id": index,
                "text": cue.text,
                "start_sec": round(start, 3),
                "duration_sec": duration,
                "visual_prompt": "Визуальный запрос будет добавлен после редакционной раскладки.",
                "source": "card:quote",
                "source_query": cue.text[:140],
            }
        )
    return {"channel": channel, "scenes": scenes}
