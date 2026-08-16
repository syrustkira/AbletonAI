from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from n0te_network import NetworkPolicy


def _http_json(url: str, headers: dict[str, str] | None = None, timeout: float = 12.0,
               network_policy: NetworkPolicy | None = None) -> dict[str, Any]:
    (network_policy or NetworkPolicy()).require(url)
    req = urllib.request.Request(url, headers={"User-Agent": "N0TE-Ableton-AI/1.2", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            value = json.loads(resp.read().decode("utf-8"))
            return value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}")


def _contains(query: str, *parts: Any) -> bool:
    q = [x for x in query.lower().split() if x]
    hay = " ".join(str(p or "") for p in parts).lower()
    return bool(q) and all(term in hay for term in q)


def current_set_audio(snapshot: dict[str, Any], query: str, limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = [snapshot.get("set", {}).get("tracks") or [], snapshot.get("set", {}).get("return_tracks") or []]
    master = snapshot.get("set", {}).get("master_track")
    if isinstance(master, dict):
        groups.append([master])
    for tracks in groups:
        for track in tracks:
            if not isinstance(track, dict):
                continue
            clips = (track.get("clips") or []) + (track.get("arrangement_clips") or [])
            for clip in clips:
                if not isinstance(clip, dict):
                    continue
                name = str(clip.get("name") or "")
                file_path = str(clip.get("file_path") or "")
                if query and not _contains(query, name, file_path, track.get("name")):
                    continue
                if not file_path and not name:
                    continue
                rows.append({
                    "source": "current_set",
                    "title": name or os.path.basename(file_path),
                    "track": track.get("name"),
                    "path": file_path,
                    "local": True,
                    "license": "project_asset",
                    "downloadable": False,
                })
                if len(rows) >= limit:
                    return rows
    return rows


def search_live_browser(bridge, query: str, limit: int = 24) -> dict[str, Any]:
    roots = []
    errors = []
    try:
        raw_roots = bridge.request("browser_roots", {"timeout": 4}) or []
        root_names = [str(x.get("name") or "") for x in raw_roots if isinstance(x, dict)]
    except Exception as exc:
        root_names = []
        errors.append(str(exc))
    preferred_terms = ("sample", "sound", "clip", "user", "pack", "project", "splice")
    preferred = [name for name in root_names if any(term in name.lower() for term in preferred_terms)]
    roots = preferred or root_names
    if not roots:
        # The pinned bridge currently supports these roots on recent Live versions; unsupported roots are ignored/fail closed.
        roots = ["samples", "sounds", "clips", "user_library", "packs", "user_folders"]
    try:
        result = bridge.request("browser_search", {
            "query": query,
            "roots": roots,
            "limit": limit,
            "max_depth": 12,
            "max_visited": 18000,
            "loadable_only": True,
            "include_folders": False,
            "stop_on_limit": True,
            "match_all_terms": False,
            "timeout": 18,
        }) or {}
        rows = []
        for item in result.get("results") or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                "source": "ableton_browser",
                "title": item.get("name") or "Untitled",
                "path": item.get("path") or item.get("uri") or "",
                "root": item.get("root") or item.get("scan_root") or "",
                "local": True,
                "license": "already_owned_or_available_in_live",
                "downloadable": False,
                "raw": item,
            })
        return {"results": rows, "roots": roots, "truncated": bool(result.get("truncated")), "errors": errors}
    except Exception as exc:
        errors.append(str(exc))
        return {"results": [], "roots": roots, "truncated": False, "errors": errors}


def search_openverse(query: str, limit: int = 12, token: str = "", license_filter: str = "",
                     network_policy: NetworkPolicy | None = None) -> dict[str, Any]:
    params = {"q": query, "page_size": str(max(1, min(limit, 20))), "mature": "false"}
    if license_filter:
        params["license"] = license_filter
    url = "https://api.openverse.org/v1/audio/?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        data = _http_json(url, headers=headers, network_policy=network_policy)
    except Exception as exc:
        return {"results": [], "error": str(exc), "source": "openverse"}
    rows = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        alt_files = item.get("alt_files") or []
        preview = ""
        if isinstance(alt_files, list):
            for alt in alt_files:
                if isinstance(alt, dict) and alt.get("url"):
                    preview = str(alt.get("url"))
                    if "mp3" in str(alt.get("filetype") or "").lower():
                        break
        rows.append({
            "source": "openverse",
            "id": item.get("id"),
            "title": item.get("title") or "Untitled",
            "creator": item.get("creator") or "",
            "license": item.get("license") or "unknown",
            "license_url": item.get("license_url") or "",
            "attribution": item.get("attribution") or "",
            "landing_url": item.get("foreign_landing_url") or item.get("detail_url") or "",
            "audio_url": item.get("url") or "",
            "preview_url": preview or item.get("url") or "",
            "duration": item.get("duration"),
            "filetype": item.get("filetype") or "",
            "sample_rate": item.get("sample_rate"),
            "provider": item.get("provider") or "",
            "local": False,
            "downloadable": bool(item.get("url")),
        })
    return {"results": rows, "source": "openverse", "error": ""}


def search_freesound(query: str, api_key: str, limit: int = 12,
                     network_policy: NetworkPolicy | None = None) -> dict[str, Any]:
    if not api_key:
        return {"results": [], "source": "freesound", "error": "Freesound API key not configured"}
    fields = "id,name,tags,username,license,previews,duration,type,samplerate,url,download"
    params = {
        "query": query,
        "page_size": str(max(1, min(limit, 30))),
        "fields": fields,
    }
    # Current APIv2 search endpoint; the older /search/text endpoint was deprecated in 2025.
    url = "https://freesound.org/apiv2/search/?" + urllib.parse.urlencode(params)
    try:
        data = _http_json(url, headers={"Authorization": f"Token {api_key}"}, network_policy=network_policy)
    except Exception as exc:
        return {"results": [], "source": "freesound", "error": str(exc)}
    rows = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        previews = item.get("previews") or {}
        preview = ""
        if isinstance(previews, dict):
            for key in ("preview-hq-mp3", "preview-lq-mp3", "preview-hq-ogg", "preview-lq-ogg"):
                if previews.get(key):
                    preview = str(previews[key])
                    break
        rows.append({
            "source": "freesound",
            "id": item.get("id"),
            "title": item.get("name") or "Untitled",
            "creator": item.get("username") or "",
            "license": item.get("license") or "unknown",
            "license_url": item.get("license") or "",
            "landing_url": item.get("url") or "",
            "preview_url": preview,
            "duration": item.get("duration"),
            "filetype": item.get("type") or "",
            "sample_rate": item.get("samplerate"),
            "tags": item.get("tags") or [],
            "local": False,
            # Original download typically needs OAuth2 even when search/previews use an API token.
            "downloadable": False,
        })
    return {"results": rows, "source": "freesound", "error": ""}


def general_web_search_urls(query: str) -> list[dict[str, str]]:
    # Broad-web discovery is intentionally click-through only: licensing/anti-bot/paywall rules vary by site.
    phrases = [
        query + " royalty free sample wav",
        query + " CC0 audio sample",
    ]
    return [
        {
            "source": "web_discovery",
            "title": phrase,
            "landing_url": "https://www.google.com/search?" + urllib.parse.urlencode({"q": phrase}),
            "license": "verify_on_source_page",
        }
        for phrase in phrases
    ]




def extract_discovery_intent(text: str) -> dict[str, Any]:
    """Normalize conversational discovery language into a search-oriented query.

    This is intentionally deterministic and conservative. It removes command filler
    ("find me", "search for") and extracts a small set of negative constraints so
    Browser searches do not waste tokens matching words like "find" and "me".
    """
    raw = " ".join(str(text or "").strip().split())
    value = raw
    include_web_hint = bool(re.search(r"\b(web|online|internet|outside ableton|search everywhere)\b", value, re.I))
    value = re.sub(r"^(?:can you\s+|please\s+)?(?:find|search(?: for)?|look for|show me|give me)\s+(?:me\s+)?", "", value, flags=re.I)
    value = re.sub(r"^(?:i\s+)?need\s+(?:me\s+)?(?:an?\s+|some\s+)?", "", value, flags=re.I)
    value = re.sub(r"\b(?:search )?(?:the )?(?:web|internet|online)(?: too| as well)?\b", "", value, flags=re.I)
    value = re.sub(r"\b(?:from|on)\s+(?:the )?(?:web|internet|online)\b", "", value, flags=re.I)

    negatives: list[str] = []
    neg_patterns = [
        r"(?:that\s+)?isn['’]?t\s+(?:too\s+)?([^,.;]+)$",
        r"(?:but\s+)?not\s+([^,.;]+)$",
        r"without\s+([^,.;]+)$",
    ]
    for pattern in neg_patterns:
        match = re.search(pattern, value, flags=re.I)
        if match:
            phrase = match.group(1).strip()
            if phrase:
                negatives.append(phrase)
            value = value[:match.start()].strip()
            break

    value = re.sub(r"\b(?:that|which)\s+(?:fits|works with)\s+(?:this|the)\s+(?:song|section|chorus|verse|track)\b.*$", "", value, flags=re.I).strip()
    value = re.sub(r"\s+", " ", value).strip(" ,.-")
    if not value:
        value = raw
    return {"raw": raw, "query": value, "negative_terms": negatives, "include_web_hint": include_web_hint}


def _filter_negative(rows: list[dict[str, Any]], negative_terms: list[str]) -> list[dict[str, Any]]:
    if not negative_terms:
        return rows
    negatives = [term.lower().strip() for term in negative_terms if term.strip()]
    out = []
    for row in rows:
        hay = " ".join(str(row.get(k) or "") for k in ("title", "path", "tags", "creator")).lower()
        if any(term in hay for term in negatives):
            continue
        out.append(row)
    return out

def discover(query: str, bridge, library, snapshot: dict[str, Any], *, include_web: bool = True,
             openverse_token: str = "", freesound_key: str = "", web_threshold: int = 6,
             license_filter: str = "", network_policy: NetworkPolicy | None = None) -> dict[str, Any]:
    intent = extract_discovery_intent(query)
    normalized = str(intent.get("query") or "").strip()
    negatives = [str(x) for x in intent.get("negative_terms") or []]
    if not normalized:
        raise RuntimeError("Discovery query is empty")

    current = _filter_negative(current_set_audio(snapshot, normalized), negatives)
    browser = search_live_browser(bridge, normalized)
    browser["results"] = _filter_negative(browser.get("results") or [], negatives)
    cached = []
    try:
        for item in library.search(normalized, limit=20):
            cached.append({
                "source": "n0te_library_cache",
                "title": item.get("name") or "Untitled",
                "path": item.get("path") or item.get("uri") or "",
                "kind": item.get("kind") or "",
                "local": True,
                "license": "already_owned_or_available_in_live",
                "downloadable": False,
            })
    except Exception:
        pass
    cached = _filter_negative(cached, negatives)

    local_count = len(current) + len(browser.get("results") or []) + len(cached)
    openverse = {"results": [], "error": "", "source": "openverse"}
    freesound = {"results": [], "error": "", "source": "freesound"}
    broad = []
    web_requested = bool(include_web or intent.get("include_web_hint"))
    if web_requested and local_count < web_threshold:
        openverse = search_openverse(normalized, limit=12, token=openverse_token, license_filter=license_filter,
                                     network_policy=network_policy)
        openverse["results"] = _filter_negative(openverse.get("results") or [], negatives)
        freesound = search_freesound(normalized, freesound_key, limit=12, network_policy=network_policy)
        freesound["results"] = _filter_negative(freesound.get("results") or [], negatives)
        if not openverse.get("results") and not freesound.get("results"):
            broad = general_web_search_urls(normalized)

    return {
        "raw_query": str(query or "").strip(),
        "query": normalized,
        "negative_terms": negatives,
        "search_order": ["current set", "Ableton Browser", "N0TE local cache", "Openverse", "Freesound", "general web click-through"],
        "fallback_triggered": bool(web_requested and local_count < web_threshold),
        "local_count": local_count,
        "current_set": current,
        "ableton_browser": browser,
        "local_cache": cached,
        "openverse": openverse,
        "freesound": freesound,
        "web_discovery": broad,
    }
