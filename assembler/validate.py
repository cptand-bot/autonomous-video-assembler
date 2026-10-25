from __future__ import annotations

from collections import Counter

from .guards import storyboard_warnings


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload.get("channel"), str) or not payload["channel"].strip():
        errors.append("channel must be a non-empty string")
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return errors + ["scenes must be a non-empty list"]

    expected_start = 0.0
    ids = []
    durations = []
    queries = []
    for position, scene in enumerate(scenes, start=1):
        for field in ("id", "text", "start_sec", "duration_sec", "visual_prompt", "source", "source_query"):
            if field not in scene:
                errors.append(f"scene {position}: missing {field}")
        if scene.get("id") != position:
            errors.append(f"scene {position}: id is not sequential")
        ids.append(scene.get("id"))
        start = scene.get("start_sec")
        duration = scene.get("duration_sec")
        if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)):
            errors.append(f"scene {position}: time values must be numeric")
            continue
        if abs(start - expected_start) > 0.001:
            errors.append(f"scene {position}: gap or overlap at {start}")
        if duration <= 0:
            errors.append(f"scene {position}: duration must be positive")
        expected_start = round(start + duration, 3)
        durations.append(duration)
        queries.append(scene.get("source_query"))
    if len(set(ids)) != len(ids):
        errors.append("scene ids must be unique")
    non_cards = [query for scene, query in zip(scenes, queries) if not str(scene.get("source", "")).startswith("card:")]
    if len(non_cards) != len(set(non_cards)):
        errors.append("non-card source_query values must be unique")
    if len(durations) > 1 and len(set(durations)) == 1:
        errors.append("all scene durations are identical")
    return errors


def assert_valid(payload: dict) -> None:
    errors = validate_payload(payload)
    if errors:
        raise ValueError("Invalid scenes payload: " + "; ".join(errors))


def storyboard_review(payload: dict, narration_sec: float | None = None) -> list[str]:
    """Norms a storyboard must satisfy before anything is fetched.

    Separate from `validate_payload` on purpose: that one answers "is this file
    well-formed", this one answers "is this a storyboard we can shoot". The
    second question is where the expensive defects live - scene count against
    the narration, drawn-card spacing, stock share, query mines, and one object
    ordered many times with different wording.
    """
    return storyboard_warnings(payload.get("scenes") or [], narration_sec)
