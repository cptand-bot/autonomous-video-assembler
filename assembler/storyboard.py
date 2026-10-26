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

_STARLINK_OBJECTS = [
    "Илон Маск выступление на сцене", "Илон Маск интервью у микрофона", "Илон Маск у логотипа SpaceX",
    "ракета Falcon 9 стартует с площадки", "носитель Falcon 9 на стартовом столе", "носитель Starship на полигоне",
    "космический центр SpaceX с земли", "башня Starlink на крыше здания", "терминал Starlink в полевых условиях",
    "антенна спутниковой связи крупный план", "спутник Starlink на орбите Земли", "созвездие спутников на ночном небе",
    "спутниковая тарелка на украинской позиции", "оператор настраивает терминал связи", "военный оператор с терминалом связи",
    "украинский расчёт беспилотника", "беспилотник готовится к запуску", "беспилотный аппарат на стартовой площадке",
    "операторский терминал беспилотника крупный план", "антенны связи на военной базе", "полевая радиостанция с антенной",
    "мобильный пункт связи на автомобиле", "спутниковый интернет в автомобиле", "ноутбук подключён к Starlink",
    "портативный терминал связи на столе", "кабель спутниковой антенны крупный план", "тарелка связи на фоне неба",
    "военная техника на украинской дороге", "бронемашина на просёлочной дороге", "военный грузовик у временной базы",
    "оператор наблюдает карту на экране", "цифровая карта боевой зоны на мониторе", "экран системы спутниковой связи",
    "центр управления спутниковой сетью", "серверная телекоммуникационного центра", "инженер проверяет оборудование связи",
    "монтажник устанавливает антенну на крыше", "ремонт спутникового терминала на открытом воздухе", "телекоммуникационная мачта в поле",
    "антенный комплекс на военной базе", "радиолокационная станция на позиции", "наблюдательный дрон над полем",
    "взлёт беспилотника с площадки", "военный аэродром с беспилотниками", "грузовой самолёт на аэродроме Украины",
    "грузовая платформа с военной техникой", "склад военного оборудования снаружи", "разгрузка военной помощи на аэродроме",
    "украинские военнослужащие у техники", "машина связи на украинской позиции", "полевой штаб с антеннами",
    "спутниковая антенна зимой на открытом воздухе", "терминал связи рядом с бронемашиной", "оператор связи в защитном шлеме",
    "связисты прокладывают кабель в поле", "мобильная станция связи на грузовике",
]


def build_search_query(text: str, used: set[str], topic: str = "") -> str:
    """Make a compact object-oriented query, never a narration slice.

    This is a conservative fallback for SRT-only runs. GEO2/curated storyboard
    queries remain authoritative when supplied by an upstream agent.
    """
    if "starlink" in topic.lower() and used is not None:
        index = len(used)
        if index < len(_STARLINK_OBJECTS):
            return f"{_STARLINK_OBJECTS[index]}, {topic}, реальное фото"
    words = []
    for raw in text.replace("—", " ").replace("–", " ").split():
        word = raw.strip(".,!?;:\"()[]{}«»").lower()
        if len(word) >= 4 and word not in _STOPWORDS and word not in words:
            words.append(word)
    candidates = []
    anchor = " ".join(topic.split()[:4]).strip()
    for start in range(max(1, len(words) - 1)):
        if start + 1 < len(words):
            candidates.append(f"{words[start]} {words[start + 1]} {anchor} реальное фото".strip())
    for query in candidates:
        if query not in used and " ".join(query.split()[:3]) not in {" ".join(x.split()[:3]) for x in used}:
            return query
    # Keep the query distinct without using a scene number or service wording.
    tail = next((w for w in words[3:] if w not in used), "событие")
    return f"{anchor or 'реальное фото'} {tail} {words[0] if words else 'событие'}".strip()


def build_scenes(cues: list[Cue], channel: str, topic: str = "") -> dict:
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
        query = build_search_query(text, used_queries, topic)
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
