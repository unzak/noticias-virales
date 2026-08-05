#!/usr/bin/env python3
"""Genera docs/data.json a partir de varios feeds RSS/Atom públicos.

El script está pensado para GitHub Actions: tolera fallos de red individuales y,
si todas las fuentes fallan, conserva el último JSON válido para que el despliegue
no se rompa.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

OUTPUT = Path("docs/data.json")
LAST_UPDATE = Path("docs/last-update.txt")
USER_AGENT = "RadarViralBot/1.0 (+GitHub Pages; RSS reader)"
MAX_PER_SOURCE = 25
MAX_STORIES = 40

FEEDS = (
    ("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml", 8),
    ("El Mundo", "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml", 7),
    ("20minutos", "https://www.20minutos.es/rss/", 6),
    ("Hacker News", "https://hnrss.org/frontpage", 5),
)


@dataclass(frozen=True)
class Story:
    title: str
    link: str
    source: str
    published_at: str
    summary: str
    thumbnail: str
    score: float


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def clean_text(value: str | None, limit: int = 320) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit].rstrip()


def safe_url(value: str | None) -> str:
    value = (value or "").strip()
    return value if value.startswith(("https://", "http://")) else ""


def parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def first_text(node: ET.Element, names: set[str]) -> str:
    for child in node.iter():
        if local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def find_link(node: ET.Element) -> str:
    # RSS suele usar texto; Atom suele usar el atributo href.
    for child in node.iter():
        if local_name(child.tag) != "link":
            continue
        href = safe_url(child.attrib.get("href"))
        if href and child.attrib.get("rel", "alternate") in ("alternate", ""):
            return href
        text = safe_url(child.text)
        if text:
            return text
    return ""


def find_thumbnail(node: ET.Element) -> str:
    for child in node.iter():
        name = local_name(child.tag)
        if name in {"thumbnail", "content", "enclosure"}:
            candidate = safe_url(child.attrib.get("url") or child.attrib.get("href"))
            media_type = child.attrib.get("type", "")
            medium = child.attrib.get("medium", "")
            if candidate and (name == "thumbnail" or medium == "image" or media_type.startswith("image/")):
                return candidate
    return ""


def calculate_score(published: datetime, source_bonus: int) -> float:
    age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
    recency = max(0.0, 92.0 - age_hours * 1.8)
    return round(min(100.0, recency + source_bonus), 1)


def parse_feed(xml_bytes: bytes, source: str, source_bonus: int) -> list[Story]:
    root = ET.fromstring(xml_bytes)
    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    stories: list[Story] = []

    for entry in entries[:MAX_PER_SOURCE]:
        title = clean_text(first_text(entry, {"title"}), 180)
        link = find_link(entry)
        if not title or not link:
            continue

        published_raw = first_text(entry, {"pubdate", "published", "updated", "date"})
        published = parse_date(published_raw)
        summary = clean_text(first_text(entry, {"description", "summary", "content"}))
        thumbnail = find_thumbnail(entry)

        stories.append(
            Story(
                title=title,
                link=link,
                source=source,
                published_at=published.isoformat().replace("+00:00", "Z"),
                summary=summary,
                thumbnail=thumbnail,
                score=calculate_score(published, source_bonus),
            )
        )
    return stories


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/xml"},
    )
    with urllib.request.urlopen(request, timeout=18) as response:
        return response.read(3_000_000)


def deduplicate(stories: Iterable[Story]) -> list[Story]:
    result: list[Story] = []
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    for story in stories:
        title_key = re.sub(r"\W+", "", story.title.lower())
        if story.link in seen_links or title_key in seen_titles:
            continue
        seen_links.add(story.link)
        seen_titles.add(title_key)
        result.append(story)
    return result


def previous_stories() -> list[dict]:
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        stories = payload.get("stories", [])
        return stories if isinstance(stories, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def write_payload(stories: list[Story], errors: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    all_items = [asdict(story) for story in stories]

    if all_items:
        selected = all_items[:MAX_STORIES]
        status = "ok" if not errors else "partial"
    else:
        selected = previous_stories()
        all_items = selected
        status = "fallback" if selected else "empty"

    payload = {
        "generated_at": now,
        "status": status,
        "errors": errors,
        "stories": selected,
        "unfiltered_stories": all_items,
        "temporal_summary": {
            "accepted": len(all_items),
            "selected": len(selected),
            "sources_ok": len(FEEDS) - len(errors),
            "sources_total": len(FEEDS),
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LAST_UPDATE.write_text(now + "\n", encoding="utf-8")


def main() -> int:
    collected: list[Story] = []
    errors: list[str] = []

    for source, url, bonus in FEEDS:
        try:
            collected.extend(parse_feed(download(url), source, bonus))
            print(f"OK: {source}")
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            message = f"{source}: {type(exc).__name__}"
            errors.append(message)
            print(f"AVISO: {message}", file=sys.stderr)

    ranked = sorted(deduplicate(collected), key=lambda item: (item.score, item.published_at), reverse=True)
    write_payload(ranked, errors)
    print(f"Generadas {min(len(ranked), MAX_STORIES)} noticias; errores: {len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
