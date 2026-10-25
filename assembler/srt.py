from __future__ import annotations

import re
from dataclasses import dataclass


TIMECODE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})"
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def parse_time(value: str) -> float:
    match = TIMECODE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timecode: {value}")
    parts = {key: int(raw) for key, raw in match.groupdict().items()}
    return parts["h"] * 3600 + parts["m"] * 60 + parts["s"] + parts["ms"] / 1000


def parse_srt(raw: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\r?\n\s*\r?\n", raw.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines()]
        if not lines:
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        left, right = [part.strip() for part in lines[timing_index].split("-->", 1)]
        text = " ".join(line for line in lines[timing_index + 1 :] if line)
        if not text:
            continue
        start, end = parse_time(left), parse_time(right)
        if end <= start:
            raise ValueError(f"SRT cue ends before it starts: {left} --> {right}")
        cues.append(Cue(start, end, text))
    if not cues:
        raise ValueError("SRT contains no readable cues")
    return cues
