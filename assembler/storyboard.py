from __future__ import annotations

from .srt import Cue


_STOPWORDS = {
    "это", "как", "что", "для", "при", "после", "перед", "между", "через", "также",
    "был", "была", "были", "будет", "есть", "его", "её", "их", "этот", "эта", "эти",
    "один", "одна", "одни", "уже", "еще", "ещё", "только", "самый", "свой", "свои",
    "который", "которая", "которые", "потому", "такой", "такая", "может", "могут",
    "говорит", "говорят", "сообщает", "сообщают", "заявил", "заявила", "заявили",
    "сказал", "сказала", "сказали", "будто", "если", "тогда", "теперь", "где", "когда",
    "в", "во", "на", "из", "к", "у", "о", "об", "от", "до", "по", "за", "и", "или",
    "но", "а", "не", "ни", "же", "ли", "что"
}


def build_search_query(text: str, used: set[str]) -> str:
    """Make a compact object-oriented query, never a narration slice.

    This is a conservative fallback for SRT-only runs. GEO2/curated storyboard
    queries remain authoritative when supplied by an upstream agent.
    """
    words = []
    for raw in text.replace("—", " ").replace("–", " ").split():
        word = raw.strip(".,!?;:\"()[]{}«»").lower()
        if len(word) >= 4 and word not in _STOPWORDS and word not in words:
            words.append(word)
    candidates = []
    for width in (6, 5, 4, 3):
        if len(words) >= width:
            candidates.append("реальное фото " + " ".join(words[:width]))
    for query in candidates:
        if query not in used and " ".join(query.split()[:3]) not in {" ".join(x.split()[:3]) for x in used}:
            return query
    # Keep the query distinct without using a scene number or service wording.
    tail = next((w for w in words[3:] if w not in used), "событие")
    return f"реальное фото {tail} {words[0] if words else 'новости'}"


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
        if (total <= 12 and len(current) == 1) or (elapsed >= 11.5 and remaining >= 1):
            groups.append(current); current = []
    if current:
        groups.append(current)
    scenes = []
    used_queries: set[str] = set()
    for index, group in enumerate(groups, start=1):
        start = 0.0 if index == 1 else scenes[-1]["start_sec"] + scenes[-1]["duration_sec"]
        duration = round(group[-1].end - group[0].start, 3)
        text = " ".join(c.text.strip() for c in group).strip()
        query = build_search_query(text, used_queries)
        used_queries.add(query)
        scenes.append(
            {
                "id": index,
                "text": text,
                "start_sec": round(start, 3),
                "duration_sec": duration,
                "visual_prompt": f"Реальный новостной кадр по предмету: {query}",
                "source": "press_photo",
                "source_query": query,
            }
        )
    return {"channel": channel, "scenes": scenes}
