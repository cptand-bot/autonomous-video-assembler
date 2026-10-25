"""Rejection filters ported from the production Cloud Code pipeline.

The pipeline in this repository reproduces the *path* (srt -> storyboard ->
search -> review -> render). What it was missing is the set of guards that
reject bad material before a human ever sees it. Every threshold below comes
from a measurement on real builds, not from taste:

* width < 1600 px is the single most common defect (13 of 47 frames on one
  shipped video, worst 943 px) - the frame is stretched to 1920 and the person
  in it stops being recognisable;
* a banned frame returns through the *cache*, not through search, so the ban
  list has to be consulted when a file is already on disk too;
* a query that merely reads differently is not a different query: one object
  ordered eight times with different wording produced 35 scenes out of 69 on
  five objects, with 64 of 64 "unique" query strings;
* replacements are dirtier than first-pass results - six measurements in a row,
  16-31 % first pass against 36-79 % in the replacement sheet.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

CARD_PREFIX = "card:"

# ---------------------------------------------------------------- domains ---
# Hosts that keep returning watermarked stock, catalogue shots on white, or
# AI-generated pictures that look like photographs at thumbnail size.
BANNED_HOSTS = (
    "alamy.", "dreamstime.", "shutterstock.", "gettyimages.", "depositphotos.",
    "istockphoto.", "123rf.", "lori.ru", "pixel-shot.", "fotolia.",
    "airliners.net", "jetphotos.", "russianplanes.", "planespotters.",
    "etsystatic.", "satu.kz", "pinterest.", "tehnomaks.",
    "public.bnbstatic.com",
)
# Yandex' own generative service: always a 1024x1024 square that reads as a
# photo until you look twice.
BANNED_PATHS = ("/get-shedevrum/",)


def host_is_banned(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in BANNED_HOSTS) or any(p in low for p in BANNED_PATHS)


def filter_candidates(candidates: list[dict]) -> list[dict]:
    """Drop search hits that come from a host we never accept."""
    return [c for c in candidates if not host_is_banned(str(c.get("full") or c.get("thumb") or ""))]


# -------------------------------------------------------------- ban list ---
def md5_of(path: str | Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_bans(path: str | Path) -> dict[str, dict]:
    """Active bans only: a timed ban expires silently and the frame comes back.

    That expiry is itself a known trap - a clip banned for ten days returned on
    day eleven through the same generic query, and it looked like a new defect
    rather than an expired timer.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = time.time()
    active = {}
    for digest, meta in raw.items():
        if not isinstance(meta, dict):
            meta = {"reason": str(meta)}
        until = meta.get("until")
        if until and float(until) < now:
            continue
        active[digest] = meta
    return active


def banned_files(root: str | Path, bans: dict[str, dict], patterns=("images/scene_*", "overlays/scene_*")) -> list[tuple[str, dict]]:
    """Final gate before shipping: every frame of the build against the ban list.

    Runs last on purpose. The list changes *while* a build is in flight - with
    several assemblers working in parallel one of them bans a frame that another
    one is already holding, and the only thing that catches it is a sweep right
    before the send.
    """
    root = Path(root)
    hits = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.suffix in {".json", ".png"} or not path.is_file():
                continue
            digest = md5_of(path)
            if digest in bans:
                hits.append((str(path), bans[digest]))
    return hits


# --------------------------------------------------------------- quality ---
MIN_WIDTH = 1600          # full-frame scenes
MIN_WIDTH_OVERLAY = 800   # pop-ups are small on screen
MIN_DENSITY = 0.08        # bytes per pixel; below 0.06 is always an upscale


def frame_quality(path: str | Path) -> dict:
    """Width, height and bytes-per-pixel. No decoding beyond the header."""
    from PIL import Image

    path = Path(path)
    with Image.open(path) as image:
        width, height = image.size
    size = path.stat().st_size
    density = size / float(width * height) if width and height else 0.0
    return {"path": str(path), "w": width, "h": height, "density": round(density, 4)}


def quality_warnings(paths, min_width: int = MIN_WIDTH) -> list[str]:
    """Suspicions for a human to look at, never an automatic reject.

    The numbers are wrong in both directions: a 5616x3744 frame compresses
    efficiently and scores a low density while being excellent, and a smooth
    night scene scores low sharpness while being fine.
    """
    out = []
    for path in paths:
        try:
            info = frame_quality(path)
        except Exception as exc:  # noqa: BLE001 - a broken file is itself a finding
            out.append(f"{path}: unreadable ({exc})")
            continue
        if info["w"] < min_width:
            out.append(f"{info['path']}: width {info['w']} < {min_width}")
        elif info["density"] < MIN_DENSITY:
            out.append(f"{info['path']}: density {info['density']} < {MIN_DENSITY} (looks upscaled)")
    return out


# ------------------------------------------------------------ query lint ---
# Each entry: (pattern, what comes back instead, how to fix it). Only the
# classes that cost us whole fix rounds are carried over.
QUERY_MINES: tuple[tuple[str, str, str], ...] = (
    (r"повестк|мобилизац|призывник|облав",
     "the most widely circulated photo for this is a detention, violence or a crowd with children",
     "ask for an object: the building, the entrance, an empty hall"),
    (r"розыск|wanted",
     "a real private citizen's wanted notice with name, face and a tip-line number",
     "describe the activity (a patrol, a patrol car), never the concept of being hunted"),
    (r"документ|контракт|бланк|договор|закон\b",
     "a readable document, which is banned outright",
     "show the people, the place or the object instead"),
    (r"школ|детсад|ученик|подрост",
     "children in frame, banned in any form",
     "equipment only, an empty classroom, a facade"),
    (r"\bкамер\b(?!.*(турель|оруж|наблюд))",
     "an ordinary photographer's camera",
     "anchor it to the device: turret camera, gun optics mount"),
    (r"трибун",
     "a football stadium stand - the word's dominant meaning",
     "ask for «за кафедрой» or «у микрофонов»"),
    (r"диспетчерск|пульт управлен",
     "a switch cabinet or a branded port tower",
     "ask for an operator at the desk, or change the object"),
    (r"железнодорож|электричк|вокзал",
     "Russian railways or a Soviet-era archive shot",
     "name the object precisely or move to a detail"),
    (r"топлив",
     "a black-and-white WWII archive frame",
     "name branch + country + year, drop the word «топливо»"),
    (r"зал\b|интерьер",
     "the institution's single most famous historical photo",
     "ask for the facade, or add a year and a serving official"),
    (r"подсветк",
     "LED-contractor advertising",
     "ask for the facade with a year"),
    (r"портрет.*(поэт|писател|философ)",
     "the cover of a book about them - text in frame",
     "ask for a photographic portrait plus dates or place"),
    (r"инфографик|диаграмм|график|схем",
     "a branded state-media or finance-blog graphic",
     "ask for a real photo of people, a building or an object"),
)

# Stock libraries are indexed in English; everything else is searched in
# Russian, for every country and every person. A non-Russian query outside the
# stock sources is a defect by construction.
_NON_RU_LETTERS = re.compile(r"[іїєґ]")
_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
_TRANSPORT = re.compile(r"traffic|road|street|train|subway|truck|motorway|platform")
_CLOSEUP = re.compile(r"closeup|close-up|macro|detail|texture|reflection")


def lint_query(query: str, source: str) -> list[str]:
    """Hard findings only. Returns a list of human-readable problems."""
    problems: list[str] = []
    text = (query or "").strip()
    if not text or str(source).startswith(CARD_PREFIX):
        return problems
    low = text.lower()

    if str(source).startswith("pexels"):
        if _CYRILLIC.search(text):
            problems.append("stock search is indexed in English - this query is Cyrillic")
        if _TRANSPORT.search(low) and not _CLOSEUP.search(low):
            problems.append(
                "transport scene without a country: English stock returns a random country "
                "(a sign, a plate or a number is always in frame) - go to a closeup detail")
        return problems

    if not _CYRILLIC.search(text):
        problems.append("press and web search must be queried in Russian")
    if _NON_RU_LETTERS.search(low):
        problems.append("Ukrainian letters in the query - Russian only, for every country")
    for pattern, gets, fix in QUERY_MINES:
        if re.search(pattern, low):
            problems.append(f"mine «{pattern}»: {gets} -> {fix}")
    return problems


def cross_check_queries(entries: list[tuple[str, str]]) -> list[str]:
    """Every query of the build against every other one.

    Uniqueness inside one file is not enough: a pop-up added late got exactly
    the query of another scene's base shot, search honestly returned one file,
    and only a checksum sweep after the fetch caught it.
    """
    import difflib

    problems: list[str] = []
    seen: dict[str, str] = {}
    for label, query in entries:
        if not query:
            continue
        norm = " ".join(sorted(re.findall(r"[а-яёa-z0-9]{3,}", query.lower())))
        if not norm:
            continue
        if norm in seen:
            problems.append(f"duplicate query: {seen[norm]} and {label} word for word - search returns one file")
        else:
            seen[norm] = label
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            (label_a, query_a), (label_b, query_b) = entries[i], entries[j]
            if not (query_a and query_b):
                continue
            ratio = difflib.SequenceMatcher(None, query_a.lower(), query_b.lower()).ratio()
            if 0.82 <= ratio < 1.0:
                problems.append(f"near-identical queries ({ratio:.0%}): {label_a} and {label_b}")
    return problems


# -------------------------------------------------------- storyboard norms ---
SECONDS_PER_SCENE = 11.5   # median across shipped videos is 11.6 s
SCENE_TOLERANCE = 0.10
CARDS_PER_SCENES = 15      # one drawn card per fifteen scenes, +-1
CARD_GAP = 8               # never closer than eight scenes
OBJECT_LIMIT = 3           # no object on more than three scenes
STOCK_RANGE = (0.10, 0.20) # share of runtime

# Words that belong to our own query templates, not to the subject.
_OBJECT_STOPWORDS = {
    "реальн", "фотогр", "крупны", "общий", "кадр", "съёмка", "съемка",
    "украин", "россий", "москва", "видео", "плане", "вид",
    "январ", "феврал", "марта", "апрел", "июня", "июля",
    "август", "сентяб", "октябр", "ноябр", "декабр",
}


def repeated_objects(scenes: list[dict], limit: int = OBJECT_LIMIT) -> list[str]:
    """One object ordered many times with different wording.

    This is the defect no other check sees: the storyboard passes every numeric
    norm, all query strings are unique, and the viewer still gets the same hall
    eight times. Grouped by the stem of the noun, not by the phrase.
    """
    roots: dict[str, list[int]] = {}
    for scene in scenes:
        if str(scene.get("source", "")).startswith(CARD_PREFIX):
            continue
        seen: set[str] = set()
        for word in re.findall(r"[а-яёa-z]{5,}", str(scene.get("source_query", "")).lower()):
            root = word[:6]
            if root in _OBJECT_STOPWORDS or root in seen:
                continue
            seen.add(root)
            roots.setdefault(root, []).append(scene.get("id"))
    heavy = sorted(((r, ids) for r, ids in roots.items() if len(ids) > limit),
                   key=lambda item: len(item[1]), reverse=True)
    return [f"object «{root}…» on {len(ids)} scenes ({', '.join(map(str, ids[:8]))}) - limit is {limit}"
            for root, ids in heavy[:5]]


def storyboard_warnings(scenes: list[dict], narration_sec: float | None = None) -> list[str]:
    """Norms that a storyboard has to satisfy before anything is fetched."""
    problems: list[str] = []
    if not scenes:
        return ["no scenes"]

    total = sum(float(s.get("duration_sec") or 0) for s in scenes)
    if narration_sec:
        want = narration_sec / SECONDS_PER_SCENE
        low, high = round(want * (1 - SCENE_TOLERANCE)), round(want * (1 + SCENE_TOLERANCE))
        if not low <= len(scenes) <= high:
            problems.append(f"{len(scenes)} scenes against a norm of {round(want)} ({low}-{high})")
        if abs(total - narration_sec) > 1.5:
            problems.append(f"durations sum to {total:.1f} s against narration {narration_sec:.1f} s")

    cards = [s["id"] for s in scenes if str(s.get("source", "")).startswith(CARD_PREFIX)]
    want_cards = max(1, round(len(scenes) / CARDS_PER_SCENES))
    if abs(len(cards) - want_cards) > 1:
        problems.append(f"{len(cards)} drawn cards against a norm of {want_cards} (+-1)")
    for first, second in zip(cards, cards[1:]):
        if second - first < CARD_GAP:
            problems.append(f"cards on scenes {first} and {second} are closer than {CARD_GAP} scenes")

    stock = sum(float(s.get("duration_sec") or 0) for s in scenes
                if str(s.get("source", "")).startswith("pexels"))
    if total:
        share = stock / total
        if share > STOCK_RANGE[1]:
            problems.append(f"stock is {share:.0%} of runtime, ceiling is {STOCK_RANGE[1]:.0%}")
        elif share < STOCK_RANGE[0]:
            problems.append(f"stock is {share:.0%} of runtime, floor is {STOCK_RANGE[0]:.0%} "
                            "(acceptable when the script has no concrete objects - say so with a number)")

    problems.extend(repeated_objects(scenes))
    for scene in scenes:
        for issue in lint_query(str(scene.get("source_query", "")), str(scene.get("source", ""))):
            problems.append(f"scene {scene.get('id')}: {issue}")
    problems.extend(cross_check_queries(
        [(f"scene {s.get('id')}", str(s.get("source_query", ""))) for s in scenes]))
    return problems


# ------------------------------------------------------------ fix rounds ---
ROUND_BUDGET = 2
ROUNDS_FILE = ".fix_rounds.json"


def load_rounds(root: str | Path) -> dict:
    try:
        return json.loads((Path(root) / ROUNDS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rounds": [], "tried": {}}


def check_round(root: str | Path, fixes: dict[str, str]) -> tuple[list[str], list[str]]:
    """Returns (blocking errors, scene ids to drop from this round).

    A round costs about three minutes regardless of how many frames are in it,
    so all findings belong in one call. Two things are refused: a third round,
    and a reworded query on a scene that was already replaced - the source
    returns the same frame for the same meaning, which is how a quarter of all
    replacements were wasted.
    """
    import difflib

    journal = load_rounds(root)
    done = len([r for r in journal.get("rounds", []) if not r.get("fill")])
    errors: list[str] = []
    drop: list[str] = []
    if done + 1 > ROUND_BUDGET:
        errors.append(f"this is round {done + 1}, budget is {ROUND_BUDGET} - "
                      "borderline frames go to the review card instead")
    for sid, query in fixes.items():
        for previous in journal.get("tried", {}).get(str(sid), []):
            ratio = difflib.SequenceMatcher(None, str(previous).lower(), str(query).lower()).ratio()
            if ratio >= 0.45:
                drop.append(str(sid))
                errors.append(f"scene {sid}: rewording, not a new query ({ratio:.0%} shared) - "
                              "change the object, the shot type or the source")
                break
    return errors, drop


def record_round(root: str | Path, fixes: dict[str, str], fill: bool = False) -> None:
    root = Path(root)
    journal = load_rounds(root)
    journal.setdefault("rounds", []).append(
        {"n": len(journal.get("rounds", [])) + 1, "ids": sorted(fixes), "fill": fill})
    tried = journal.setdefault("tried", {})
    for sid, query in fixes.items():
        tried.setdefault(str(sid), []).append(query)
    (root / ROUNDS_FILE).write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")
