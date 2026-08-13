"""Obtiene el ranking público de ForoCoches como señales, no como noticias."""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

TRENDING_URL = "https://forocoches.com/foro/trending.php?forumid=0&all&display"
BASE_URL = "https://forocoches.com/foro/"
USER_AGENT = "PulsoViral/3.0 (+https://github.com/unzak/noticias-virales)"


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
    return parse_trending_html(payload.decode(charset, errors="replace"), limit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(fetch_forocoches_trending(args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
