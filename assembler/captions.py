from __future__ import annotations

import re
from pathlib import Path


def ass_time(seconds: float) -> str:
    total = max(0, int(round(seconds * 100)))
    centis = total % 100; total //= 100
    sec = total % 60; total //= 60
    minute = total % 60; hour = total // 60
    return f"{hour}:{minute:02d}:{sec:02d}.{centis:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\\{").replace("}", r"\\}").replace("\n", r"\\N")


def scenes_to_ass(scenes: list[dict]) -> str:
    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,42,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,55,1\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"""
    lines = [header]
    for scene in scenes:
        start = float(scene["start_sec"]); end = start + float(scene["duration_sec"])
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,{ass_escape(str(scene.get('text', '')))}\n")
    return "".join(lines)


def write_ass(scenes: list[dict], path: Path) -> None:
    path.write_text(scenes_to_ass(scenes), encoding="utf-8-sig")
