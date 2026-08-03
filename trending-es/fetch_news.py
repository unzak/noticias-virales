"""Genera el ranking del dashboard y lo guarda en docs/data.json.

Fuentes sin API key:
- Google News España (RSS)
- Menéame (RSS)
- Google Trends España, "Tendencias actuales" (RSS)

El score es una heurística editorial: combina diversidad de medios,
repetición del tema, recencia y coincidencia con Google Trends.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import feedparser

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "docs" / "data.json"

NEWS_SOURCES = (
    ("Google News España", "https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es"),
    ("Menéame", "https://www.meneame.net/rss2"),
)
TRENDS_URL = "https://trends.google.com/trending/rss?geo=ES"
USER_AGENT = "PulsoNoticias/1.1 (+GitHub Actions; RSS dashboard)"
HTTP_TIMEOUT_SECONDS = 20
MAX_STORY_AGE_HOURS = 48
MAX_STORIES = 40

STOPWORDS = set(
    """de la el en y a los que del las un por con no una su para es al lo
    como más pero sus le ya o este si porque esta entre cuando muy sin
    sobre también me hasta hay donde quien desde todo nos durante todos
    uno les ni contra otros ese eso ante ellos e esto mi antes algunos
    unos yo otro otras otra tanto esa estos mucho quienes nada muchos
    cual poco ella estar estas algunas algo nosotros mis tu tus ellas
    nosotras vosotros vosotras os mio mia mios mias tuyo tuya tuyos
    tuyas suyo suya suyos suyas nuestro nuestra nuestros nuestras
    vuestro vuestra vuestros vuestras esos esas tras dice dijo según
    ultima último últimas últimos hoy directo minuto minutos""".split()
)


@dataclass(frozen=True)
class StoryEntry:
    title: str
    link: str
    source: str
    published_at: dt.datetime | None
    keywords: frozenset[str]


def fetch_feed(url: str) -> Any:
    """Descarga un RSS con timeout y lo entrega a feedparser."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = response.read()
    return feedparser.parse(payload)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^a-záéíóúñü0-9\s]", " ", text)
    return " ".join(text.split())


def keywords(text: str) -> frozenset[str]:
    return frozenset(
        word for word in normalize(text).split() if len(word) > 3 and word not in STOPWORDS
    )


def valid_http_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def parse_published(entry: Any) -> dt.datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        timestamp = calendar.timegm(parsed)
        return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return None


def clean_google_title(title: str, publisher: str | None) -> str:
    """Quita el sufijo ' - Medio' habitual en Google News."""
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
    if fallback == "Google News España" and " - " in raw_title:
        possible = raw_title.rsplit(" - ", 1)[1].strip()
        if possible:
            return possible
    return fallback


def fetch_entries() -> tuple[list[StoryEntry], list[str]]:
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=MAX_STORY_AGE_HOURS)
    seen: set[tuple[str, str]] = set()

    for fallback_source, url in NEWS_SOURCES:
        try:
            feed = fetch_feed(url)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            warnings.append(f"No se pudo descargar {fallback_source}: {exc}")
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
            title = (
                clean_google_title(raw_title, source)
                if fallback_source == "Google News España"
                else raw_title
            )
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
                    title=title,
                    link=link,
                    source=source,
                    published_at=published_at,
                    keywords=title_keywords,
                )
            )
            accepted += 1

        print(f"[ok] {fallback_source}: {accepted} noticias aceptadas")

    return entries, warnings


def get_trends() -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    try:
        feed = fetch_feed(TRENDS_URL)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return [], [f"No se pudo descargar Google Trends: {exc}"]

    if getattr(feed, "bozo", False):
        warnings.append(
            "Google Trends devolvió un RSS con advertencias: "
            f"{getattr(feed, 'bozo_exception', 'formato no válido')}"
        )

    trends: list[str] = []
    seen: set[str] = set()
    for entry in feed.entries:
        title = str(entry.get("title", "")).strip()
        normalized = normalize(title)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        trends.append(title)
    print(f"[ok] Google Trends: {len(trends)} tendencias")
    return trends[:25], warnings


def title_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Similitud conservadora para evitar unir temas por una sola palabra."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    intersection = len(a & b)
    if intersection < 2:
        return 0.0
    containment = intersection / min(len(a), len(b))
    jaccard = intersection / len(a | b)
    return max(containment * 0.7, jaccard)


def cluster_entries(entries: list[StoryEntry]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    ordered = sorted(
        entries,
        key=lambda item: item.published_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        reverse=True,
    )

    for entry in ordered:
        best_cluster: dict[str, Any] | None = None
        best_score = 0.0
        for cluster in clusters:
            score = max(
                title_similarity(entry.keywords, item.keywords)
                for item in cluster["items"]
            )
            if score >= 0.55 and score > best_score:
                best_cluster = cluster
                best_score = score

        if best_cluster is None:
            clusters.append({"items": [entry]})
        else:
            best_cluster["items"].append(entry)

    return clusters


def trend_match(cluster_keywords: frozenset[str], trends: list[str]) -> str | None:
    for trend in trends:
        trend_keywords = keywords(trend)
        if not trend_keywords:
            continue
        overlap = len(cluster_keywords & trend_keywords)
        if len(trend_keywords) == 1 and overlap == 1:
            return trend
        if overlap >= 2 and overlap / len(trend_keywords) >= 0.5:
            return trend
    return None


def recency_bonus(items: list[StoryEntry], now: dt.datetime) -> int:
    dates = [item.published_at for item in items if item.published_at]
    if not dates:
        return 0
    age_hours = max(0.0, (now - max(dates)).total_seconds() / 3600)
    return max(0, round(12 - age_hours / 2))


def build() -> dict[str, Any]:
    entries, warnings = fetch_entries()
    if not entries:
        raise RuntimeError(
            "No se obtuvo ninguna noticia. Se conserva el data.json anterior para no vaciar el panel."
        )

    trends, trend_warnings = get_trends()
    warnings.extend(trend_warnings)
    clusters = cluster_entries(entries)
    now = dt.datetime.now(dt.timezone.utc)

    ranked: list[dict[str, Any]] = []
    for cluster in clusters:
        items: list[StoryEntry] = cluster["items"]
        sources = sorted({item.source for item in items}, key=str.casefold)
        cluster_keywords = frozenset().union(*(item.keywords for item in items))
        matched_trend = trend_match(cluster_keywords, trends)
        bonus = recency_bonus(items, now)
        score = len(sources) * 12 + len(items) * 3 + bonus
        if matched_trend:
            score += 30

        main = max(
            items,
            key=lambda item: (
                item.published_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                -len(item.title),
            ),
        )
        ranked.append(
            {
                "title": main.title,
                "link": main.link,
                "score": score,
                "sources": sources,
                "num_mentions": len(items),
                "matched_trend": matched_trend,
                "published_at": main.published_at.isoformat().replace("+00:00", "Z")
                if main.published_at
                else None,
            }
        )

    ranked.sort(
        key=lambda item: (item["score"], item.get("published_at") or ""), reverse=True
    )

    return {
        "updated_at": now.isoformat().replace("+00:00", "Z"),
        "trends_google": trends[:20],
        "stories": ranked[:MAX_STORIES],
        "warnings": warnings,
        "methodology": (
            "Score heurístico basado en diversidad de medios, menciones, recencia "
            "y coincidencia con Google Trends; no representa compartidos reales en redes sociales."
        ),
    }


def write_json_atomic(data: dict[str, Any], output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix="data-", suffix=".json.tmp", dir=output_path.parent
    )
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
    print(f"Escritas {len(result['stories'])} noticias en {OUTPUT_PATH}")
