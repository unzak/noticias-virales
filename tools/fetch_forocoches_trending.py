"""Obtiene el ranking público de ForoCoches como señales, no como noticias."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

TRENDING_URL = "https://forocoches.com/foro/trending.php?forumid=0&all&display"
BASE_URL = "https://forocoches.com/foro/"
USER_AGENT = "PulsoViral/3.0 (+https://github.com/unzak/noticias-virales)"
MADRID_TZ = ZoneInfo("Europe/Madrid")


class TrendingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []
        self._started = False
        self._href = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and self._started:
            href = dict(attrs).get("href") or ""
            if re.search(r"(?:^|/)showthread\.php\?t=\d+", href):
                self._href, self._parts = href, []

    def handle_data(self, data: str) -> None:
        if "Trending en Forocoches" in data:
            self._started = True
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._href:
            return
        title = " ".join(html.unescape(" ".join(self._parts)).split()).strip()
        match = re.search(r"[?&]t=(\d+)", self._href)
        if title and match and not any(item["thread_id"] == match.group(1) for item in self.items):
            self.items.append({
                "rank": len(self.items) + 1,
                "thread_id": match.group(1),
                "name": title,
                "url": urllib.parse.urljoin(BASE_URL, self._href),
            })
        self._href, self._parts = "", []


def parse_trending_html(document: str, limit: int = 30) -> list[dict[str, Any]]:
    parser = TrendingParser()
    parser.feed(document)
    parser.close()
    return parser.items[: max(0, limit)]


class ThreadTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split()).strip()
        if value:
            self.parts.append(value)


def parse_thread_published(document: str, now: dt.datetime | None = None) -> dt.datetime | None:
    """Extrae la fecha del mensaje #1, nunca la de la última respuesta."""
    parser = ThreadTextParser()
    parser.feed(document)
    parser.close()
    try:
        first_post_index = parser.parts.index("#1")
    except ValueError:
        return None
    context = parser.parts[max(0, first_post_index - 12):first_post_index]
    reference = (now or dt.datetime.now(MADRID_TZ)).astimezone(MADRID_TZ)
    for value in reversed(context):
        relative = re.fullmatch(r"(Hoy|Ayer)\s+(\d{1,2}):(\d{2})", value, re.IGNORECASE)
        if relative:
            day = reference.date() - dt.timedelta(days=int(relative.group(1).lower() == "ayer"))
            return dt.datetime.combine(
                day,
                dt.time(int(relative.group(2)), int(relative.group(3))),
                tzinfo=MADRID_TZ,
            )
        absolute = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})", value)
        if absolute:
            return dt.datetime(
                int(absolute.group(3)), int(absolute.group(2)), int(absolute.group(1)),
                int(absolute.group(4)), int(absolute.group(5)), tzinfo=MADRID_TZ,
            )
    return None


def fetch_thread_published(url: str, timeout: int = 20) -> dt.datetime | None:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "es-ES,es;q=0.9",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(1_500_000)
        charset = response.headers.get_content_charset() or "utf-8"
    return parse_thread_published(payload.decode(charset, errors="replace"))


def fetch_forocoches_trending(limit: int = 30, timeout: int = 20) -> list[dict[str, Any]]:
    request = urllib.request.Request(TRENDING_URL, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "es-ES,es;q=0.9",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(1_500_000)
        charset = response.headers.get_content_charset() or "utf-8"
    items = parse_trending_html(payload.decode(charset, errors="replace"), limit)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_thread_published, item["url"], timeout): item
            for item in items
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                published = future.result()
            except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
                published = None
            item["published_at"] = published.isoformat() if published else None
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(fetch_forocoches_trending(args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
