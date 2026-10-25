from __future__ import annotations

import json
import os
import re
from html import unescape
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, headers={"User-Agent": "autonomous-video-assembler/0.1", **(headers or {})})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def search_openverse(query: str, limit: int = 8) -> list[dict]:
    url = "https://api.openverse.org/v1/images/" + "?" + urlencode({"q": query, "page_size": limit})
    data = _get_json(url)
    return [{"thumb": x.get("thumbnail"), "full": x.get("url"), "kind": "photo", "w": x.get("width"), "h": x.get("height"), "src": "openverse", "license": x.get("license"), "creator": x.get("creator")} for x in data.get("results", []) if x.get("url")]


def search_wikimedia(query: str, limit: int = 8) -> list[dict]:
    params = {"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|size", "iiurlwidth": 320, "format": "json", "origin": "*"}
    data = _get_json("https://commons.wikimedia.org/w/api.php?" + urlencode(params))
    results = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("url"):
            results.append({"thumb": info.get("thumburl", info["url"]), "full": info["url"], "kind": "photo", "w": info.get("width"), "h": info.get("height"), "src": "wikimedia"})
    return results


def search_archive(query: str, limit: int = 8) -> list[dict]:
    params = {"q": f"({query}) AND mediatype:(image OR movies)", "fl[]": ["identifier", "title", "mediatype"], "rows": limit, "output": "json"}
    data = _get_json("https://archive.org/advancedsearch.php?" + urlencode(params, doseq=True))
    results = []
    for doc in data.get("response", {}).get("docs", []):
        ident = doc.get("identifier")
        if not ident:
            continue
        kind = "video" if doc.get("mediatype") == "movies" else "photo"
        results.append({"thumb": f"https://archive.org/services/img/{quote(ident)}", "full": f"https://archive.org/details/{quote(ident)}", "kind": kind, "src": "archive"})
    return results


def search_pexels_video(query: str, limit: int = 8) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    data = _get_json("https://api.pexels.com/videos/search?" + urlencode({"query": query, "per_page": limit}), {"Authorization": key})
    results = []
    for item in data.get("videos", []):
        files = sorted(item.get("video_files", []), key=lambda f: (f.get("width") or 0), reverse=True)
        if files:
            results.append({"thumb": item.get("image"), "full": files[0].get("link"), "kind": "video", "w": files[0].get("width"), "h": files[0].get("height"), "src": "pexels"})
    return results


def search_dvids(query: str, limit: int = 8) -> list[dict]:
    data = _get_json("https://www.dvidshub.net/api/search?" + urlencode({"q": query, "page": 1}))
    items = data.get("results", data.get("data", []))
    return [{"thumb": x.get("thumb", x.get("thumbnail")), "full": x.get("url", x.get("link")), "kind": "video" if x.get("type") == "video" else "photo", "src": "dvids"} for x in items[:limit] if x.get("url") or x.get("link")]


def search_flickr(query: str, limit: int = 8) -> list[dict]:
    key = os.environ.get("FLICKR_API_KEY")
    if not key:
        return []
    params = {"method": "flickr.photos.search", "api_key": key, "text": query, "license": "1,2,3,4,5,6,7,8,9,10", "extras": "url_q,url_o,o_dims", "per_page": limit, "format": "json", "nojsoncallback": 1}
    data = _get_json("https://www.flickr.com/services/rest/?" + urlencode(params))
    results = []
    for x in data.get("photos", {}).get("photo", []):
        full = x.get("url_o", x.get("url_q"))
        if full:
            results.append({"thumb": x.get("url_q", full), "full": full, "kind": "photo", "w": x.get("width_o"), "h": x.get("height_o"), "src": "flickr", "license": x.get("license"), "creator": x.get("ownername")})
    return results


def search_web(query: str, limit: int = 8) -> list[dict]:
    """Last-resort discovery only; results are pages, never treated as CC media."""
    data = urlopen(Request("https://html.duckduckgo.com/html/?" + urlencode({"q": query}), headers={"User-Agent": "autonomous-video-assembler/0.1"}), timeout=20).read().decode("utf-8", errors="replace")
    results = []
    for match in re.finditer(r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', data, re.I | re.S):
        url = unescape(match.group(1)); title = re.sub(r"<[^>]+>", "", unescape(match.group(2))).strip()
        if url.startswith("//"): url = "https:" + url
        results.append({"thumb": None, "full": url, "kind": "web", "src": "web_search", "title": title})
        if len(results) >= limit: break
    return results


def search_yandex(query: str, limit: int = 8) -> list[dict]:
    """First web discovery pass; pages are not treated as licensed media."""
    url = "https://yandex.com/search/?" + urlencode({"text": query})
    data = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 autonomous-video-assembler/0.1"}), timeout=20).read().decode("utf-8", errors="replace")
    results = []
    for match in re.finditer(r'href="(https?://[^" ]+)"[^>]*>.*?</a>', data, re.I | re.S):
        link = unescape(match.group(1))
        if "yandex." in link:
            continue
        results.append({"thumb": None, "full": link, "kind": "web", "src": "yandex", "title": link})
        if len(results) >= limit:
            break
    return results


def search_google(query: str, limit: int = 8) -> list[dict]:
    """Second web discovery pass; pages are not treated as licensed media."""
    url = "https://www.google.com/search?" + urlencode({"q": query, "num": limit})
    data = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 autonomous-video-assembler/0.1"}), timeout=20).read().decode("utf-8", errors="replace")
    results = []
    for match in re.finditer(r'<a href="(/url\?q=)?(https?://[^"&]+)[^>]*>', data, re.I):
        link = unescape(match.group(2))
        if "google." in link:
            continue
        results.append({"thumb": None, "full": link, "kind": "web", "src": "google", "title": link})
        if len(results) >= limit:
            break
    return results


def search_sources(query: str, limit: int = 8) -> list[dict]:
    return search_sources_detailed(query, limit)["options"]


def search_sources_detailed(query: str, limit: int = 8) -> dict:
    results: list[dict] = []
    errors: list[dict] = []
    # Editorial waterfall for this project: web discovery first, archive last.
    for source_name, fn in (("yandex", search_yandex), ("google", search_google), ("archive", search_archive)):
        try:
            results.extend(fn(query, limit=max(1, limit - len(results))))
        except Exception as exc:
            errors.append({"source": source_name, "error": str(exc)})
        if len(results) >= limit:
            break
    if len(results) < limit:
        try:
            results.extend(search_pexels_video(query, limit - len(results)))
        except Exception as exc:
            errors.append({"source": "pexels", "error": str(exc)})
    return {"options": results[:limit], "errors": errors}
