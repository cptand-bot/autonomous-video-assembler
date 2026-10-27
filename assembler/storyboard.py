from __future__ import annotations
import re

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

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_WORD = re.compile(r"[А-ЯЁA-Za-zа-яё][А-ЯЁA-Za-zа-яё\-]{2,}")
# Названия изданий и агрегаторов предметом съёмки НЕ являются и на экран не
# попадают никогда — отдельное правило. Как поисковый запрос они дают логотип
# редакции вместо события.
_NOT_A_SUBJECT = {
    "the", "new", "york", "times", "post", "news", "reuters", "bloomberg", "axios",
    "politico", "guardian", "cnn", "bbc", "риа", "тасс", "лента", "рбк", "интерфакс",
    "unian", "liga", "газета", "издание", "агентство", "телеканал", "корреспондент",
    "telegram", "ютуб", "youtube", "пост", "публикация", "канал", "соцсеть",
}


_PRONOUNS = {"эту", "этот", "эта", "эти", "тот", "та", "те", "они", "она", "оно", "мы", "вы", "ты", "он"}


def _stem(word: str) -> str:
    """Грубая основа слова: достаточно, чтобы склонения считались одним предметом."""
    return word.lower().rstrip("аеёиыоуюяйьъ")[:5] or word.lower()[:5]


def scene_subjects(text: str) -> list[str]:
    """Названные в сцене предметы: имена собственные и латиница.

    Это единственное, что можно достоверно вытащить из одного SRT. Нарицательные
    слова озвучки предметом НЕ являются: из «операции пришлось остановить»
    предмет не «операции пришлось». Попытка лепить запрос из двух слов озвучки
    давала «правильные произносит реальное фото» — кадр ни о чём.
    """
    found: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.replace("—", " ").replace("–", " ")):
        for index, raw in enumerate(_WORD.findall(sentence)):
            word = raw.strip("-")
            if len(word) < 3:
                continue
            latin = bool(re.fullmatch(r"[A-Za-z][A-Za-z\-]+", word))
            # Заглавная в начале предложения ничего не значит — пропускаем её.
            proper = word[0].isupper() and (index > 0 or latin)
            if word.lower() in _NOT_A_SUBJECT or word.lower() in _PRONOUNS:
                continue
            if (proper or latin) and word.lower() not in _STOPWORDS and word not in found:
                found.append(word)
    return found
_OBJECT_HINTS = (
    "маск", "трамп", "starlink", "starshield", "украин", "киев", "пентагон",
    "антенн", "терминал", "спутник", "ракета", "starship", "falcon", "фронт",
    "карта", "оператор", "тариф", "интернет", "связ", "дрон", "аппарат", "база",
    "генератор", "трансформатор", "подстанц", "кабел", "завод", "самолёт", "самолет",
    "машин", "техник", "экран", "микрофон", "сцен", "дом", "здан", "порт", "аэродром",
)


def build_search_query(text: str, used: set[str], topic: str = "") -> str:
    """Запрос СТРОГО из предмета, названного в этой сцене. Иначе — пусто.

    `topic` в построении НЕ участвует: запрос обязан зависеть только от смысла
    сцены. Ветка по теме ролика или список готовых строк под ролик запрещены —
    на этом уже обожглись: список из 56 запросов выдавался по НОМЕРУ сцены и
    осмысленно выглядел ровно на одном ролике.

    Пустая строка — honest-результат, а не ошибка: сцена помечается «нужен
    ручной запрос» и уходит человеку на дашборд. Пустая пометка ЛУЧШЕ
    выдуманного кадра: пометку он закроет за десять секунд, а чужую картинку
    не заметит.
    """
    names = scene_subjects(text)
    subject = names[0] if names else ""
    words = []
    for raw in text.replace("—", " ").replace("–", " ").split():
        word = raw.strip(".,!?;:\"()[]{}«»").lower()
        if len(word) >= 4 and word not in _STOPWORDS and word not in words:
            words.append(word)
    if not subject:
        meaningful = [word for word in words if any(hint in word for hint in _OBJECT_HINTS)]
        subject = meaningful[0] if meaningful else ""
    if not subject:
        return ""
    subject_stem = _stem(subject)
    details = [
        word for word in words
        if _stem(word) != subject_stem
        and word not in {name.lower() for name in names}
        and word not in _NOT_A_SUBJECT
    ]
    # A query needs a physical/detail anchor. Generic modifiers are discarded;
    # they are exactly what turned narration fragments into meaningless searches.
    details = [word for word in details if len(word) >= 5]
    candidates = []
    for size in (3, 2, 1):
        for start in range(0, max(0, len(details) - size + 1)):
            detail = " ".join(details[start:start + size])
            candidates.append(f"{subject} {detail} 2026")
    for query in candidates:
        if query not in used and " ".join(query.split()[:3]) not in {" ".join(x.split()[:3]) for x in used}:
            return query
    # Keep the query distinct without using a scene number or service wording.
    return ""


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
    texts = [" ".join(c.text.strip() for c in group).strip() for group in groups]
    own = [scene_subjects(text) for text in texts]
    # Предмет ПЕРЕНОСИТСЯ по сценам: речь идёт о том же субъекте, пока не назван
    # новый. Так работает любая устная речь, и наше правило это разрешает —
    # запрещён только БУКВАЛЬНО тот же кадр, а разные фото одного субъекта в
    # разных сценах можно (дедупликация по md5 это и обеспечивает).
    # Без переноса 45 сцен из 55 оставались жёлтыми карточками «нужно твоё
    # фото» — это не результат, а перестраховка.
    fallback = next((names[0] for names in own if names), "")
    used_count: dict[str, int] = {}
    assigned: list[tuple[str, bool]] = []
    carried = ""
    for names in own:
        if names:
            # Из названных в сцене берём наименее использованный — так субъекты
            # распределяются по ролику, а не один повторяется весь ролик.
            pick = min(names, key=lambda n: (used_count.get(_stem(n), 0), names.index(n)))
            carried = pick
            # Повтор субъекта — не ошибка: сцена может снова называть того же
            # человека, и это НАМЕРЕННЫЙ повтор запроса (разные фото одного
            # субъекта разрешены). Помечаем, чтобы проверка уникальности его
            # не заваливала.
            assigned.append((pick, used_count.get(_stem(pick), 0) > 0))
        else:
            assigned.append((carried or fallback, True))
        chosen = assigned[-1][0]
        if chosen:
            used_count[_stem(chosen)] = used_count.get(_stem(chosen), 0) + 1

    scenes = []
    used_queries: set[str] = set()
    for index, (group, text, (subject, inherited)) in enumerate(zip(groups, texts, assigned), start=1):
        start = 0.0 if index == 1 else scenes[-1]["start_sec"] + scenes[-1]["duration_sec"]
        duration = round(group[-1].end - group[0].start, 3)
        query = build_search_query(f"{text} {subject}" if subject else text, used_queries, topic)
        if not query and subject:
            query = build_search_query(subject, used_queries, topic)
        if query:
            used_queries.add(query)
        scene = {
            "id": index,
            "text": text,
            "start_sec": round(start, 3),
            "duration_sec": duration,
            "visual_prompt": (
                f"Реальный новостной кадр по предмету: {query}" if query
                else "Нужен ручной запрос: в сцене не назван предмет съёмки"
            ),
            "source": "press_photo" if query else "card:manual_query",
            "source_query": query,
            "subject": subject,
        }
        if inherited and subject:
            # Пометка для аудита и для человека: предмет взят из соседней сцены,
            # поэтому повтор запроса здесь намеренный, а не ошибка.
            scene["inherited_subject"] = True
        if not query:
            scene["needs_manual_query"] = True
        scenes.append(scene)
    return {"channel": channel, "scenes": scenes}
