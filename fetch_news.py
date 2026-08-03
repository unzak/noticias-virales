"""Genera un ranking editorial de contenidos con potencial viral en España.

Fuentes sin clave:
- Google News España y búsquedas temáticas (RSS)
- Menéame (RSS)
- Google Trends España (RSS)
- Bluesky (API pública)
- Mastodon (endpoints públicos de tendencias)

Fuentes opcionales mediante secretos de GitHub:
- Reddit Data API (REDDIT_CLIENT_ID y REDDIT_CLIENT_SECRET)
- YouTube Data API (YOUTUBE_API_KEY)
- X Trends API (X_BEARER_TOKEN; servicio de pago por uso)

El ranking es una heurística editorial. Combina interacción observable,
velocidad, recencia, presencia en varias plataformas, coincidencia con
Google/X Trends y afinidad con formatos de entretenimiento. No predice ni
garantiza likes futuros.
"""

from __future__ import annotations

import base64
import calendar
import datetime as dt
import html
import json
import math
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import feedparser

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "docs" / "data.json"

GOOGLE_NEWS_BASE = "https://news.google.com/rss"
GOOGLE_NEWS_PARAMS = "hl=es&gl=ES&ceid=ES:es"
NEWS_SOURCES = (
    ("Google News España", f"{GOOGLE_NEWS_BASE}?{GOOGLE_NEWS_PARAMS}"),
    (
        "Google News · viral y curiosidades",
        f"{GOOGLE_NEWS_BASE}/search?{urllib.parse.urlencode({'q': 'viral OR insólito OR curioso OR redes sociales'})}&{GOOGLE_NEWS_PARAMS}",
    ),
    (
        "Google News · entretenimiento",
        f"{GOOGLE_NEWS_BASE}/search?{urllib.parse.urlencode({'q': 'televisión OR famosos OR reality OR vídeo viral'})}&{GOOGLE_NEWS_PARAMS}",
    ),
    (
        "Google News · animales e historias",
        f"{GOOGLE_NEWS_BASE}/search?{urllib.parse.urlencode({'q': 'animales OR mascotas OR historia viral'})}&{GOOGLE_NEWS_PARAMS}",
    ),
    ("Menéame", "https://www.meneame.net/rss"),
)
GOOGLE_TRENDS_URL = "https://trends.google.com/trending/rss?geo=ES"
BLUESKY_SEARCH_URL = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
X_TRENDS_URL = "https://api.x.com/2/trends/by/woeid/23424950"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

DEFAULT_MASTODON_INSTANCES = ("https://masto.es", "https://mastodon.social")
DEFAULT_REDDIT_ES = (
    "spain",
    "Espana",
    "es",
    "askspain",
    "yo_elvr",
    "MemesEnEspanol",
    "HistoriasDeReddit",
    "Asi_va_Espana",
)
DEFAULT_REDDIT_GLOBAL = (
    "Unexpected",
    "AnimalsBeingDerps",
    "ContagiousLaughter",
    "MadeMeSmile",
)

USER_AGENT = os.getenv(
    "PULSO_USER_AGENT",
    "PulsoNoticias/2.0 (+https://github.com/unzak/noticias-virales)",
)
HTTP_TIMEOUT_SECONDS = 25
NEWS_MAX_AGE_HOURS = 72
SOCIAL_MAX_AGE_HOURS = 48
YOUTUBE_MAX_AGE_HOURS = 14 * 24
MAX_STORIES = 60

STOPWORDS = set(
    """de la el en y a los que del las un por con no una su para es al lo
    como mas pero sus le ya o este si porque esta entre cuando muy sin
    sobre tambien me hasta hay donde quien desde todo nos durante todos
    uno les ni contra otros ese eso ante ellos e esto mi antes algunos
    unos yo otro otras otra tanto esa estos mucho quienes nada muchos
    cual poco ella estar estas algunas algo nosotros mis tu tus ellas
    nosotras vosotros vosotras os mio mia mios mias tuyo tuya tuyos
    tuyas suyo suya suyos suyas nuestro nuestra nuestros nuestras
    vuestro vuestra vuestros vuestras esos esas tras dice dijo segun
    ultima ultimo ultimas ultimos hoy directo minuto minutos espana
    espanol espanola noticia noticias viral virales video videos meme
    memes reddit bluesky mastodon youtube twitter facebook ahora aqui
    asi solo puede hace hacen nuevo nueva nuevos nuevas parte ver""".split()
)

VIRAL_TERMS = (
    "animal",
    "animales",
    "perro",
    "gato",
    "mascota",
    "reaccion",
    "sorpresa",
    "insolito",
    "curioso",
    "curiosidad",
    "increible",
    "divertido",
    "humor",
    "broma",
    "meme",
    "television",
    "reality",
    "famoso",
    "famosa",
    "celebridad",
    "futbol",
    "deporte",
    "comida",
    "viaje",
    "tecnologia",
    "truco",
    "historia",
    "anecdota",
    "fail",
    "reto",
)
POLITICS_TERMS = (
    "gobierno",
    "ministro",
    "ministra",
    "congreso",
    "senado",
    "elecciones",
    "partido politico",
    "sanchez",
    "abascal",
    "feijoo",
    "podemos",
    "vox",
    "psoe",
    "pp ",
)
HARD_NEWS_TERMS = (
    "guerra",
    "ataque",
    "bombardeo",
    "asesinato",
    "muere",
    "muerte",
    "fallece",
    "accidente",
    "incendio",
    "violencia",
    "tribunal",
    "detenido",
    "detenida",
    "crisis",
)
BLOCKED_TERMS = (
    "pornografia",
    "porno ",
    "nsfw",
    "violacion",
    "suicidio",
    "se suicida",
    "pedofilia",
    "cadaver",
    "decapitado",
    "decapitada",
    "gore",
    "contenido grafico",
)
GENERIC_REDDIT_TITLES = {
    "yo elvr",
    "meme",
    "memes",
    "titulo",
    "sin titulo",
    "xd",
    "jajaja",
    "jajajaja",
}
PLATFORM_LABELS = {
    "news": "Medios",
    "reddit": "Reddit",
    "bluesky": "Bluesky",
    "mastodon": "Mastodon",
    "youtube": "YouTube",
}


@dataclass(frozen=True)
class StoryEntry:
    title: str
    link: str
    source: str
    platform: str
    published_at: dt.datetime | None
    keywords: frozenset[str]
    social_points: float = 0.0
    metrics: dict[str, int | float | str] = field(default_factory=dict)
    thumbnail: str | None = None
    media_type: str = "article"
    seed_trend: str | None = None


def env_list(name: str, default: Iterable[str]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return tuple(default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
) -> bytes:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        headers=request_headers,
        data=data,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read()


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
) -> Any:
    payload = fetch_bytes(url, headers=headers, data=data, method=method)
    return json.loads(payload.decode("utf-8"))


def fetch_feed(url: str) -> Any:
    return feedparser.parse(fetch_bytes(url))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def keywords(text: str) -> frozenset[str]:
    return frozenset(
        word for word in normalize(text).split() if len(word) > 3 and word not in STOPWORDS
    )


def contains_phrase(text: str, phrases: Iterable[str]) -> int:
    normalized = f" {normalize(text)} "
    return sum(1 for phrase in phrases if f" {normalize(phrase)} " in normalized)


def is_blocked_content(text: str) -> bool:
    return contains_phrase(text, BLOCKED_TERMS) > 0


def valid_http_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = html.unescape(value.strip())
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def parse_iso_datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return None


def parse_published(entry: Any) -> dt.datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            timestamp = calendar.timegm(parsed)
            return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
        except (OverflowError, TypeError, ValueError):
            pass
    return parse_iso_datetime(entry.get("published") or entry.get("updated"))


def strip_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def compact_text(value: str, limit: int = 190) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0].strip()
    return f"{shortened}…"


def parse_human_count(value: Any) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if not isinstance(value, str):
        return 0
    match = re.search(r"([\d.,]+)\s*([kmb]?)", value.lower().replace("+", ""))
    if not match:
        return 0
    number = match.group(1)
    suffix = match.group(2)
    if number.count(",") == 1 and "." not in number:
        left, right = number.split(",")
        number = f"{left}.{right}" if len(right) <= 2 else f"{left}{right}"
    else:
        number = number.replace(",", "")
    try:
        numeric = float(number)
    except ValueError:
        return 0
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
    return max(0, int(numeric * multiplier))


def age_hours(published_at: dt.datetime | None, now: dt.datetime) -> float:
    if not published_at:
        return 24.0
    return max(0.0, (now - published_at).total_seconds() / 3600)


def velocity_bonus(total: float, published_at: dt.datetime | None, now: dt.datetime) -> float:
    hours = max(1.0, age_hours(published_at, now))
    per_hour = max(0.0, total) / hours
    return min(15.0, math.log10(per_hour + 1.0) * 8.0)


def reddit_social_points(score: int, comments: int, published_at: dt.datetime | None) -> float:
    now = dt.datetime.now(dt.timezone.utc)
    weighted = score + comments * 3
    points = math.log10(score + 1) * 9 + math.log10(comments + 1) * 7
    points += velocity_bonus(weighted, published_at, now)
    return min(58.0, points)


def bluesky_social_points(
    likes: int,
    reposts: int,
    replies: int,
    quotes: int,
    published_at: dt.datetime | None,
) -> float:
    now = dt.datetime.now(dt.timezone.utc)
    weighted = likes + reposts * 3 + replies * 2 + quotes * 3
    points = math.log10(weighted + 1) * 15 + velocity_bonus(weighted, published_at, now)
    return min(52.0, points)


def mastodon_social_points(
    favourites: int,
    boosts: int,
    replies: int,
    published_at: dt.datetime | None,
) -> float:
    now = dt.datetime.now(dt.timezone.utc)
    weighted = favourites + boosts * 3 + replies * 2
    points = math.log10(weighted + 1) * 14 + velocity_bonus(weighted, published_at, now)
    return min(48.0, points)


def youtube_social_points(
    views: int,
    likes: int,
    comments: int,
    published_at: dt.datetime | None,
) -> float:
    now = dt.datetime.now(dt.timezone.utc)
    engagement = likes + comments * 4
    points = math.log10(views + 1) * 4.5 + math.log10(engagement + 1) * 8
    points += velocity_bonus(views, published_at, now)
    return min(65.0, points)


def extract_feed_thumbnail(entry: Any) -> str | None:
    for field_name in ("media_thumbnail", "media_content"):
        media = entry.get(field_name)
        if isinstance(media, list):
            for item in reversed(media):
                if isinstance(item, dict):
                    candidate = valid_http_url(item.get("url"))
                    if candidate:
                        return candidate
    enclosure = entry.get("enclosures")
    if isinstance(enclosure, list):
        for item in enclosure:
            if isinstance(item, dict) and str(item.get("type", "")).startswith("image/"):
                candidate = valid_http_url(item.get("href") or item.get("url"))
                if candidate:
                    return candidate
    return None


def clean_google_title(title: str, publisher: str | None) -> str:
    if publisher:
        suffix = f" - {publisher}"
        if title.endswith(suffix):
            return title[: -len(suffix)].strip()
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2 and 1 < len(parts[1].split()) <= 8:
        return parts[0].strip()
    return title.strip()


def extract_publisher(entry: Any, fallback: str) -> str:
    source = entry.get("source")
    if isinstance(source, dict):
        title = str(source.get("title", "")).strip()
        if title:
            return title
    if hasattr(source, "get"):
        title = str(source.get("title", "")).strip()
        if title:
            return title
    raw_title = str(entry.get("title", "")).strip()
    if fallback.startswith("Google News") and " - " in raw_title:
        possible = raw_title.rsplit(" - ", 1)[1].strip()
        if possible:
            return possible
    return fallback


def fetch_news_entries() -> tuple[list[StoryEntry], list[str], list[dict[str, Any]]]:
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=NEWS_MAX_AGE_HOURS)
    seen: set[tuple[str, str]] = set()

    for fallback_source, url in NEWS_SOURCES:
        try:
            feed = fetch_feed(url)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            warnings.append(f"No se pudo descargar {fallback_source}: {exc}")
            statuses.append({"name": fallback_source, "ok": False, "items": 0})
            continue

        if getattr(feed, "bozo", False):
            warnings.append(
                f"{fallback_source} devolvió un RSS con advertencias: "
                f"{getattr(feed, 'bozo_exception', 'formato no válido')}"
            )

        accepted = 0
        for raw in feed.entries:
            raw_title = str(raw.get("title", "")).strip()
            link = valid_http_url(raw.get("link"))
            if not raw_title or not link:
                continue

            source = extract_publisher(raw, fallback_source)
            title = clean_google_title(raw_title, source) if fallback_source.startswith("Google News") else raw_title
            if is_blocked_content(title):
                continue
            title_keywords = keywords(title)
            if not title_keywords:
                continue

            published_at = parse_published(raw)
            if published_at and published_at < cutoff:
                continue

            dedupe_key = (normalize(title), source.casefold())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            entries.append(
                StoryEntry(
                    title=compact_text(title, 220),
                    link=link,
                    source=source,
                    platform="news",
                    published_at=published_at,
                    keywords=title_keywords,
                    thumbnail=extract_feed_thumbnail(raw),
                    media_type="article",
                )
            )
            accepted += 1

        statuses.append({"name": fallback_source, "ok": True, "items": accepted})
        print(f"[ok] {fallback_source}: {accepted} elementos")

    return entries, warnings, statuses


def get_google_trends() -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    try:
        feed = fetch_feed(GOOGLE_TRENDS_URL)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return [], [f"No se pudo descargar Google Trends: {exc}"], {
            "name": "Google Trends España",
            "ok": False,
            "items": 0,
        }

    if getattr(feed, "bozo", False):
        warnings.append(
            "Google Trends devolvió un RSS con advertencias: "
            f"{getattr(feed, 'bozo_exception', 'formato no válido')}"
        )

    trends: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in feed.entries:
        title = str(entry.get("title", "")).strip()
        normalized = normalize(title)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        traffic_raw = entry.get("ht_approx_traffic") or entry.get("approx_traffic") or ""
        trends.append(
            {
                "name": title,
                "traffic": parse_human_count(traffic_raw),
                "traffic_label": str(traffic_raw).strip() or None,
            }
        )
    trends = trends[:30]
    print(f"[ok] Google Trends: {len(trends)} tendencias")
    return trends, warnings, {"name": "Google Trends España", "ok": True, "items": len(trends)}


def get_x_trends() -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    token = os.getenv("X_BEARER_TOKEN", "").strip()
    if not token:
        return [], [], {
            "name": "X Trends España",
            "ok": None,
            "items": 0,
            "note": "No configurado",
        }
    params = urllib.parse.urlencode(
        {"max_trends": 30, "trend.fields": "trend_name,tweet_count"}
    )
    try:
        payload = fetch_json(
            f"{X_TRENDS_URL}?{params}",
            headers={"Authorization": f"Bearer {token}"},
        )
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return [], [f"No se pudo consultar X Trends: {exc}"], {
            "name": "X Trends España",
            "ok": False,
            "items": 0,
        }

    trends: list[dict[str, Any]] = []
    for item in payload.get("data", []) if isinstance(payload, dict) else []:
        name = str(item.get("trend_name", "")).strip()
        if not name:
            continue
        trends.append({"name": name, "tweet_count": parse_human_count(item.get("tweet_count"))})
    print(f"[ok] X Trends: {len(trends)} tendencias")
    return trends, [], {"name": "X Trends España", "ok": True, "items": len(trends)}


def reddit_access_token() -> str | None:
    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    payload = fetch_json(
        "https://www.reddit.com/api/v1/access_token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": os.getenv("REDDIT_USER_AGENT", "").strip() or USER_AGENT,
        },
        data=body,
        method="POST",
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    return str(token).strip() if token else None


def reddit_thumbnail(data: dict[str, Any]) -> str | None:
    preview = data.get("preview")
    if isinstance(preview, dict):
        images = preview.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                resolutions = first.get("resolutions")
                if isinstance(resolutions, list):
                    for resolution in reversed(resolutions):
                        if isinstance(resolution, dict):
                            candidate = valid_http_url(resolution.get("url"))
                            if candidate:
                                return candidate
                source = first.get("source")
                if isinstance(source, dict):
                    candidate = valid_http_url(source.get("url"))
                    if candidate:
                        return candidate
    thumbnail = valid_http_url(data.get("thumbnail"))
    if thumbnail and not thumbnail.endswith("default.png"):
        return thumbnail
    return None


def reddit_media_type(data: dict[str, Any]) -> str:
    if data.get("is_video"):
        return "video"
    post_hint = str(data.get("post_hint", ""))
    if post_hint in {"image", "hosted:video", "rich:video"}:
        return "video" if "video" in post_hint else "image"
    url = str(data.get("url_overridden_by_dest") or data.get("url") or "").lower()
    if re.search(r"\.(jpg|jpeg|png|gif|webp)(\?|$)", url):
        return "image"
    if re.search(r"\.(mp4|webm)(\?|$)", url):
        return "video"
    return "text" if data.get("is_self") else "link"


def fetch_reddit_group(
    token: str,
    subreddits: tuple[str, ...],
    label: str,
) -> tuple[list[StoryEntry], list[str], dict[str, Any]]:
    if not subreddits:
        return [], [], {"name": label, "ok": True, "items": 0}
    listing = "+".join(urllib.parse.quote(item, safe="") for item in subreddits)
    url = f"https://oauth.reddit.com/r/{listing}/hot?limit=100&raw_json=1"
    try:
        payload = fetch_json(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": os.getenv("REDDIT_USER_AGENT", "").strip() or USER_AGENT,
            },
        )
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return [], [f"No se pudo consultar {label}: {exc}"], {
            "name": label,
            "ok": False,
            "items": 0,
        }

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=SOCIAL_MAX_AGE_HOURS)
    entries: list[StoryEntry] = []
    children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
    for child in children:
        data = child.get("data", {}) if isinstance(child, dict) else {}
        if not isinstance(data, dict):
            continue
        if data.get("over_18") or data.get("stickied") or data.get("removed_by_category"):
            continue
        title = str(data.get("title", "")).strip()
        if not title or is_blocked_content(title):
            continue
        published_at = dt.datetime.fromtimestamp(float(data.get("created_utc", 0)), tz=dt.timezone.utc)
        if published_at < cutoff:
            continue
        score = max(0, int(data.get("score") or 0))
        comments = max(0, int(data.get("num_comments") or 0))
        if score < 15 and comments < 8:
            continue
        subreddit = str(data.get("subreddit", "reddit")).strip()
        permalink = str(data.get("permalink", "")).strip()
        link = valid_http_url(f"https://www.reddit.com{permalink}")
        if not link:
            continue
        normalized_title = normalize(title)
        if normalized_title in GENERIC_REDDIT_TITLES or normalized_title.startswith("yo elvr"):
            title = f"Meme destacado en r/{subreddit}"
        media_type = reddit_media_type(data)
        metrics: dict[str, int | float | str] = {
            "upvotes": score,
            "comments": comments,
            "upvote_ratio": float(data.get("upvote_ratio") or 0),
            "subreddit": subreddit,
        }
        entries.append(
            StoryEntry(
                title=compact_text(title, 220),
                link=link,
                source=f"Reddit r/{subreddit}",
                platform="reddit",
                published_at=published_at,
                keywords=keywords(title),
                social_points=reddit_social_points(score, comments, published_at),
                metrics=metrics,
                thumbnail=reddit_thumbnail(data),
                media_type=media_type,
            )
        )
    print(f"[ok] {label}: {len(entries)} publicaciones")
    return entries, [], {"name": label, "ok": True, "items": len(entries)}


def fetch_reddit_entries() -> tuple[list[StoryEntry], list[str], list[dict[str, Any]]]:
    try:
        token = reddit_access_token()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return [], [f"No se pudo autenticar Reddit: {exc}"], [
            {"name": "Reddit", "ok": False, "items": 0}
        ]
    if not token:
        return [], [], [
            {
                "name": "Reddit",
                "ok": None,
                "items": 0,
                "note": "Añade REDDIT_CLIENT_ID y REDDIT_CLIENT_SECRET",
            }
        ]

    groups = (
        (env_list("REDDIT_SUBREDDITS_ES", DEFAULT_REDDIT_ES), "Reddit España"),
        (env_list("REDDIT_SUBREDDITS_GLOBAL", DEFAULT_REDDIT_GLOBAL), "Reddit visual global"),
    )
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    for subreddits, label in groups:
        group_entries, group_warnings, status = fetch_reddit_group(token, subreddits, label)
        entries.extend(group_entries)
        warnings.extend(group_warnings)
        statuses.append(status)
    return entries, warnings, statuses


def bluesky_thumbnail(embed: Any) -> tuple[str | None, str]:
    if not isinstance(embed, dict):
        return None, "text"
    embed_type = str(embed.get("$type", ""))
    if "recordWithMedia" in embed_type:
        return bluesky_thumbnail(embed.get("media"))
    if "images" in embed_type:
        images = embed.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                return valid_http_url(first.get("thumb") or first.get("fullsize")), "image"
        return None, "image"
    if "video" in embed_type:
        return valid_http_url(embed.get("thumbnail")), "video"
    if "external" in embed_type:
        external = embed.get("external")
        if isinstance(external, dict):
            return valid_http_url(external.get("thumb")), "link"
        return None, "link"
    return None, "text"


def bluesky_post_url(uri: str, handle: str) -> str | None:
    parts = uri.split("/")
    if len(parts) < 5 or not handle:
        return None
    rkey = parts[-1]
    return valid_http_url(f"https://bsky.app/profile/{handle}/post/{rkey}")


def fetch_bluesky_entries(
    seed_trends: list[str],
) -> tuple[list[StoryEntry], list[str], dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=SOCIAL_MAX_AGE_HOURS)).isoformat().replace("+00:00", "Z")
    seeds: list[str] = []
    for candidate in [*seed_trends[:8], "meme", "insólito", "animales", "televisión"]:
        candidate = candidate.strip().lstrip("#")
        if len(candidate) < 3 or normalize(candidate) in {normalize(item) for item in seeds}:
            continue
        seeds.append(candidate)
        if len(seeds) >= 12:
            break

    entries: list[StoryEntry] = []
    warnings: list[str] = []
    seen: set[str] = set()
    successful_queries = 0
    for seed in seeds:
        params = urllib.parse.urlencode(
            {
                "q": seed,
                "lang": "es",
                "sort": "top",
                "since": since,
                "limit": 25,
            }
        )
        try:
            payload = fetch_json(f"{BLUESKY_SEARCH_URL}?{params}")
            successful_queries += 1
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            warnings.append(f"Bluesky falló para «{seed}»: {exc}")
            continue

        for post in payload.get("posts", []) if isinstance(payload, dict) else []:
            if not isinstance(post, dict):
                continue
            uri = str(post.get("uri", ""))
            if not uri or uri in seen:
                continue
            record = post.get("record")
            if not isinstance(record, dict) or record.get("reply"):
                continue
            text = strip_html(record.get("text"))
            if len(text) < 12 or is_blocked_content(text):
                continue
            labels = post.get("labels")
            if isinstance(labels, list) and any(
                str(label.get("val", "")) in {"porn", "sexual", "nudity", "graphic-media"}
                for label in labels
                if isinstance(label, dict)
            ):
                continue
            published_at = parse_iso_datetime(record.get("createdAt") or post.get("indexedAt"))
            if published_at and published_at < now - dt.timedelta(hours=SOCIAL_MAX_AGE_HOURS):
                continue
            likes = max(0, int(post.get("likeCount") or 0))
            reposts = max(0, int(post.get("repostCount") or 0))
            replies = max(0, int(post.get("replyCount") or 0))
            quotes = max(0, int(post.get("quoteCount") or 0))
            weighted = likes + reposts * 3 + replies * 2 + quotes * 3
            thumbnail, media_type = bluesky_thumbnail(post.get("embed"))
            if weighted < 8 and not thumbnail:
                continue
            author = post.get("author") if isinstance(post.get("author"), dict) else {}
            handle = str(author.get("handle", "")).strip()
            link = bluesky_post_url(uri, handle)
            if not link:
                continue
            seen.add(uri)
            entries.append(
                StoryEntry(
                    title=compact_text(text, 220),
                    link=link,
                    source=f"Bluesky · @{handle}" if handle else "Bluesky",
                    platform="bluesky",
                    published_at=published_at,
                    keywords=keywords(text),
                    social_points=bluesky_social_points(likes, reposts, replies, quotes, published_at),
                    metrics={
                        "likes": likes,
                        "reposts": reposts,
                        "replies": replies,
                        "quotes": quotes,
                    },
                    thumbnail=thumbnail,
                    media_type=media_type,
                    seed_trend=seed,
                )
            )

    ok = successful_queries > 0
    print(f"[ok] Bluesky: {len(entries)} publicaciones")
    return entries, warnings, {
        "name": "Bluesky España",
        "ok": ok,
        "items": len(entries),
        "note": None if ok else "No respondió ninguna búsqueda",
    }


def looks_spanish(text: str) -> bool:
    tokens = normalize(text).split()
    if not tokens:
        return False
    common = {"que", "para", "como", "esto", "esta", "pero", "porque", "cuando", "tambien", "muy", "una", "los", "las"}
    return sum(token in common for token in tokens) >= 2


def fetch_mastodon_entries() -> tuple[list[StoryEntry], list[str], list[dict[str, Any]]]:
    instances = env_list("MASTODON_INSTANCES", DEFAULT_MASTODON_INSTANCES)
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=SOCIAL_MAX_AGE_HOURS)
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    seen: set[str] = set()

    for instance in instances:
        base = instance.rstrip("/")
        name = f"Mastodon · {urllib.parse.urlparse(base).netloc}"
        try:
            payload = fetch_json(f"{base}/api/v1/trends/statuses?limit=40")
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            warnings.append(f"No se pudo consultar {name}: {exc}")
            statuses.append({"name": name, "ok": False, "items": 0})
            continue

        accepted = 0
        for status in payload if isinstance(payload, list) else []:
            if not isinstance(status, dict):
                continue
            if status.get("sensitive") or status.get("in_reply_to_id"):
                continue
            content = strip_html(status.get("content"))
            spoiler = strip_html(status.get("spoiler_text"))
            if spoiler or len(content) < 16 or is_blocked_content(content):
                continue
            language = str(status.get("language") or "").lower()
            if language and not language.startswith("es"):
                continue
            if not language and not looks_spanish(content):
                continue
            published_at = parse_iso_datetime(status.get("created_at"))
            if published_at and published_at < cutoff:
                continue
            link = valid_http_url(status.get("url"))
            if not link or link in seen:
                continue
            favourites = max(0, int(status.get("favourites_count") or 0))
            boosts = max(0, int(status.get("reblogs_count") or 0))
            replies = max(0, int(status.get("replies_count") or 0))
            weighted = favourites + boosts * 3 + replies * 2
            media = status.get("media_attachments")
            thumbnail = None
            media_type = "text"
            if isinstance(media, list) and media:
                first = media[0]
                if isinstance(first, dict):
                    thumbnail = valid_http_url(first.get("preview_url") or first.get("url"))
                    attachment_type = str(first.get("type", ""))
                    media_type = "video" if attachment_type in {"video", "gifv"} else "image"
            if weighted < 6 and not thumbnail:
                continue
            account = status.get("account") if isinstance(status.get("account"), dict) else {}
            acct = str(account.get("acct", "")).strip()
            seen.add(link)
            entries.append(
                StoryEntry(
                    title=compact_text(content, 220),
                    link=link,
                    source=f"Mastodon · @{acct}" if acct else name,
                    platform="mastodon",
                    published_at=published_at,
                    keywords=keywords(content),
                    social_points=mastodon_social_points(favourites, boosts, replies, published_at),
                    metrics={"favourites": favourites, "boosts": boosts, "replies": replies},
                    thumbnail=thumbnail,
                    media_type=media_type,
                )
            )
            accepted += 1
        statuses.append({"name": name, "ok": True, "items": accepted})
        print(f"[ok] {name}: {accepted} publicaciones")

    return entries, warnings, statuses


def fetch_youtube_entries() -> tuple[list[StoryEntry], list[str], dict[str, Any]]:
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return [], [], {
            "name": "YouTube España",
            "ok": None,
            "items": 0,
            "note": "Añade YOUTUBE_API_KEY",
        }
    params = urllib.parse.urlencode(
        {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": "ES",
            "maxResults": 40,
            "key": api_key,
            "fields": "items(id,snippet(publishedAt,channelTitle,title,thumbnails),statistics(viewCount,likeCount,commentCount))",
        }
    )
    try:
        payload = fetch_json(f"{YOUTUBE_VIDEOS_URL}?{params}")
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return [], [f"No se pudo consultar YouTube: {exc}"], {
            "name": "YouTube España",
            "ok": False,
            "items": 0,
        }

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=YOUTUBE_MAX_AGE_HOURS)
    entries: list[StoryEntry] = []
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("id", "")).strip()
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        title = str(snippet.get("title", "")).strip()
        if not video_id or not title or is_blocked_content(title):
            continue
        published_at = parse_iso_datetime(snippet.get("publishedAt"))
        if published_at and published_at < cutoff:
            continue
        views = parse_human_count(statistics.get("viewCount"))
        likes = parse_human_count(statistics.get("likeCount"))
        comments = parse_human_count(statistics.get("commentCount"))
        thumbnails = snippet.get("thumbnails") if isinstance(snippet.get("thumbnails"), dict) else {}
        thumbnail = None
        for key in ("maxres", "standard", "high", "medium", "default"):
            value = thumbnails.get(key)
            if isinstance(value, dict):
                thumbnail = valid_http_url(value.get("url"))
                if thumbnail:
                    break
        channel = str(snippet.get("channelTitle", "")).strip()
        entries.append(
            StoryEntry(
                title=compact_text(title, 220),
                link=f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id)}",
                source=f"YouTube · {channel}" if channel else "YouTube España",
                platform="youtube",
                published_at=published_at,
                keywords=keywords(title),
                social_points=youtube_social_points(views, likes, comments, published_at),
                metrics={"views": views, "likes": likes, "comments": comments},
                thumbnail=thumbnail,
                media_type="video",
            )
        )
    print(f"[ok] YouTube: {len(entries)} vídeos")
    return entries, [], {"name": "YouTube España", "ok": True, "items": len(entries)}


def title_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    intersection = len(a & b)
    if intersection < 2:
        return 0.0
    containment = intersection / min(len(a), len(b))
    jaccard = intersection / len(a | b)
    return max(containment * 0.72, jaccard)


def cluster_entries(entries: list[StoryEntry]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    ordered = sorted(
        entries,
        key=lambda item: (
            item.social_points,
            item.published_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        ),
        reverse=True,
    )

    for entry in ordered:
        best_cluster: dict[str, Any] | None = None
        best_score = 0.0
        for cluster in clusters:
            score = max(title_similarity(entry.keywords, item.keywords) for item in cluster["items"])
            same_seed = entry.seed_trend and any(
                item.seed_trend and normalize(item.seed_trend) == normalize(entry.seed_trend)
                for item in cluster["items"]
            )
            if same_seed:
                score = max(score, 0.64)
            # Dos términos distintivos compartidos suelen bastar para unir un
            # titular corto de una red social con la noticia que aporta contexto.
            if score >= 0.47 and score > best_score:
                best_cluster = cluster
                best_score = score

        if best_cluster is None:
            clusters.append({"items": [entry]})
        else:
            best_cluster["items"].append(entry)

    return clusters


def match_trend(cluster_keywords: frozenset[str], trends: list[dict[str, Any]]) -> dict[str, Any] | None:
    for trend in trends:
        name = str(trend.get("name", "")).strip()
        trend_keywords = keywords(name)
        if not trend_keywords:
            continue
        overlap = len(cluster_keywords & trend_keywords)
        if len(trend_keywords) == 1 and overlap == 1:
            return trend
        if overlap >= 2 and overlap / len(trend_keywords) >= 0.5:
            return trend
    return None


def recency_points(items: list[StoryEntry], now: dt.datetime) -> float:
    dates = [item.published_at for item in items if item.published_at]
    if not dates:
        return 5.0
    hours = age_hours(max(dates), now)
    return max(0.0, 16.0 - hours / 3.0)


def editorial_fit(entry: StoryEntry) -> float:
    text = entry.title
    score = 0.0
    if entry.platform != "news":
        score += 4.0
    if entry.media_type in {"image", "video"}:
        score += 6.0
    score += min(12.0, contains_phrase(text, VIRAL_TERMS) * 2.5)
    score -= min(15.0, contains_phrase(text, POLITICS_TERMS) * 7.0)
    score -= min(12.0, contains_phrase(text, HARD_NEWS_TERMS) * 5.0)
    if entry.source.startswith("Reddit r/yo_elvr") or entry.source.startswith("Reddit r/MemesEnEspanol"):
        score += 4.0
    return max(-18.0, min(22.0, score))


def format_metric(value: int | float) -> str:
    numeric = float(value)
    if numeric >= 1_000_000:
        return f"{numeric / 1_000_000:.1f} M".replace(".0", "")
    if numeric >= 1_000:
        return f"{numeric / 1_000:.1f} k".replace(".0", "")
    return str(int(numeric))


def entry_signal(entry: StoryEntry) -> str | None:
    m = entry.metrics
    if entry.platform == "reddit":
        return f"{format_metric(int(m.get('upvotes', 0)))} votos · {format_metric(int(m.get('comments', 0)))} comentarios en Reddit"
    if entry.platform == "bluesky":
        return f"{format_metric(int(m.get('likes', 0)))} likes · {format_metric(int(m.get('reposts', 0)))} reposts en Bluesky"
    if entry.platform == "mastodon":
        return f"{format_metric(int(m.get('favourites', 0)))} favoritos · {format_metric(int(m.get('boosts', 0)))} impulsos en Mastodon"
    if entry.platform == "youtube":
        return f"{format_metric(int(m.get('views', 0)))} visualizaciones · {format_metric(int(m.get('likes', 0)))} likes en YouTube"
    return None


def choose_main(items: list[StoryEntry]) -> StoryEntry:
    news_items = [item for item in items if item.platform == "news"]
    if news_items and len(items) > 1:
        return max(
            news_items,
            key=lambda item: item.published_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        )
    return max(
        items,
        key=lambda item: (
            item.social_points,
            editorial_fit(item),
            item.published_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        ),
    )


def build_ranked(
    entries: list[StoryEntry],
    google_trends: list[dict[str, Any]],
    x_trends: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    ranked: list[dict[str, Any]] = []

    for cluster in cluster_entries(entries):
        items: list[StoryEntry] = cluster["items"]
        sources = sorted({item.source for item in items}, key=str.casefold)
        platforms = sorted({item.platform for item in items})
        cluster_keywords = frozenset().union(*(item.keywords for item in items))
        google_match = match_trend(cluster_keywords, google_trends)
        x_match = match_trend(cluster_keywords, x_trends)
        if not google_match:
            seed_names = {normalize(item.seed_trend or "") for item in items if item.seed_trend}
            google_match = next(
                (trend for trend in google_trends if normalize(str(trend.get("name", ""))) in seed_names),
                None,
            )
        if not x_match:
            seed_names = {normalize(item.seed_trend or "") for item in items if item.seed_trend}
            x_match = next(
                (trend for trend in x_trends if normalize(str(trend.get("name", ""))) in seed_names),
                None,
            )

        social_values = sorted((item.social_points for item in items), reverse=True)
        social_score = social_values[0] if social_values else 0.0
        social_score += sum(social_values[1:3]) * 0.25
        social_score = min(68.0, social_score)
        platform_bonus = min(30.0, max(0, len(platforms) - 1) * 11.0)
        source_bonus = min(24.0, len(sources) * 5.0)
        mention_bonus = min(16.0, len(items) * 3.0)
        trend_bonus = 0.0
        if google_match:
            trend_bonus += 20.0 + min(8.0, math.log10(int(google_match.get("traffic") or 0) + 1) * 1.6)
        if x_match:
            trend_bonus += 18.0 + min(8.0, math.log10(int(x_match.get("tweet_count") or 0) + 1) * 1.5)
        fit_values = [editorial_fit(item) for item in items]
        fit_score = max(fit_values) + max(0.0, sum(max(0.0, value) for value in fit_values) / max(1, len(fit_values)) * 0.25)
        raw_score = (
            8.0
            + social_score
            + platform_bonus
            + source_bonus
            + mention_bonus
            + trend_bonus
            + recency_points(items, now)
            + fit_score
        )
        # Curva de saturación: evita que muchos candidatos distintos acaben
        # empatados artificialmente en 100.
        viral_score = max(1, min(100, round(100 * (1 - math.exp(-raw_score / 95.0)))))
        main = choose_main(items)
        thumbnail = main.thumbnail or next((item.thumbnail for item in items if item.thumbnail), None)
        media_type = main.media_type
        if media_type == "article":
            media_type = next(
                (item.media_type for item in items if item.media_type in {"image", "video"}),
                media_type,
            )
        signals = [signal for signal in (entry_signal(item) for item in sorted(items, key=lambda item: item.social_points, reverse=True)) if signal]
        signals = list(dict.fromkeys(signals))[:3]
        if google_match:
            label = f"Google Trends: {google_match['name']}"
            if google_match.get("traffic_label"):
                label += f" ({google_match['traffic_label']})"
            signals.append(label)
        if x_match:
            label = f"Tendencia en X: {x_match['name']}"
            if x_match.get("tweet_count"):
                label += f" ({format_metric(int(x_match['tweet_count']))} posts)"
            signals.append(label)
        if len(platforms) >= 2:
            signals.append(f"Detectado en {len(platforms)} plataformas")

        ranked.append(
            {
                "title": main.title,
                "link": main.link,
                "score": viral_score,
                "viral_score": viral_score,
                "raw_score": round(raw_score, 1),
                "sources": sources,
                "source_count": len(sources),
                "platforms": platforms,
                "platform_labels": [PLATFORM_LABELS.get(platform, platform.title()) for platform in platforms],
                "main_platform": main.platform,
                "num_mentions": len(items),
                "matched_trend": google_match.get("name") if google_match else None,
                "matched_google_trend": google_match.get("name") if google_match else None,
                "matched_x_trend": x_match.get("name") if x_match else None,
                "published_at": main.published_at.isoformat().replace("+00:00", "Z") if main.published_at else None,
                "thumbnail": thumbnail,
                "media_type": media_type,
                "signals": signals[:5],
                "metrics": main.metrics,
                "potential": "muy alto" if viral_score >= 80 else "alto" if viral_score >= 65 else "medio" if viral_score >= 45 else "exploratorio",
            }
        )

    ranked.sort(
        key=lambda item: (item["raw_score"], item.get("published_at") or ""),
        reverse=True,
    )
    return ranked[:MAX_STORIES]


def build() -> dict[str, Any]:
    warnings: list[str] = []
    source_status: list[dict[str, Any]] = []

    news_entries, news_warnings, news_status = fetch_news_entries()
    warnings.extend(news_warnings)
    source_status.extend(news_status)

    google_trends, trend_warnings, google_status = get_google_trends()
    warnings.extend(trend_warnings)
    source_status.append(google_status)

    x_trends, x_warnings, x_status = get_x_trends()
    warnings.extend(x_warnings)
    source_status.append(x_status)

    seed_trends = [str(item.get("name", "")) for item in [*google_trends[:8], *x_trends[:5]] if item.get("name")]

    reddit_entries, reddit_warnings, reddit_status = fetch_reddit_entries()
    warnings.extend(reddit_warnings)
    source_status.extend(reddit_status)

    bluesky_entries, bluesky_warnings, bluesky_status = fetch_bluesky_entries(seed_trends)
    warnings.extend(bluesky_warnings)
    source_status.append(bluesky_status)

    mastodon_entries, mastodon_warnings, mastodon_status = fetch_mastodon_entries()
    warnings.extend(mastodon_warnings)
    source_status.extend(mastodon_status)

    youtube_entries, youtube_warnings, youtube_status = fetch_youtube_entries()
    warnings.extend(youtube_warnings)
    source_status.append(youtube_status)

    entries = [
        *news_entries,
        *reddit_entries,
        *bluesky_entries,
        *mastodon_entries,
        *youtube_entries,
    ]
    if not entries:
        raise RuntimeError(
            "No se obtuvo ningún contenido. Se conserva el data.json anterior para no vaciar el panel."
        )

    now = dt.datetime.now(dt.timezone.utc)
    ranked = build_ranked(entries, google_trends, x_trends)
    active_sources = sum(1 for status in source_status if status.get("ok") is True)
    configured_sources = sum(1 for status in source_status if status.get("ok") is not None)

    return {
        "updated_at": now.isoformat().replace("+00:00", "Z"),
        "trends_google": [item["name"] for item in google_trends[:20]],
        "trends_x": [item["name"] for item in x_trends[:20]],
        "trend_details": {"google": google_trends[:20], "x": x_trends[:20]},
        "stories": ranked,
        "warnings": warnings,
        "source_status": source_status,
        "source_summary": {
            "active": active_sources,
            "configured": configured_sources,
            "total": len(source_status),
            "entries_collected": len(entries),
        },
        "methodology": (
            "Potencial viral heurístico basado en interacción observable, velocidad, recencia, "
            "presencia en varias plataformas, Google/X Trends y afinidad editorial. "
            "No predice ni garantiza likes futuros."
        ),
        "editorial_notice": (
            "El panel enlaza a contenido de terceros para descubrimiento. Antes de republicar, "
            "verifica contexto, permisos, autoría, privacidad y seguridad de marca."
        ),
    }


def write_json_atomic(data: dict[str, Any], output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="data-", suffix=".json.tmp", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, output_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


if __name__ == "__main__":
    result = build()
    write_json_atomic(result)
    for warning in result["warnings"]:
        print(f"[aviso] {warning}")
    print(f"Escritos {len(result['stories'])} temas en {OUTPUT_PATH}")
