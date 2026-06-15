"""
intellidj.slskd — Soulseek/slskd interaction utilities.

Pure functions for building API URLs, retrying HTTP calls with backoff,
fetching search responses, scoring files, and picking the best download.
"""
import os
import random
import time
from typing import Dict, List, Tuple

import requests

from intellidj.spotify import simplify_for_search

DEFAULT_HOST = "http://localhost:5030"
DEFAULT_URL_BASE = "/api/v0"
DEFAULT_RETRIES = int(os.getenv("SLSKD_RETRY_ATTEMPTS", "3"))
DEFAULT_RETRY_BACKOFF = float(os.getenv("SLSKD_RETRY_BACKOFF", "0.5"))
DEFAULT_RETRY_MAX_DELAY = float(os.getenv("SLSKD_RETRY_MAX_DELAY", "8"))


def build_api_base(host: str) -> str:
    base = host.rstrip("/")
    if base.endswith("/api/v0"):
        base = base[: -len("/api/v0")]
    return base


def _should_retry_http(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        status = response.status_code if response is not None else None
        if status is None:
            return True
        if status in (408, 409, 429):
            return True
        return 500 <= status < 600
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    return True


def retry_with_backoff(
    func,
    *,
    label: str,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_RETRY_BACKOFF,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    should_retry=_should_retry_http,
):
    attempt = 0
    while True:
        try:
            return func()
        except Exception as exc:
            if attempt >= retries or (should_retry and not should_retry(exc)):
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay += random.uniform(0, base_delay)
            print(f"[warn] {label} failed ({exc}); retrying in {delay:.1f}s")
            time.sleep(delay)
            attempt += 1


def fetch_search_responses(base_url: str, api_key: str, search_id: str) -> List[Dict]:
    url = f"{base_url}/api/v0/searches/{search_id}/responses"
    headers = {"X-API-KEY": api_key}
    r = retry_with_backoff(
        lambda: requests.get(url, headers=headers, timeout=10),
        label="requests.get search_responses",
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def _normalize_for_match(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy comparison."""
    import re as _re
    text = text.lower()
    text = _re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def relevance_score(filename: str, query: str) -> int:
    """Score how well a filename matches the search query (0-100).

    Returns 0 if the file is clearly irrelevant (missing artist or track words).
    """
    fn = _normalize_for_match(filename)
    q = _normalize_for_match(query)

    query_words = q.split()
    if not query_words:
        return 0

    matched = sum(1 for w in query_words if w in fn)
    ratio = matched / len(query_words)

    # Require at least half the query words to be present
    if ratio < 0.5:
        return 0

    return int(ratio * 100)


AUDIO_EXTENSIONS = frozenset({"flac", "mp3", "wav", "aac", "ogg", "m4a", "wma", "aiff", "alac", "opus"})


def score_file(file_info: Dict, query: str = "") -> Tuple[int, int, int]:
    """Score a file by (relevance, format_quality, size).

    When query is provided, files that don't match get relevance=0 and are
    effectively filtered out by pick_best_file.
    """
    name = str(file_info.get("filename", "")).lower()
    ext = str(file_info.get("extension", "")).lower()
    size = int(file_info.get("size") or 0)

    # Filter out non-audio files
    file_ext = ext or name.rsplit(".", 1)[-1] if "." in name else ""
    if file_ext not in AUDIO_EXTENSIONS:
        return 0, 0, 0

    # Relevance score (0-100)
    rel = relevance_score(name, query) if query else 50

    # Format quality score
    fmt = 0
    if name.endswith(".flac") or ext == "flac":
        fmt += 100
    if "flac" in name:
        fmt += 20
    if name.endswith(".mp3") or ext == "mp3":
        fmt += 5
    if "320" in name:
        fmt += 10

    return rel, fmt, size


def normalize_responses(raw) -> List[Dict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "responses" in raw and isinstance(raw["responses"], list):
            return raw["responses"]
        if "items" in raw and isinstance(raw["items"], list):
            return raw["items"]
    return []


def iter_files(response: Dict) -> List[Dict]:
    for key in ("files", "fileInfos", "results", "file_results"):
        files = response.get(key)
        if isinstance(files, list):
            return files
    return []


def pick_best_file(responses: List[Dict], query: str = "") -> Tuple[str, Dict] | Tuple[None, None]:
    best_user = None
    best_file = None
    best_score = (-1, -1, -1)

    for response in responses:
        username = response.get("username")
        files = iter_files(response)
        for f in files:
            score = score_file(f, query)
            # Skip files with zero relevance (irrelevant to the query)
            if query and score[0] == 0:
                continue
            if score > best_score:
                best_score = score
                best_user = username
                best_file = f

    if not best_user or not best_file:
        return None, None

    return best_user, best_file


def build_search_queries(query: str) -> List[str]:
    """Build a list of search queries from most specific to most general.

    Returns up to 3 variants:
    1. The original query as-is
    2. Simplified query (remix/version/feat stripped) if different from original
    3. Artist-only query as last resort
    """
    queries = [query]

    # Extract artist and track parts
    parts = query.split(" - ", 1)
    artist = parts[0].strip()
    track = parts[1].strip() if len(parts) > 1 else ""

    if track:
        simplified_track = simplify_for_search(track)
        simplified = f"{artist} {simplified_track}"
        if simplified.lower() != query.lower():
            queries.append(simplified)

        # Artist-only fallback (only if there's a track to drop)
        if len(artist.split()) >= 2:
            queries.append(artist)

    return queries


def parse_search_string(query: str) -> Tuple[str | None, str | None]:
    if " - " not in query:
        return None, query.strip() or None
    artist, title = query.split(" - ", 1)
    artist = artist.strip() or None
    title = title.strip() or None
    return artist, title
