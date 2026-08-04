"""Genera un ranking editorial de contenidos con potencial viral en España.

Fuentes sin clave:
- Google News España, búsquedas temáticas y secciones virales de medios españoles (RSS)
- Menéame · Populares y Más visitadas (HTML público)
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
import hashlib
import html
import ipaddress
import json
import math
import os
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

import feedparser

ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "docs" / "data.json"
MEDIA_DIR = ROOT / "docs" / "media"

GOOGLE_NEWS_BASE = "https://news.google.com/rss"
GOOGLE_NEWS_PARAMS = "hl=es&gl=ES&ceid=ES:es"


def google_news_search_url(query: str) -> str:
    return (
        f"{GOOGLE_NEWS_BASE}/search?"
        f"{urllib.parse.urlencode({'q': query})}&{GOOGLE_NEWS_PARAMS}"
    )


# Cada tupla contiene:
# (nombre visible del feed, URL, impulso editorial, sección editorial, etiquetas).
#
# Las búsquedas temáticas se agrupan por familias de medios para cubrir un
# abanico amplio sin disparar el número de peticiones. Google News devuelve el
# medio real en cada entrada, por lo que el panel sigue mostrando la cabecera
# de origen y no el nombre del grupo de búsqueda.


CABRONAZI_QUERY_EXCLUSIONS = (
    '-politica -política -gobierno -elecciones -congreso -senado '
    '-ministro -ministra -guerra -tribunal -economia -economía'
)


def focused_news_query(terms: str) -> str:
    """Limita Google News a piezas recientes y evita actualidad institucional."""
    return f"({terms}) when:1d {CABRONAZI_QUERY_EXCLUSIONS}"


def google_news_sites_query(domains: Iterable[str], terms: str) -> str:
    sites = " OR ".join(f"site:{domain}" for domain in domains)
    return google_news_search_url(f"{focused_news_query(terms)} ({sites})")


MEDIA_TOPIC_GROUPS = (
    (
        "prensa nacional",
        (
            "elpais.com", "elmundo.es", "abc.es", "lavanguardia.com",
            "20minutos.es", "elconfidencial.com", "elespanol.com",
            "huffingtonpost.es",
        ),
    ),
    (
        "televisión y radio",
        (
            "rtve.es", "antena3.com", "lasexta.com", "telecinco.es",
            "cuatro.com", "cope.es", "ondacero.es",
        ),
    ),
    (
        "medios digitales",
        (
            "eldiario.es", "publico.es", "larazon.es", "okdiario.com",
            "vozpopuli.com", "infolibre.es", "libertaddigital.com",
        ),
    ),
    (
        "deportes y entretenimiento",
        (
            "marca.com", "as.com", "mundodeportivo.com", "sport.es",
            "hola.com", "lecturas.com", "diezminutos.es", "semana.es",
        ),
    ),
    (
        "prensa regional",
        (
            "elperiodico.com", "heraldo.es", "levante-emv.com",
            "lasprovincias.es", "ideal.es", "diariodesevilla.es",
            "farodevigo.es",
        ),
    ),
)


def build_topic_sources() -> tuple[tuple[Any, ...], ...]:
    sources: list[tuple[Any, ...]] = []
    for group_name, domains in MEDIA_TOPIC_GROUPS:
        sources.append(
            (
                f"TikTok · {group_name}",
                google_news_sites_query(
                    domains,
                    'TikTok OR tiktoker OR "vídeo de TikTok" OR "video de TikTok"',
                ),
                9.0,
                "TikTok",
                ("tiktok",),
            )
        )
        sources.append(
            (
                f"Curiosidades · {group_name}",
                google_news_sites_query(
                    domains,
                    'curiosidades OR curioso OR curiosa OR insólito OR insolito OR sorprendente',
                ),
                8.0,
                "Curiosidades",
                ("curiosidades",),
            )
        )
    return tuple(sources)


NEWS_SOURCES = (
    (
        "EL PAÍS · Lo más visto",
        "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/lo-mas-visto/portada",
        5.0,
        "Lo más visto",
        ("popular",),
    ),
    (
        "EL PAÍS · Viral Internet",
        google_news_search_url(focused_news_query(
            'site:elpais.com (viral OR meme OR "redes sociales" OR TikTok OR Instagram OR curioso)'
        )),
        8.0,
        "Viral Internet y redes",
        ("viral", "redes"),
    ),
    (
        "MARCA · Tiramillas",
        google_news_search_url(focused_news_query(
            'site:marca.com/tiramillas (viral OR curioso OR famosos OR television OR redes)'
        )),
        9.0,
        "Tiramillas",
        ("viral", "curiosidades"),
    ),
    (
        "20minutos · Virales",
        google_news_search_url(focused_news_query(
            'site:20minutos.es (viral OR memes OR TikTok OR Instagram OR curioso OR insolito)'
        )),
        9.0,
        "Virales, redes y Gonzoo",
        ("viral", "redes"),
    ),
    (
        "El HuffPost · Virales",
        google_news_search_url(focused_news_query(
            'site:huffingtonpost.es/virales (viral OR humor OR curioso OR redes)'
        )),
        10.0,
        "Virales",
        ("viral",),
    ),
    (
        "AS · Tikitakas Viral",
        google_news_search_url(focused_news_query(
            'site:as.com/tikitakas (viral OR TikTok OR Instagram OR famosos OR television)'
        )),
        9.0,
        "Tikitakas Virales",
        ("viral", "famosos"),
    ),
    (
        "Telecinco · Curioso y virales",
        google_news_search_url(focused_news_query(
            'site:telecinco.es ("noticias virales" OR curioso OR viral OR reality OR famosos)'
        )),
        8.0,
        "Curioso y noticias virales",
        ("viral", "curiosidades", "television"),
    ),
    (
        "Público · Tremending",
        google_news_search_url(focused_news_query(
            'site:publico.es/tremending (viral OR redes OR humor OR memes)'
        )),
        8.0,
        "Tremending",
        ("viral", "redes"),
    ),
    (
        "LOS40 · Virales",
        google_news_search_url(focused_news_query(
            'site:los40.com (viral OR meme OR TikTok OR famosos OR television OR musica)'
        )),
        8.0,
        "Virales y entretenimiento",
        ("viral", "famosos", "redes"),
    ),
    *build_topic_sources(),
    (
        "Google News · humor y memes",
        google_news_search_url(focused_news_query(
            'meme OR memes OR humor OR broma OR parodia OR gracioso OR divertido OR "hace reír"'
        )),
        7.0,
        "Humor y memes",
        ("humor", "memes"),
    ),
    (
        "Google News · animales y mascotas",
        google_news_search_url(focused_news_query(
            'perro OR gato OR mascota OR animales OR rescate animal OR "vídeo de animales"'
        )),
        7.0,
        "Animales y mascotas",
        ("animales",),
    ),
    (
        "Google News · famosos, televisión y realities",
        google_news_search_url(focused_news_query(
            'famosos OR celebridades OR television OR reality OR influencer OR streamer OR "momento viral"'
        )),
        6.0,
        "Famosos, televisión y realities",
        ("famosos", "television"),
    ),
    (
        "Google News · insólito y WTF",
        google_news_search_url(focused_news_query(
            'insolito OR insólito OR sorprendente OR surrealista OR inesperado OR alucina OR "no da crédito"'
        )),
        8.0,
        "Insólito y sorprendente",
        ("insolito", "curiosidades"),
    ),
    (
        "Google News · redes y creadores",
        google_news_search_url(focused_news_query(
            'TikTok OR Instagram OR YouTube OR streamer OR influencer OR "arrasa en redes" OR "se hace viral"'
        )),
        7.0,
        "Redes y creadores",
        ("redes",),
    ),
    (
        "Google News · tecnología e IA curiosa",
        google_news_search_url(focused_news_query(
            '"inteligencia artificial" OR robot OR gadget OR WhatsApp OR movil OR videojuego OR invento curioso'
        )),
        5.0,
        "Tecnología e IA",
        ("tecnologia",),
    ),
    (
        "Google News · deporte viral",
        google_news_search_url(focused_news_query(
            '"momento viral" deporte OR celebración OR aficionado OR golazo OR reacción OR gesto deportivo'
        )),
        6.0,
        "Deporte viral",
        ("deportes",),
    ),
    (
        "Google News · comida, viajes y trucos",
        google_news_search_url(focused_news_query(
            'comida OR receta OR restaurante OR viaje OR destino OR truco OR hogar OR "consejo viral"'
        )),
        4.0,
        "Lifestyle compartible",
        ("lifestyle",),
    ),
    (
        "Google News · historias positivas",
        google_news_search_url(focused_news_query(
            'historia emotiva OR gesto solidario OR reencuentro OR rescate OR sorpresa OR superación'
        )),
        6.0,
        "Historias positivas",
        ("historias",),
    ),
    (
        "Google News · videojuegos y nostalgia",
        google_news_search_url(focused_news_query(
            'videojuegos OR gaming OR nostalgia OR "años 90" OR "años 2000" OR infancia OR retro'
        )),
        5.0,
        "Videojuegos y nostalgia",
        ("videojuegos", "nostalgia"),
    ),
)

# Secciones editoriales que se leen directamente desde la portada del medio.
# Google News queda como respaldo si una portada cambia temporalmente su HTML.
# Tupla: (estado, medio, URL directa, URL de respaldo, impulso, sección, etiquetas).
DIRECT_SECTION_SOURCES = (
    (
        "La Vanguardia · Cribeo Viral",
        "La Vanguardia",
        "https://www.lavanguardia.com/cribeo/viral",
        google_news_search_url(focused_news_query("site:lavanguardia.com/cribeo/viral")),
        10.0,
        "Cribeo Viral",
        ("viral", "curiosidades"),
    ),
    (
        "Antena 3 · Virales",
        "Antena 3",
        "https://www.antena3.com/noticias/virales/",
        google_news_search_url(focused_news_query("site:antena3.com/noticias/virales")),
        9.0,
        "Virales",
        ("viral",),
    ),
    (
        "laSexta · Viral",
        "laSexta",
        "https://www.lasexta.com/temas/viral-1",
        google_news_search_url(focused_news_query('site:lasexta.com (viral OR "vídeo viral" OR "video viral")')),
        9.0,
        "Viral y vídeos virales",
        ("viral", "curiosidades"),
    ),
    (
        "EL ESPAÑOL · Offbeat",
        "EL ESPAÑOL",
        "https://www.elespanol.com/offbeat/",
        google_news_search_url(focused_news_query("site:elespanol.com/offbeat")),
        9.0,
        "Offbeat",
        ("viral", "curiosidades"),
    ),
    (
        "Infobae · Virales",
        "Infobae",
        "https://www.infobae.com/virales/",
        google_news_search_url(focused_news_query('site:infobae.com/virales (TikTok OR curiosidades OR viral OR insólito)')),
        10.0,
        "Virales",
        ("viral", "tiktok", "curiosidades"),
    ),
    (
        "Infobae España · Virales",
        "Infobae España",
        "https://www.infobae.com/tag/virales-espana/",
        google_news_search_url(focused_news_query('site:infobae.com/espana (TikTok OR curiosidades OR curioso OR viral)')),
        9.0,
        "Virales España",
        ("viral", "tiktok", "curiosidades"),
    ),
)
MENEAME_SECTIONS = (
    ("Menéame · Populares", "https://www.meneame.net/popular", "popular"),
    ("Menéame · Más visitadas", "https://www.meneame.net/top_visited", "top_visited"),
)
GOOGLE_TRENDS_URL = "https://trends.google.com/trending/rss?geo=ES"
BLUESKY_SEARCH_URLS = (
    "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
    "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
)
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
    "PulsoNoticias/3.0 (+https://github.com/unzak/noticias-virales)",
)
HTTP_TIMEOUT_SECONDS = 25
CONTENT_MAX_AGE_HOURS = 24
NEWS_MAX_AGE_HOURS = CONTENT_MAX_AGE_HOURS
SOCIAL_MAX_AGE_HOURS = CONTENT_MAX_AGE_HOURS
YOUTUBE_MAX_AGE_HOURS = CONTENT_MAX_AGE_HOURS
FUTURE_CLOCK_SKEW_MINUTES = 20
PUBLICATION_DATE_ENRICH_LIMIT = 160
PUBLICATION_DATE_WORKERS = 10
PUBLICATION_DATE_HTML_MAX_BYTES = 900_000
MAX_STORIES = 100
MAX_NEWS_ITEMS_PER_SOURCE = 35
IMAGE_ENRICH_LIMIT = 100
IMAGE_PAGE_CONTEXT_LIMIT = 3
IMAGE_CANDIDATE_LIMIT = 5
IMAGE_WORKERS = 10
IMAGE_HTML_MAX_BYTES = 1_800_000
IMAGE_FILE_MAX_BYTES = 2_500_000
IMAGE_MIN_WIDTH = 300
IMAGE_MIN_HEIGHT = 150
IMAGE_MIN_AREA = 90_000
IMAGE_MIN_ASPECT = 0.28
IMAGE_MAX_ASPECT = 4.0
IMAGE_FETCH_TIMEOUT_SECONDS = 10
BROWSER_USER_AGENT = os.getenv(
    "PULSO_IMAGE_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 PulsoNoticias/3.0",
)

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
    "animal", "animales", "perro", "gato", "mascota", "reaccion",
    "sorpresa", "insolito", "curioso", "curiosidad", "increible",
    "divertido", "humor", "broma", "meme", "television", "reality",
    "famoso", "famosa", "celebridad", "influencer", "streamer",
    "futbol", "deporte", "comida", "viaje", "tecnologia", "truco",
    "historia", "anecdota", "fail", "reto", "parodia", "surrealista",
    "inesperado", "emociona", "nostalgia", "videojuego", "viraliza",
)
POLITICS_TERMS = (
    "gobierno", "ministro", "ministra", "presidente", "presidenta",
    "congreso", "senado", "elecciones", "campana electoral",
    "partido politico", "diputado", "diputada", "parlamento",
    "moncloa", "coalicion", "oposicion", "mocion", "decreto ley",
    "sanchez", "abascal", "feijoo", "podemos", "vox", "psoe", "pp ",
)
HARD_NEWS_TERMS = (
    "guerra", "ataque", "bombardeo", "asesinato", "muere", "muerte",
    "fallece", "accidente", "incendio", "violencia", "tribunal",
    "detenido", "detenida", "crisis", "delito", "homicidio",
    "desaparecido", "desaparecida", "herido", "herida", "catastrofe",
)
INSTITUTIONAL_TERMS = (
    "boe", "ley", "impuesto", "presupuesto", "economia", "inflacion",
    "paro", "bolsa", "union europea", "ayuntamiento", "comunidad autonoma",
    "juzgado", "audiencia nacional", "tribunal supremo", "fiscalia",
)

CABRONAZI_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("humor", ("humor", "gracioso", "divertido", "broma", "parodia", "chiste", "carcajada", "desternillante", "hace reir", "se rie", "risa", "risas")),
    ("memes", ("meme", "memes", "plantilla viral", "reaccion viral", "se convierte en meme")),
    ("animales", ("animal", "animales", "perro", "gato", "mascota", "cachorro", "rescate animal", "zoo")),
    ("famosos", ("famoso", "famosa", "celebridad", "influencer", "streamer", "cantante", "actor", "actriz")),
    ("television", ("television", "programa", "presentador", "presentadora", "en directo", "plato", "concurso")),
    ("reality", ("reality", "supervivientes", "gran hermano", "tentaciones", "masterchef", "operacion triunfo")),
    ("insolito", ("insolito", "sorprendente", "sorprende", "sorprendio", "surrealista", "inesperado", "inesperada", "alucina", "no da credito", "wtf")),
    ("redes", ("tiktok", "tik tok", "instagram", "youtube", "twitter", "redes sociales", "se hace viral", "arrasa en redes", "viraliza")),
    ("tecnologia", ("inteligencia artificial", "chatgpt", "robot", "gadget", "movil", "iphone", "android", "whatsapp", "invento")),
    ("videojuegos", ("videojuego", "videojuegos", "gaming", "playstation", "xbox", "nintendo", "steam", "gamer")),
    ("deportes", ("futbol", "deporte", "partido", "golazo", "aficionado", "celebracion", "entrenador", "arbitro")),
    ("comida", ("comida", "receta", "restaurante", "cocina", "hamburguesa", "pizza", "supermercado", "chef")),
    ("viajes", ("viaje", "viajar", "destino", "turista", "turismo", "hotel", "playa", "avion")),
    ("historias", ("historia emotiva", "emociona", "gesto", "solidario", "reencuentro", "rescate", "superacion", "sorpresa")),
    ("nostalgia", ("nostalgia", "anos 90", "anos 2000", "infancia", "retro", "recordar", "generacion")),
    ("lifestyle", ("truco", "consejo", "hogar", "limpieza", "moda", "belleza", "pareja", "familia", "salud", "ahorrar")),
)
CABRONAZI_CORE_TAGS = frozenset(tag for tag, _ in CABRONAZI_TAG_RULES)
CABRONAZI_STRONG_TAGS = frozenset({
    "humor", "memes", "animales", "famosos", "television", "reality",
    "insolito", "redes", "videojuegos", "deportes", "historias", "nostalgia",
})
CABRONAZI_TAG_ORDER = (
    "trending", "viral", "humor", "memes", "animales", "insolito",
    "famosos", "television", "reality", "redes", "tecnologia",
    "videojuegos", "deportes", "comida", "viajes", "historias",
    "nostalgia", "lifestyle", "tiktok", "curiosidades",
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
    "meneame": "Menéame",
    "reddit": "Reddit",
    "bluesky": "Bluesky",
    "mastodon": "Mastodon",
    "youtube": "YouTube",
}


@dataclass(frozen=True)
class ImageCandidate:
    url: str
    origin: str
    base_score: float
    alt: str = ""
    width: int = 0
    height: int = 0
    page_url: str | None = None


@dataclass(frozen=True)
class StoryEntry:
    title: str
    link: str
    source: str
    platform: str
    published_at: dt.datetime | None
    keywords: frozenset[str]
    social_points: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    thumbnail: str | None = None
    image_candidates: tuple[ImageCandidate, ...] = ()
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


def classify_topic_tags(text: str, configured: Iterable[str] = ()) -> set[str]:
    tags = {str(tag).strip().lower() for tag in configured if str(tag).strip()}
    for tag, phrases in CABRONAZI_TAG_RULES:
        if contains_phrase(text, phrases):
            tags.add(tag)
    normalized = normalize(text)
    if "tiktok" in normalized or "tik tok" in normalized:
        tags.update({"tiktok", "redes"})
    if any(term in normalized for term in ("curiosidad", "curioso", "curiosa", "insolito", "sorprendente", "surrealista")):
        tags.add("curiosidades")
    return tags


def cluster_editorial_profile(items: list["StoryEntry"]) -> dict[str, Any]:
    text = " ".join(item.title for item in items)
    configured = [
        tag
        for item in items
        for tag in (item.metrics.get("topic_tags") or [])
    ]
    tags = classify_topic_tags(text, configured)
    politics_hits = contains_phrase(text, POLITICS_TERMS)
    hard_news_hits = contains_phrase(text, HARD_NEWS_TERMS)
    institutional_hits = contains_phrase(text, INSTITUTIONAL_TERMS)
    visual = any(item.media_type in {"image", "video"} for item in items)
    social = any(item.platform != "news" for item in items)
    curated = any(bool(item.metrics.get("curated_editorial")) for item in items)
    specific_tags = tags & CABRONAZI_CORE_TAGS
    strong_tags = tags & CABRONAZI_STRONG_TAGS
    trusted_viral_feed = curated and bool(tags & {"viral", "curiosidades", "tiktok"})
    strong_viral = bool(strong_tags) and (visual or social or curated or len(items) >= 2)
    if len(specific_tags) >= 2 or (trusted_viral_feed and not politics_hits and not hard_news_hits):
        strong_viral = True
    generic_news = all(item.platform == "news" for item in items) and not curated
    return {
        "tags": tags,
        "specific_tags": specific_tags,
        "politics_hits": politics_hits,
        "hard_news_hits": hard_news_hits,
        "institutional_hits": institutional_hits,
        "visual": visual,
        "social": social,
        "curated": curated,
        "trusted_viral_feed": trusted_viral_feed,
        "strong_viral": strong_viral,
        "generic_news": generic_news,
    }


def valid_http_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = html.unescape(value.strip())
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value




GENERIC_IMAGE_TERMS = (
    "logo", "icon", "avatar", "author", "profile", "favicon", "sprite",
    "placeholder", "default", "fallback", "branding", "brandmark", "banner",
    "header", "footer", "newsletter", "subscription", "suscripcion", "pixel",
    "tracking", "analytics", "advert", "publicidad", "adsystem", "share-button",
    "social-share", "userpic", "gravatar", "emoji", "weather", "generic",
)


def public_fetch_url(value: Any) -> str | None:
    url = valid_http_url(value)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().strip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        return None
    return url


def make_image_candidate(
    value: Any,
    origin: str,
    base_score: float,
    *,
    alt: Any = "",
    width: Any = 0,
    height: Any = 0,
    page_url: str | None = None,
) -> ImageCandidate | None:
    url = public_fetch_url(value)
    if not url:
        return None
    try:
        parsed_width = max(0, int(float(width or 0)))
    except (TypeError, ValueError):
        parsed_width = 0
    try:
        parsed_height = max(0, int(float(height or 0)))
    except (TypeError, ValueError):
        parsed_height = 0
    return ImageCandidate(
        url=url,
        origin=origin,
        base_score=float(base_score),
        alt=strip_html(alt),
        width=parsed_width,
        height=parsed_height,
        page_url=public_fetch_url(page_url),
    )


def dedupe_image_candidates(candidates: Iterable[ImageCandidate | None]) -> tuple[ImageCandidate, ...]:
    best: dict[str, ImageCandidate] = {}
    for candidate in candidates:
        if not candidate:
            continue
        key = html.unescape(candidate.url).replace("&amp;", "&")
        current = best.get(key)
        if current is None or candidate.base_score > current.base_score:
            best[key] = ImageCandidate(
                url=key,
                origin=candidate.origin,
                base_score=candidate.base_score,
                alt=candidate.alt,
                width=candidate.width,
                height=candidate.height,
                page_url=candidate.page_url,
            )
    return tuple(sorted(best.values(), key=lambda item: item.base_score, reverse=True))


def best_srcset_url(value: str, base_url: str) -> str | None:
    options: list[tuple[float, str]] = []
    for part in value.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        candidate = urllib.parse.urljoin(base_url, bits[0])
        weight = 1.0
        if len(bits) > 1:
            descriptor = bits[-1].lower()
            try:
                if descriptor.endswith("w"):
                    weight = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    weight = float(descriptor[:-1]) * 1000
            except ValueError:
                pass
        options.append((weight, candidate))
    if not options:
        return None
    return public_fetch_url(max(options, key=lambda item: item[0])[1])


class InlineImageParser(HTMLParser):
    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.images: list[tuple[str, str, int, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        raw = (
            best_srcset_url(values.get("srcset", "") or values.get("data-srcset", ""), self.base_url)
            or values.get("src")
            or values.get("data-src")
            or values.get("data-lazy-src")
            or values.get("data-original")
        )
        if not raw:
            return
        url = public_fetch_url(urllib.parse.urljoin(self.base_url, raw))
        if not url:
            return
        try:
            width = int(float(values.get("width") or 0))
        except ValueError:
            width = 0
        try:
            height = int(float(values.get("height") or 0))
        except ValueError:
            height = 0
        self.images.append((url, values.get("alt", ""), width, height))


def extract_inline_images(fragment: Any, base_url: str = "") -> list[tuple[str, str, int, int]]:
    if not isinstance(fragment, str) or "<img" not in fragment.lower():
        return []
    parser = InlineImageParser(base_url)
    try:
        parser.feed(fragment)
        parser.close()
    except Exception:
        return []
    return parser.images


def _jsonld_image_values(value: Any, *, context: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, str):
        if public_fetch_url(value):
            found.append((value, context))
    elif isinstance(value, list):
        for item in value:
            found.extend(_jsonld_image_values(item, context=context))
    elif isinstance(value, dict):
        descriptive = str(
            value.get("caption") or value.get("description") or value.get("name") or context or ""
        )
        for key in ("url", "contentUrl", "thumbnailUrl"):
            if key in value:
                found.extend(_jsonld_image_values(value.get(key), context=descriptive))
    return found


def extract_jsonld_candidates(payload: Any, base_url: str) -> list[ImageCandidate]:
    candidates: list[ImageCandidate] = []

    def walk(node: Any, inherited_text: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, inherited_text)
            return
        if not isinstance(node, dict):
            return
        descriptive = str(
            node.get("headline")
            or node.get("caption")
            or node.get("name")
            or node.get("description")
            or inherited_text
            or ""
        )
        for key, score in (
            ("primaryImageOfPage", 104.0),
            ("image", 102.0),
            ("thumbnailUrl", 96.0),
        ):
            if key not in node:
                continue
            for image_url, alt in _jsonld_image_values(node.get(key), context=descriptive):
                candidate = make_image_candidate(
                    urllib.parse.urljoin(base_url, image_url),
                    f"schema:{key}",
                    score,
                    alt=alt,
                    page_url=base_url,
                )
                if candidate:
                    candidates.append(candidate)
        for key, value in node.items():
            if key.lower() in {"logo", "publisher", "author", "creator"}:
                continue
            if isinstance(value, (dict, list)):
                walk(value, descriptive)

    walk(payload)
    return candidates


class PageMetadataParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: list[ImageCandidate] = []
        self.canonical_url: str | None = None
        self.outbound_links: list[str] = []
        self.document_title: str = ""
        self._title_depth = 0
        self._title_parts: list[str] = []
        self._article_depth = 0
        self._main_depth = 0
        self._jsonld_depth = 0
        self._jsonld_parts: list[str] = []
        self._jsonld_documents: list[str] = []
        self._last_og_image_index: int | None = None
        self._last_twitter_image_index: int | None = None

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): value or "" for key, value in attrs}

    def _add(
        self,
        raw_url: Any,
        origin: str,
        score: float,
        *,
        alt: Any = "",
        width: Any = 0,
        height: Any = 0,
    ) -> None:
        if not raw_url:
            return
        candidate = make_image_candidate(
            urllib.parse.urljoin(self.base_url, str(raw_url)),
            origin,
            score,
            alt=alt,
            width=width,
            height=height,
            page_url=self.base_url,
        )
        if candidate:
            self.candidates.append(candidate)
            if origin.startswith("og:image"):
                self._last_og_image_index = len(self.candidates) - 1
            elif origin.startswith("twitter:image"):
                self._last_twitter_image_index = len(self.candidates) - 1

    def _update_candidate_metadata(self, index: int | None, *, alt: str | None = None, width: int | None = None, height: int | None = None) -> None:
        if index is None or index < 0 or index >= len(self.candidates):
            return
        current = self.candidates[index]
        self.candidates[index] = ImageCandidate(
            url=current.url,
            origin=current.origin,
            base_score=current.base_score,
            alt=strip_html(alt) if alt else current.alt,
            width=width if width and width > 0 else current.width,
            height=height if height and height > 0 else current.height,
            page_url=current.page_url,
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        if tag == "article":
            self._article_depth += 1
        if tag == "main":
            self._main_depth += 1
        if tag == "title":
            self._title_depth += 1
            self._title_parts = []
        if tag == "script" and "ld+json" in values.get("type", "").lower():
            self._jsonld_depth += 1
            self._jsonld_parts = []
            return
        if tag == "meta":
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            content = values.get("content") or values.get("value")
            mapping = {
                "og:image": (112.0, "og:image"),
                "og:image:url": (112.0, "og:image:url"),
                "og:image:secure_url": (114.0, "og:image:secure_url"),
                "twitter:image": (108.0, "twitter:image"),
                "twitter:image:src": (108.0, "twitter:image:src"),
                "thumbnail": (88.0, "meta:thumbnail"),
                "thumbnailurl": (94.0, "meta:thumbnailUrl"),
                "image": (90.0, "meta:image"),
            }
            if key in mapping:
                score, origin = mapping[key]
                self._add(content, origin, score, alt=values.get("alt", ""))
            if key in {"og:title", "twitter:title"} and content and not self.document_title:
                self.document_title = strip_html(content)
            if key in {"og:image:alt", "twitter:image:alt"} and content:
                self._update_candidate_metadata(
                    self._last_og_image_index if key.startswith("og:") else self._last_twitter_image_index,
                    alt=content,
                )
            if key in {"og:image:width", "og:image:height"} and content:
                try:
                    numeric = int(float(content))
                except (TypeError, ValueError):
                    numeric = 0
                self._update_candidate_metadata(
                    self._last_og_image_index,
                    width=numeric if key.endswith(":width") else None,
                    height=numeric if key.endswith(":height") else None,
                )
            if key in {"og:url", "twitter:url"} and content:
                resolved = public_fetch_url(urllib.parse.urljoin(self.base_url, content))
                if resolved:
                    self.canonical_url = resolved
            if values.get("http-equiv", "").lower() == "refresh" and content:
                match = re.search(r"url\s*=\s*([^;]+)$", content, flags=re.IGNORECASE)
                if match:
                    resolved = public_fetch_url(urllib.parse.urljoin(self.base_url, match.group(1).strip(" '\"")))
                    if resolved:
                        self.outbound_links.append(resolved)
            return
        if tag == "link":
            rels = {item.lower() for item in values.get("rel", "").split()}
            href = values.get("href")
            if "canonical" in rels and href:
                resolved = public_fetch_url(urllib.parse.urljoin(self.base_url, href))
                if resolved:
                    self.canonical_url = resolved
            if "image_src" in rels:
                self._add(href, "link:image_src", 104.0)
            if "preload" in rels and values.get("as", "").lower() == "image":
                self._add(href, "link:preload", 78.0)
            return
        if tag == "a":
            href = values.get("href")
            if href:
                resolved = public_fetch_url(urllib.parse.urljoin(self.base_url, href))
                if resolved:
                    self.outbound_links.append(resolved)
            return
        if tag != "img" or len(self.candidates) >= 36:
            return
        if values.get("aria-hidden", "").lower() == "true" or values.get("role", "").lower() == "presentation":
            return
        raw = (
            best_srcset_url(values.get("srcset", "") or values.get("data-srcset", ""), self.base_url)
            or values.get("data-original")
            or values.get("data-lazy-src")
            or values.get("data-src")
            or values.get("src")
        )
        score = 70.0 if self._article_depth else 64.0 if self._main_depth else 48.0
        self._add(
            raw,
            "page:article-img" if self._article_depth else "page:main-img" if self._main_depth else "page:img",
            score,
            alt=values.get("alt") or values.get("title") or "",
            width=values.get("width") or 0,
            height=values.get("height") or 0,
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
            if self._title_parts and not self.document_title:
                self.document_title = strip_html(" ".join(self._title_parts))
            self._title_parts = []
        if tag == "article" and self._article_depth:
            self._article_depth -= 1
        if tag == "main" and self._main_depth:
            self._main_depth -= 1
        if tag == "script" and self._jsonld_depth:
            self._jsonld_depth -= 1
            if self._jsonld_parts:
                self._jsonld_documents.append("".join(self._jsonld_parts))
            self._jsonld_parts = []

    def handle_data(self, data: str) -> None:
        if self._jsonld_depth:
            self._jsonld_parts.append(data)
        if self._title_depth:
            self._title_parts.append(data)

    def finish(self) -> tuple[ImageCandidate, ...]:
        for document in self._jsonld_documents:
            try:
                payload = json.loads(document.strip())
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            self.candidates.extend(extract_jsonld_candidates(payload, self.base_url))
        return dedupe_image_candidates(self.candidates)


def _decode_google_news_legacy_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if "news.google." not in (parsed.hostname or ""):
        return None
    match = re.search(r"/(?:articles|read)/([^/?]+)", parsed.path)
    if not match:
        return None
    token = match.group(1)
    try:
        decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, TypeError):
        return None
    found = re.search(rb"https?://[^\x00-\x20\x7f]+", decoded)
    if not found:
        return None
    try:
        candidate = found.group(0).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    candidate = candidate.rstrip("\x01\x02\x03\x04\x05\x06\x07\x08")
    return public_fetch_url(candidate)


def _is_google_host(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host == "google.com" or host.endswith(".google.com") or host.startswith("news.google.")


def select_external_article_link(urls: Iterable[str | None], expected_title: str = "") -> str | None:
    blocked_hosts = {
        "accounts.google.com", "support.google.com", "policies.google.com",
        "www.google.com", "google.com", "youtube.com", "www.youtube.com",
    }
    ranked: list[tuple[float, str]] = []
    for value in urls:
        candidate = public_fetch_url(value)
        if not candidate or _is_google_host(candidate):
            continue
        parsed = urllib.parse.urlparse(candidate)
        host = (parsed.hostname or "").lower()
        if host in blocked_hosts or host.endswith(".googleusercontent.com"):
            continue
        path_parts = [part for part in parsed.path.split("/") if part]
        score = min(8.0, len(path_parts) * 1.5)
        if re.search(r"\d{4}/\d{1,2}/\d{1,2}|\d{4}-\d{1,2}-\d{1,2}", parsed.path):
            score += 5.0
        if any(term in normalize(parsed.path) for term in ("article", "noticia", "viral", "video", "historia")):
            score += 3.0
        shared = keywords(urllib.parse.unquote(parsed.path)) & keywords(expected_title)
        score += min(24.0, len(shared) * 7.0)
        if expected_title and len(shared) < 2:
            score -= 16.0
        if parsed.path in {"", "/"}:
            score -= 12.0
        ranked.append((score, candidate))
    best_score, best_url = max(ranked, default=(-999.0, None), key=lambda item: item[0])
    return best_url if best_score >= 3.0 else None


def page_matches_story(document_title: str, expected_title: str, final_url: str) -> bool:
    """Descarta páginas genéricas o redirecciones que no corresponden al titular."""
    if not expected_title or not document_title:
        return True
    page_words = keywords(document_title)
    story_words = keywords(expected_title)
    if not page_words or not story_words:
        return True
    shared = len(page_words & story_words)
    required = 1 if min(len(page_words), len(story_words)) <= 3 else 2
    if shared >= required:
        return True
    path = urllib.parse.urlparse(final_url).path
    path_shared = len(keywords(urllib.parse.unquote(path)) & story_words)
    if path_shared >= required:
        return True
    # En una portada o página de categoría, una discordancia suele indicar que
    # el enlace caducó o fue redirigido; es preferible no mostrar una imagen.
    return path not in {"", "/"} and shared >= 1


def fetch_html_metadata(url: str, *, expected_title: str = "", _depth: int = 0) -> tuple[str, tuple[ImageCandidate, ...]]:
    target = public_fetch_url(url)
    if not target:
        return url, ()
    legacy = _decode_google_news_legacy_url(target)
    if legacy:
        target = legacy
    request = urllib.request.Request(
        target,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.4",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.4",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=IMAGE_FETCH_TIMEOUT_SECONDS) as response:
        final_url = public_fetch_url(response.geturl()) or target
        content_type = response.headers.get_content_type().lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            return final_url, ()
        payload = response.read(IMAGE_HTML_MAX_BYTES + 1)
        if len(payload) > IMAGE_HTML_MAX_BYTES:
            payload = payload[:IMAGE_HTML_MAX_BYTES]
        charset = response.headers.get_content_charset() or "utf-8"
    document = payload.decode(charset, errors="replace")
    parser = PageMetadataParser(final_url)
    parser.feed(document)
    parser.close()
    candidates = parser.finish()

    # Las URLs de Google News suelen envolver el artículo. Solo seguimos una
    # URL externa cuando es canónica o su slug coincide con el titular; elegir
    # un enlace cualquiera de la portada puede asociar una imagen incorrecta.
    if _is_google_host(final_url) and _depth < 1:
        canonical = public_fetch_url(parser.canonical_url)
        external = canonical if canonical and not _is_google_host(canonical) else None
        if not external:
            external = select_external_article_link(parser.outbound_links, expected_title)
        if external and external != target:
            try:
                return fetch_html_metadata(
                    external,
                    expected_title=expected_title,
                    _depth=_depth + 1,
                )
            except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeError):
                pass
        # No usamos imágenes de la envoltura de Google News: suelen pertenecer
        # a la interfaz, a otra noticia o a una miniatura genérica.
        return final_url, ()

    if not page_matches_story(parser.document_title, expected_title, final_url):
        return final_url, ()
    return final_url, candidates


def resolve_meneame_destination(url: str, expected_title: str) -> str:
    """Devuelve el artículo enlazado, no la ficha o portada de Menéame."""
    target = public_fetch_url(url)
    if not target:
        return url
    host = (urllib.parse.urlparse(target).hostname or "").lower()
    if not (host == "meneame.net" or host.endswith(".meneame.net")):
        return target
    request = urllib.request.Request(
        target,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.4",
            "Accept-Language": "es-ES,es;q=0.9",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=IMAGE_FETCH_TIMEOUT_SECONDS) as response:
            final_url = public_fetch_url(response.geturl()) or target
            if response.headers.get_content_type().lower() not in {"text/html", "application/xhtml+xml"}:
                return final_url
            payload = response.read(IMAGE_HTML_MAX_BYTES + 1)[:IMAGE_HTML_MAX_BYTES]
            charset = response.headers.get_content_charset() or "utf-8"
        parser = PageMetadataParser(final_url)
        parser.feed(payload.decode(charset, errors="replace"))
        parser.close()
        external = select_external_article_link(parser.outbound_links, expected_title)
        return external or final_url
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeError):
        return target


def image_dimensions_and_extension(data: bytes, content_type: str = "") -> tuple[int, int, str] | None:
    if len(data) < 24:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return width, height, ".png"
    if data[:3] == b"GIF" and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little"), ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return width, height, ".webp"
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            return width, height, ".webp"
        if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height, ".webp"
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(data):
                break
            length = int.from_bytes(data[index:index + 2], "big")
            if length < 2 or index + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[index + 3:index + 5], "big")
                width = int.from_bytes(data[index + 5:index + 7], "big")
                return width, height, ".jpg"
            index += length
    if "jpeg" in content_type or "jpg" in content_type:
        return None
    return None


def image_origin_kind(origin: str) -> str:
    return origin.split("destination:", 1)[-1]


def candidate_relevance(candidate: ImageCandidate, story_title: str, *, main_context: bool = False) -> float:
    score = candidate.base_score + (8.0 if main_context else 0.0)
    descriptive = f"{candidate.alt} {urllib.parse.unquote(urllib.parse.urlparse(candidate.url).path)}"
    shared = keywords(descriptive) & keywords(story_title)
    score += min(18.0, len(shared) * 4.5)
    origin_kind = image_origin_kind(candidate.origin)
    if origin_kind == "page:img" and not shared:
        score -= 42.0
    elif origin_kind == "page:main-img" and not shared:
        score -= 20.0
    elif origin_kind == "page:article-img" and not shared:
        score -= 6.0
    elif origin_kind == "link:preload" and not shared:
        score -= 24.0
    normalized_descriptor = normalize(descriptive)
    if any(term in normalized_descriptor for term in GENERIC_IMAGE_TERMS):
        score -= 85.0
    if candidate.width and candidate.height:
        area = candidate.width * candidate.height
        aspect = candidate.width / max(1, candidate.height)
        if area >= 600_000:
            score += 8.0
        elif area >= 200_000:
            score += 4.0
        if 1.35 <= aspect <= 2.1:
            score += 5.0
        if candidate.width < IMAGE_MIN_WIDTH or candidate.height < IMAGE_MIN_HEIGHT:
            score -= 45.0
    return score


def fetch_verified_image(candidate: ImageCandidate, story_title: str, *, main_context: bool) -> dict[str, Any] | None:
    request = urllib.request.Request(
        candidate.url,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.4",
            "Accept-Language": "es-ES,es;q=0.8",
            "Accept-Encoding": "identity",
            "Referer": candidate.page_url or "https://www.google.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=IMAGE_FETCH_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get_content_type().lower()
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > IMAGE_FILE_MAX_BYTES:
            return None
        payload = response.read(IMAGE_FILE_MAX_BYTES + 1)
        if len(payload) > IMAGE_FILE_MAX_BYTES:
            return None
    image_info = image_dimensions_and_extension(payload, content_type)
    if not image_info:
        return None
    width, height, extension = image_info
    area = width * height
    aspect = width / max(1, height)
    if width < IMAGE_MIN_WIDTH or height < IMAGE_MIN_HEIGHT or area < IMAGE_MIN_AREA:
        return None
    if not (IMAGE_MIN_ASPECT <= aspect <= IMAGE_MAX_ASPECT):
        return None
    verified = ImageCandidate(
        url=candidate.url,
        origin=candidate.origin,
        base_score=candidate.base_score,
        alt=candidate.alt,
        width=width,
        height=height,
        page_url=candidate.page_url,
    )
    shared = keywords(
        f"{verified.alt} {urllib.parse.unquote(urllib.parse.urlparse(verified.url).path)}"
    ) & keywords(story_title)
    origin_kind = image_origin_kind(verified.origin)
    if origin_kind == "page:img" and not shared:
        return None
    if origin_kind in {"page:main-img", "link:preload"} and not shared and not main_context:
        return None
    score = candidate_relevance(verified, story_title, main_context=main_context)
    if score < 45.0:
        return None
    if area >= 1_000_000:
        score += 8.0
    elif area >= 400_000:
        score += 5.0
    if 1.4 <= aspect <= 2.0:
        score += 4.0
    return {
        "payload": payload,
        "extension": extension,
        "width": width,
        "height": height,
        "score": score,
        "origin": candidate.origin,
        "remote_url": candidate.url,
        "alt": candidate.alt,
    }


def serialize_candidate(candidate: ImageCandidate) -> dict[str, Any]:
    return {
        "url": candidate.url,
        "origin": candidate.origin,
        "base_score": candidate.base_score,
        "alt": candidate.alt,
        "width": candidate.width,
        "height": candidate.height,
        "page_url": candidate.page_url,
    }


def deserialize_candidate(value: Any) -> ImageCandidate | None:
    if not isinstance(value, dict):
        return None
    return make_image_candidate(
        value.get("url"),
        str(value.get("origin") or "unknown"),
        float(value.get("base_score") or 0),
        alt=value.get("alt") or "",
        width=value.get("width") or 0,
        height=value.get("height") or 0,
        page_url=value.get("page_url"),
    )


def destination_link_candidates(url: str | None, title: str) -> tuple[ImageCandidate, ...]:
    """Candidatos derivados directamente del enlace destino de Menéame."""
    link = public_fetch_url(url)
    if not link:
        return ()
    parsed = urllib.parse.urlparse(link)
    host = (parsed.hostname or "").lower()
    candidates: list[ImageCandidate | None] = []
    if re.search(r"\.(?:jpe?g|png|gif|webp)(?:$|\?)", link, flags=re.IGNORECASE):
        candidates.append(
            make_image_candidate(
                link,
                "destination:direct-image",
                138.0,
                alt=title,
                page_url=link,
            )
        )
    video_id = None
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            video_id = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/")):
            parts = [part for part in parsed.path.split("/") if part]
            video_id = parts[1] if len(parts) > 1 else None
    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
        for name, score in (("maxresdefault", 136.0), ("sddefault", 132.0), ("hqdefault", 126.0)):
            candidates.append(
                make_image_candidate(
                    f"https://i.ytimg.com/vi/{video_id}/{name}.jpg",
                    "destination:youtube-thumbnail",
                    score,
                    alt=title,
                    page_url=link,
                )
            )
    return dedupe_image_candidates(candidates)


def _context_candidates(context: dict[str, Any], story_title: str) -> tuple[ImageCandidate, ...]:
    candidates: list[ImageCandidate | None] = [
        deserialize_candidate(item) for item in context.get("candidates", [])
    ]
    thumbnail = context.get("thumbnail")
    if thumbnail:
        platform = str(context.get("platform") or "")
        base = {
            "youtube": 124.0,
            "reddit": 119.0,
            "bluesky": 119.0,
            "mastodon": 119.0,
            "meneame": 72.0,
            "news": 90.0,
        }.get(platform, 82.0)
        candidates.append(
            make_image_candidate(
                thumbnail,
                f"{platform}:primary",
                base,
                alt=context.get("title") or story_title,
                page_url=context.get("link"),
            )
        )
    return dedupe_image_candidates(candidates)


def enrich_one_story_image(story: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    contexts = story.get("_image_contexts") if isinstance(story.get("_image_contexts"), list) else []
    candidates: list[tuple[ImageCandidate, bool]] = []
    for context in contexts:
        if not isinstance(context, dict):
            continue
        is_main = bool(context.get("is_main"))
        if context.get("force_destination_image"):
            continue
        candidates.extend((candidate, is_main) for candidate in _context_candidates(context, story["title"]))

    page_contexts = sorted(
        [context for context in contexts if isinstance(context, dict)],
        key=lambda context: (
            bool(context.get("force_destination_image")),
            bool(context.get("is_main")),
            context.get("platform") in {"news", "meneame"},
            bool(context.get("candidates")),
        ),
        reverse=True,
    )
    fetched_pages: set[str] = set()
    for context in page_contexts[:IMAGE_PAGE_CONTEXT_LIMIT]:
        platform = str(context.get("platform") or "")
        direct_candidates = _context_candidates(context, story["title"])
        has_trusted_direct = any(item.base_score >= 115 for item in direct_candidates)
        if has_trusted_direct and platform not in {"news", "meneame"}:
            continue
        link = public_fetch_url(context.get("link"))
        if not link or link in fetched_pages:
            continue
        if platform == "meneame":
            candidates.extend(
                (candidate, bool(context.get("is_main")))
                for candidate in destination_link_candidates(
                    link,
                    str(context.get("title") or story["title"]),
                )
            )
        fetched_pages.add(link)
        try:
            final_url, page_candidates = fetch_html_metadata(
                link,
                expected_title=str(context.get("title") or story["title"]),
            )
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, UnicodeError, ValueError):
            continue
        for candidate in page_candidates:
            if platform == "meneame":
                image_host = (urllib.parse.urlparse(candidate.url).hostname or "").lower()
                page_host = (urllib.parse.urlparse(final_url).hostname or "").lower()
                # Las miniaturas de la portada de Menéame viven en mnmstatic y
                # pueden no coincidir con la imagen principal del artículo.
                if image_host.endswith("mnmstatic.net") and not page_host.endswith("meneame.net"):
                    continue
            if candidate.page_url is None:
                candidate = ImageCandidate(
                    url=candidate.url,
                    origin=(f"destination:{candidate.origin}" if platform == "meneame" else candidate.origin),
                    base_score=candidate.base_score + (18.0 if platform == "meneame" else 0.0),
                    alt=candidate.alt or str(context.get("title") or ""),
                    width=candidate.width,
                    height=candidate.height,
                    page_url=final_url,
                )
            elif platform == "meneame":
                candidate = ImageCandidate(
                    url=candidate.url,
                    origin=f"destination:{candidate.origin}",
                    base_score=candidate.base_score + 18.0,
                    alt=candidate.alt or str(context.get("title") or ""),
                    width=candidate.width,
                    height=candidate.height,
                    page_url=final_url,
                )
            candidates.append((candidate, bool(context.get("is_main"))))

    # Conserva la mejor puntuación por URL y recuerda si procede del elemento principal.
    best_by_url: dict[str, tuple[ImageCandidate, bool, float]] = {}
    for candidate, is_main in candidates:
        pre_score = candidate_relevance(candidate, story["title"], main_context=is_main)
        current = best_by_url.get(candidate.url)
        if current is None or pre_score > current[2]:
            best_by_url[candidate.url] = (candidate, is_main, pre_score)
    ordered = sorted(best_by_url.values(), key=lambda item: item[2], reverse=True)

    verified: list[dict[str, Any]] = []
    for candidate, is_main, _ in ordered[:IMAGE_CANDIDATE_LIMIT]:
        try:
            result = fetch_verified_image(candidate, story["title"], main_context=is_main)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            result = None
        if result:
            verified.append(result)
            if result["score"] >= 132.0 and len(verified) >= 2:
                break
        if len(verified) >= 4:
            break

    updated = dict(story)
    updated.pop("_image_contexts", None)
    if not verified:
        updated["thumbnail"] = None
        updated["image_verified"] = False
        return updated, None

    selected = max(verified, key=lambda item: item["score"])
    digest = hashlib.sha256(selected["payload"]).hexdigest()[:24]
    filename = f"{digest}{selected['extension']}"
    destination = MEDIA_DIR / filename
    if not destination.exists():
        fd, tmp_name = tempfile.mkstemp(prefix="image-", suffix=selected["extension"], dir=MEDIA_DIR)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(selected["payload"])
            os.replace(tmp_name, destination)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
    updated["thumbnail"] = f"media/{filename}"
    updated["image_verified"] = True
    updated["image_origin"] = selected["origin"]
    updated["image_width"] = selected["width"]
    updated["image_height"] = selected["height"]
    updated["image_alt"] = selected.get("alt") or story.get("title") or ""
    return updated, selected["origin"]


def enrich_ranked_images(stories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    for child in MEDIA_DIR.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)

    output: list[dict[str, Any] | None] = [None] * len(stories)
    origins: dict[str, int] = {}
    limit = min(len(stories), IMAGE_ENRICH_LIMIT)
    with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as executor:
        futures = {
            executor.submit(enrich_one_story_image, stories[index]): index
            for index in range(limit)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                updated, origin = future.result()
            except Exception as exc:
                updated = dict(stories[index])
                updated.pop("_image_contexts", None)
                updated["thumbnail"] = None
                updated["image_verified"] = False
                print(f"[aviso] Imagen #{index + 1}: {exc}")
                origin = None
            output[index] = updated
            if origin:
                origins[origin] = origins.get(origin, 0) + 1

    for index in range(limit, len(stories)):
        updated = dict(stories[index])
        updated.pop("_image_contexts", None)
        updated["thumbnail"] = None
        updated["image_verified"] = False
        output[index] = updated

    final = [item for item in output if item is not None]
    verified_count = sum(1 for item in final if item.get("image_verified"))
    print(f"[ok] Previsualizaciones: {verified_count}/{len(final)} verificadas y almacenadas localmente")
    return final, {
        "verified": verified_count,
        "total": len(final),
        "cached_files": len(list(MEDIA_DIR.glob("*"))),
        "origins": origins,
    }

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




def parse_publication_date(value: Any) -> dt.datetime | None:
    """Interpreta fechas ISO, RFC 2822 o timestamps Unix de metadatos web."""
    if isinstance(value, (int, float)):
        try:
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
        except (OSError, OverflowError, TypeError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = html.unescape(value).strip()
    if cleaned.isdigit():
        return parse_publication_date(int(cleaned))
    parsed = parse_iso_datetime(cleaned)
    if parsed:
        return parsed
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def is_within_content_window(
    published_at: dt.datetime | None,
    now: dt.datetime,
) -> bool:
    """Exige fecha conocida y una antigüedad máxima estricta de 24 horas."""
    if published_at is None:
        return False
    value = published_at.astimezone(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=CONTENT_MAX_AGE_HOURS)
    future_limit = now + dt.timedelta(minutes=FUTURE_CLOCK_SKEW_MINUTES)
    return cutoff <= value <= future_limit


def _jsonld_publication_dates(value: Any) -> list[dt.datetime]:
    dates: list[dt.datetime] = []
    if isinstance(value, list):
        for item in value:
            dates.extend(_jsonld_publication_dates(item))
        return dates
    if not isinstance(value, dict):
        return dates
    for key in ("datePublished", "uploadDate", "dateCreated", "datepublished"):
        parsed = parse_publication_date(value.get(key))
        if parsed:
            dates.append(parsed)
    for child in value.values():
        if isinstance(child, (dict, list)):
            dates.extend(_jsonld_publication_dates(child))
    return dates


class PublicationDateParser(HTMLParser):
    """Extrae la fecha editorial del artículo destino sin depender del diseño."""

    DATE_KEYS = {
        "article:published_time", "og:published_time", "datepublished",
        "date_published", "publishdate", "pubdate", "publication_date",
        "datecreated", "uploadDate", "date",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.dates: list[dt.datetime] = []
        self._jsonld_depth = 0
        self._jsonld_parts: list[str] = []
        self._jsonld_documents: list[str] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): value or "" for key, value in attrs}

    def _add(self, value: Any) -> None:
        parsed = parse_publication_date(value)
        if parsed:
            self.dates.append(parsed)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        if tag == "script" and "ld+json" in values.get("type", "").lower():
            self._jsonld_depth += 1
            self._jsonld_parts = []
            return
        if tag == "meta":
            key = (
                values.get("property") or values.get("name")
                or values.get("itemprop") or ""
            ).strip().lower()
            if key in {item.lower() for item in self.DATE_KEYS}:
                self._add(values.get("content") or values.get("value"))
            return
        if tag == "time":
            self._add(values.get("datetime") or values.get("data-time") or values.get("data-ts"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._jsonld_depth:
            self._jsonld_depth -= 1
            if self._jsonld_parts:
                self._jsonld_documents.append("".join(self._jsonld_parts))
            self._jsonld_parts = []

    def handle_data(self, data: str) -> None:
        if self._jsonld_depth:
            self._jsonld_parts.append(data)

    def finish(self) -> list[dt.datetime]:
        for document in self._jsonld_documents:
            try:
                payload = json.loads(document.strip())
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            self.dates.extend(_jsonld_publication_dates(payload))
        unique = sorted(set(self.dates), reverse=True)
        return unique


def fetch_publication_date(url: str) -> dt.datetime | None:
    target = public_fetch_url(url)
    if not target:
        return None
    request = urllib.request.Request(
        target,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "es-ES,es;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=IMAGE_FETCH_TIMEOUT_SECONDS) as response:
            content_type = str(response.headers.get("Content-Type", "")).lower()
            if "html" not in content_type:
                return None
            payload = response.read(PUBLICATION_DATE_HTML_MAX_BYTES + 1)[:PUBLICATION_DATE_HTML_MAX_BYTES]
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    parser = PublicationDateParser()
    try:
        parser.feed(payload.decode("utf-8", errors="replace"))
        parser.close()
    except Exception:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    dates = [date for date in parser.finish() if date <= now + dt.timedelta(minutes=FUTURE_CLOCK_SKEW_MINUTES)]
    return max(dates, default=None)


def enrich_missing_publication_dates(
    entries: list[StoryEntry],
) -> tuple[list[StoryEntry], dict[str, int]]:
    """Completa fechas ausentes desde el artículo destino antes del filtro."""
    candidates = [
        (index, entry)
        for index, entry in enumerate(entries)
        if entry.platform == "meneame"
        or (entry.published_at is None and entry.platform in {"news", "mastodon"})
    ]
    priority = {"meneame": 0, "news": 1, "mastodon": 2}
    candidates.sort(
        key=lambda pair: (
            priority.get(pair[1].platform, 9),
            0 if pair[1].metrics.get("curated_editorial") else 1,
        )
    )
    candidates = candidates[:PUBLICATION_DATE_ENRICH_LIMIT]
    if not candidates:
        return entries, {"attempted": 0, "resolved": 0}

    dates_by_url: dict[str, dt.datetime | None] = {}
    unique_urls = list(dict.fromkeys(entry.link for _, entry in candidates))
    with ThreadPoolExecutor(max_workers=PUBLICATION_DATE_WORKERS) as executor:
        futures = {executor.submit(fetch_publication_date, url): url for url in unique_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                dates_by_url[url] = future.result()
            except Exception:
                dates_by_url[url] = None

    output = list(entries)
    resolved = 0
    for index, entry in candidates:
        published_at = dates_by_url.get(entry.link)
        if published_at:
            output[index] = replace(entry, published_at=published_at)
            resolved += 1
        elif entry.platform == "meneame":
            # La fecha de Menéame corresponde al envío, no necesariamente a la
            # publicación original. Sin fecha verificable en el destino se descarta.
            output[index] = replace(entry, published_at=None)
    print(f"[ok] Fechas editoriales: {resolved}/{len(candidates)} ausentes recuperadas desde el destino")
    return output, {"attempted": len(candidates), "resolved": resolved}


def filter_recent_entries(
    entries: list[StoryEntry],
    now: dt.datetime,
) -> tuple[list[StoryEntry], dict[str, int]]:
    recent: list[StoryEntry] = []
    missing = 0
    old = 0
    future = 0
    cutoff = now - dt.timedelta(hours=CONTENT_MAX_AGE_HOURS)
    future_limit = now + dt.timedelta(minutes=FUTURE_CLOCK_SKEW_MINUTES)
    for entry in entries:
        published_at = entry.published_at
        if published_at is None:
            missing += 1
            continue
        value = published_at.astimezone(dt.timezone.utc)
        if value < cutoff:
            old += 1
            continue
        if value > future_limit:
            future += 1
            continue
        recent.append(entry)
    print(
        f"[ok] Ventana de 24 h: {len(recent)}/{len(entries)} contenidos válidos · "
        f"{old} antiguos · {missing} sin fecha · {future} con fecha futura"
    )
    return recent, {
        "accepted": len(recent), "total": len(entries), "old": old,
        "missing_date": missing, "future_date": future,
    }


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



def meneame_social_points(
    meneos: int,
    comments: int,
    clicks: int,
    published_at: dt.datetime | None,
    section: str,
) -> float:
    """Convierte las señales visibles de Menéame en puntos comparables."""
    now = dt.datetime.now(dt.timezone.utc)
    if section == "top_visited":
        weighted = clicks + meneos * 7 + comments * 4
        points = (
            math.log10(clicks + 1) * 7.5
            + math.log10(meneos + 1) * 7.0
            + math.log10(comments + 1) * 4.0
            + 3.0
        )
    else:
        weighted = meneos * 8 + comments * 5 + clicks * 0.25
        points = (
            math.log10(meneos + 1) * 10.0
            + math.log10(comments + 1) * 5.0
            + math.log10(clicks + 1) * 2.5
            + 4.0
        )
    points += velocity_bonus(weighted, published_at, now)
    return min(58.0, points)


def parse_meneame_count(text: str, label: str) -> int:
    match = re.search(rf"([\d.]+)\s+{label}", text, flags=re.IGNORECASE)
    if not match:
        return 0
    try:
        return max(0, int(match.group(1).replace(".", "")))
    except ValueError:
        return 0


class MeneamePageParser(HTMLParser):
    """Extrae titulares y métricas de las listas públicas de Menéame.

    Se apoya en elementos semánticos (h2/h3, enlaces y texto de métricas),
    evitando selectores CSS frágiles ligados al diseño visual de la página.
    """

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self._heading_tag: str | None = None
        self._heading_link: str | None = None
        self._heading_text: list[str] = []
        self._current: dict[str, Any] | None = None

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def _flush_current(self) -> None:
        if not self._current:
            return
        title = " ".join(self._current.get("title_parts", [])).strip()
        link = self._current.get("link")
        text = " ".join(self._current.get("text_parts", []))
        meneos = parse_meneame_count(text, r"meneos?")
        comments = parse_meneame_count(text, r"comentarios?")
        clicks = parse_meneame_count(text, r"clics?")
        # Exige al menos una métrica para descartar encabezados de navegación.
        if title and link and (meneos or comments or clicks):
            self.items.append(
                {
                    "title": title,
                    "link": link,
                    "text": text,
                    "meneos": meneos,
                    "comments": comments,
                    "clicks": clicks,
                    "published_at": self._current.get("published_at"),
                    "thumbnail": self._current.get("thumbnail"),
                }
            )
        self._current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        if tag in {"h2", "h3"}:
            self._flush_current()
            self._heading_tag = tag
            self._heading_link = None
            self._heading_text = []
            return

        if self._heading_tag and tag == "a" and not self._heading_link:
            href = values.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:")):
                candidate = urllib.parse.urljoin(self.base_url, href)
                parsed = urllib.parse.urlparse(candidate)
                # Descarta enlaces de navegación, usuarios y categorías.
                blocked_paths = (
                    "/user/",
                    "/m/",
                    "/popular",
                    "/top_visited",
                    "/queue",
                    "/search",
                    "/login",
                )
                if parsed.scheme in {"http", "https"} and not any(
                    parsed.path.startswith(path) for path in blocked_paths
                ):
                    self._heading_link = candidate
            return

        if not self._current:
            return

        if tag == "time":
            raw_date = values.get("datetime") or values.get("data-time") or values.get("data-ts")
            parsed_date = parse_iso_datetime(raw_date)
            if not parsed_date and raw_date and raw_date.isdigit():
                timestamp = int(raw_date)
                if timestamp > 10_000_000_000:
                    timestamp //= 1000
                try:
                    parsed_date = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
                except (OverflowError, OSError, ValueError):
                    parsed_date = None
            if parsed_date:
                self._current["published_at"] = parsed_date

        if tag == "img" and not self._current.get("thumbnail"):
            candidate = values.get("src") or values.get("data-src") or values.get("data-original")
            if candidate:
                self._current["thumbnail"] = valid_http_url(
                    urllib.parse.urljoin(self.base_url, candidate)
                )

    def handle_endtag(self, tag: str) -> None:
        if self._heading_tag == tag:
            title = " ".join(self._heading_text).strip()
            if title and self._heading_link:
                self._current = {
                    "title_parts": [title],
                    "link": self._heading_link,
                    "text_parts": [],
                    "published_at": None,
                    "thumbnail": None,
                }
            self._heading_tag = None
            self._heading_link = None
            self._heading_text = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._heading_tag:
            self._heading_text.append(value)
        elif self._current:
            self._current["text_parts"].append(value)

    def close(self) -> None:
        super().close()
        self._flush_current()


def infer_meneame_media_type(link: str, title: str) -> str:
    value = f"{link} {normalize(title)}".lower()
    if any(token in value for token in ("youtube.com", "youtu.be", "tiktok.com", "vimeo.com", " video ")):
        return "video"
    if re.search(r"\.(?:jpg|jpeg|png|gif|webp)(?:\?|$)", link, flags=re.IGNORECASE):
        return "image"
    return "article"


def fetch_meneame_entries() -> tuple[list[StoryEntry], list[str], list[dict[str, Any]]]:
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=NEWS_MAX_AGE_HOURS)
    seen: set[tuple[str, str]] = set()

    for source_name, url, section in MENEAME_SECTIONS:
        try:
            page = fetch_bytes(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                    "Accept-Language": "es-ES,es;q=0.9",
                },
            ).decode("utf-8", errors="replace")
            parser = MeneamePageParser(url)
            parser.feed(page)
            parser.close()
            if not parser.items:
                warnings.append(
                    f"{source_name} no devolvió titulares parseables; puede haber cambiado su HTML."
                )
                statuses.append({"name": source_name, "ok": False, "items": 0})
                continue
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            warnings.append(f"No se pudo descargar {source_name}: {exc}")
            statuses.append({"name": source_name, "ok": False, "items": 0})
            continue

        accepted = 0
        for raw in parser.items:
            title = compact_text(str(raw.get("title", "")).strip(), 220)
            link = valid_http_url(raw.get("link"))
            if link:
                link = resolve_meneame_destination(link, title)
            if not title or not link or is_blocked_content(title):
                continue
            published_at = raw.get("published_at")
            if isinstance(published_at, dt.datetime) and published_at < cutoff:
                continue
            title_keywords = keywords(title)
            if not title_keywords:
                continue
            dedupe_key = (normalize(title), source_name.casefold())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            meneos = int(raw.get("meneos") or 0)
            comments = int(raw.get("comments") or 0)
            clicks = int(raw.get("clicks") or 0)
            entries.append(
                StoryEntry(
                    title=title,
                    link=link,
                    source=source_name,
                    platform="meneame",
                    published_at=published_at if isinstance(published_at, dt.datetime) else None,
                    keywords=title_keywords,
                    social_points=meneame_social_points(
                        meneos,
                        comments,
                        clicks,
                        published_at if isinstance(published_at, dt.datetime) else None,
                        section,
                    ),
                    metrics={
                        "meneos": meneos,
                        "comments": comments,
                        "clicks": clicks,
                        "section": section,
                    },
                    # No reutilizamos la miniatura de la portada de Menéame.
                    # La imagen se extrae posteriormente del artículo destino.
                    thumbnail=None,
                    image_candidates=(),
                    media_type=infer_meneame_media_type(link, title),
                )
            )
            accepted += 1

        statuses.append({"name": source_name, "ok": True, "items": accepted})
        print(f"[ok] {source_name}: {accepted} elementos")

    return entries, warnings, statuses


def extract_feed_image_candidates(entry: Any) -> tuple[ImageCandidate, ...]:
    candidates: list[ImageCandidate | None] = []
    for field_name, score in (("media_content", 98.0), ("media_thumbnail", 94.0)):
        media = entry.get(field_name)
        if not isinstance(media, list):
            continue
        for item in media:
            if not isinstance(item, dict):
                continue
            candidates.append(
                make_image_candidate(
                    item.get("url"),
                    f"feed:{field_name}",
                    score,
                    alt=item.get("description") or item.get("title") or "",
                    width=item.get("width") or 0,
                    height=item.get("height") or 0,
                    page_url=entry.get("link"),
                )
            )
    enclosure = entry.get("enclosures")
    if isinstance(enclosure, list):
        for item in enclosure:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).lower()
            href = item.get("href") or item.get("url")
            if item_type.startswith("image/") or re.search(r"\.(?:jpe?g|png|gif|webp)(?:\?|$)", str(href), re.I):
                candidates.append(make_image_candidate(href, "feed:enclosure", 96.0, page_url=entry.get("link")))
    for field_name in ("summary", "description"):
        for url, alt, width, height in extract_inline_images(entry.get(field_name), str(entry.get("link") or "")):
            candidates.append(
                make_image_candidate(
                    url,
                    f"feed:{field_name}-img",
                    84.0,
                    alt=alt,
                    width=width,
                    height=height,
                    page_url=entry.get("link"),
                )
            )
    content = entry.get("content")
    if isinstance(content, list):
        for block in content:
            value = block.get("value") if isinstance(block, dict) else None
            for url, alt, width, height in extract_inline_images(value, str(entry.get("link") or "")):
                candidates.append(
                    make_image_candidate(
                        url,
                        "feed:content-img",
                        88.0,
                        alt=alt,
                        width=width,
                        height=height,
                        page_url=entry.get("link"),
                    )
                )
    return dedupe_image_candidates(candidates)


def extract_feed_thumbnail(entry: Any) -> str | None:
    candidates = extract_feed_image_candidates(entry)
    return candidates[0].url if candidates else None


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



SECTION_GENERIC_TITLES = {
    "viral", "virales", "curiosidades", "últimas noticias", "ultima hora",
    "ver más", "ver mas", "más información", "mas informacion", "inicio",
    "noticias", "vídeos", "videos", "redes sociales", "publicidad",
}


def best_srcset_url(value: str | None) -> str | None:
    if not value:
        return None
    options: list[tuple[float, str]] = []
    for part in value.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        url = bits[0]
        weight = 0.0
        if len(bits) > 1:
            descriptor = bits[-1].lower()
            try:
                if descriptor.endswith("w"):
                    weight = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    weight = float(descriptor[:-1]) * 1000
            except ValueError:
                pass
        options.append((weight, url))
    if not options:
        return None
    return max(options, key=lambda item: item[0])[1]


class SectionListingParser(HTMLParser):
    """Extrae titulares de una portada editorial sin depender de sus clases CSS."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.main_depth = 0
        self.article_depth = 0
        self.heading_depth = 0
        self.current_anchor: dict[str, Any] | None = None
        self.anchors: list[dict[str, Any]] = []
        self.in_jsonld = False
        self.jsonld_buffer: list[str] = []
        self.jsonld_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "main":
            self.main_depth += 1
        if tag == "article":
            self.article_depth += 1
        if tag in {"h1", "h2", "h3", "h4"}:
            self.heading_depth += 1
        if tag == "script" and "ld+json" in attr.get("type", "").lower():
            self.in_jsonld = True
            self.jsonld_buffer = []
        if tag == "a" and attr.get("href"):
            self.current_anchor = {
                "href": urllib.parse.urljoin(self.base_url, attr["href"]),
                "text": [],
                "heading": [],
                "images": [],
                "in_main": self.main_depth > 0,
                "in_article": self.article_depth > 0,
                "aria": attr.get("aria-label") or attr.get("title") or "",
                "published_at": None,
            }
        elif tag == "time" and self.current_anchor is not None:
            self.current_anchor["published_at"] = parse_publication_date(
                attr.get("datetime") or attr.get("data-time") or attr.get("data-ts")
            )
        elif tag == "img" and self.current_anchor is not None:
            src = (
                best_srcset_url(attr.get("srcset") or attr.get("data-srcset"))
                or attr.get("data-original")
                or attr.get("data-src")
                or attr.get("loading-src")
                or attr.get("src")
            )
            if src:
                self.current_anchor["images"].append(
                    {
                        "url": urllib.parse.urljoin(self.base_url, src),
                        "alt": attr.get("alt") or attr.get("title") or "",
                        "width": parse_human_count(attr.get("width")),
                        "height": parse_human_count(attr.get("height")),
                    }
                )

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self.jsonld_buffer.append(data)
        if self.current_anchor is not None:
            value = " ".join(data.split())
            if value:
                self.current_anchor["text"].append(value)
                if self.heading_depth:
                    self.current_anchor["heading"].append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self.current_anchor is not None:
            self.anchors.append(self.current_anchor)
            self.current_anchor = None
        if tag == "script" and self.in_jsonld:
            self.jsonld_blocks.append("".join(self.jsonld_buffer).strip())
            self.in_jsonld = False
            self.jsonld_buffer = []
        if tag in {"h1", "h2", "h3", "h4"} and self.heading_depth:
            self.heading_depth -= 1
        if tag == "article" and self.article_depth:
            self.article_depth -= 1
        if tag == "main" and self.main_depth:
            self.main_depth -= 1


def jsonld_url(value: Any) -> str | None:
    if isinstance(value, str):
        return valid_http_url(value)
    if isinstance(value, dict):
        return valid_http_url(value.get("url") or value.get("@id"))
    return None


def jsonld_image(value: Any) -> str | None:
    if isinstance(value, str):
        return valid_http_url(value)
    if isinstance(value, list):
        for item in value:
            result = jsonld_image(item)
            if result:
                return result
    if isinstance(value, dict):
        return valid_http_url(value.get("url") or value.get("contentUrl") or value.get("@id"))
    return None


def iter_jsonld_articles(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from iter_jsonld_articles(item)
        return
    if not isinstance(value, dict):
        return
    raw_type = value.get("@type")
    types = {str(item).lower() for item in raw_type} if isinstance(raw_type, list) else {str(raw_type).lower()}
    if types & {"article", "newsarticle", "reportagenewsarticle", "blogposting", "videoobject"}:
        yield value
    if "listitem" in types and isinstance(value.get("item"), dict):
        yield from iter_jsonld_articles(value["item"])
    for key in ("@graph", "itemListElement", "mainEntity", "hasPart"):
        child = value.get(key)
        if isinstance(child, (list, dict)):
            yield from iter_jsonld_articles(child)


def section_host_matches(url: str, section_url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.")
    section_host = (urllib.parse.urlparse(section_url).hostname or "").lower().removeprefix("www.")
    return bool(host and section_host and (host == section_host or host.endswith("." + section_host)))


def looks_like_section_article(url: str, section_url: str) -> bool:
    if not section_host_matches(url, section_url):
        return False
    parsed = urllib.parse.urlparse(url)
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    section_path = re.sub(r"/+", "/", urllib.parse.urlparse(section_url).path).rstrip("/")
    if not path or path == section_path:
        return False
    lowered = path.casefold()
    if any(piece in lowered for piece in ("/tag/", "/temas/", "/autor/", "/authors/", "/contact", "/rss")):
        return False
    parts = [part for part in path.split("/") if part]
    if len(parts) < 3:
        return False
    return bool(
        re.search(r"/20\d{2}(?:/|\d{4})", path)
        or re.search(r"_20\d{6,}", path)
        or path.endswith(".html")
        or len(parts) >= 5
    )


def clean_section_title(value: str) -> str:
    value = compact_text(strip_html(value), 220)
    value = re.sub(r"^(?:vídeo|video|viral|virales|tiktok)\s*:\s*", "", value, flags=re.I)
    return value.strip(" -–—|·")


def parse_section_listing(payload: bytes, section_url: str) -> list[dict[str, Any]]:
    parser = SectionListingParser(section_url)
    parser.feed(payload.decode("utf-8", errors="replace"))
    candidates: list[dict[str, Any]] = []

    for block in parser.jsonld_blocks:
        if not block:
            continue
        try:
            decoded = json.loads(block)
        except json.JSONDecodeError:
            continue
        for article in iter_jsonld_articles(decoded):
            link = jsonld_url(article.get("url") or article.get("mainEntityOfPage"))
            title = clean_section_title(str(article.get("headline") or article.get("name") or ""))
            if not link or not title or not looks_like_section_article(link, section_url):
                continue
            candidates.append(
                {
                    "title": title,
                    "link": link,
                    "published_at": parse_iso_datetime(article.get("datePublished")),
                    "image": jsonld_image(article.get("image") or article.get("thumbnailUrl")),
                    "image_alt": title,
                    "score": 20,
                    "origin": "jsonld",
                }
            )

    for anchor in parser.anchors:
        link = valid_http_url(anchor.get("href"))
        if not link or not looks_like_section_article(link, section_url):
            continue
        images = anchor.get("images") if isinstance(anchor.get("images"), list) else []
        image_alt = next((str(item.get("alt") or "").strip() for item in images if item.get("alt")), "")
        options = [
            " ".join(anchor.get("heading") or []),
            str(anchor.get("aria") or ""),
            image_alt,
            " ".join(anchor.get("text") or []),
        ]
        title = next((clean_section_title(item) for item in options if len(clean_section_title(item)) >= 24), "")
        if not title or normalize(title) in {normalize(item) for item in SECTION_GENERIC_TITLES}:
            continue
        score = 0
        score += 8 if anchor.get("in_article") else 0
        score += 5 if anchor.get("in_main") else 0
        score += 6 if anchor.get("heading") else 0
        score += 2 if images else 0
        candidates.append(
            {
                "title": title,
                "link": link,
                "published_at": anchor.get("published_at") if isinstance(anchor.get("published_at"), dt.datetime) else None,
                "image": images[0].get("url") if images else None,
                "image_alt": image_alt or title,
                "image_width": images[0].get("width") if images else 0,
                "image_height": images[0].get("height") if images else 0,
                "score": score,
                "origin": "html",
            }
        )

    best_by_link: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate["link"].split("#", 1)[0]
        previous = best_by_link.get(key)
        if previous is None or candidate.get("score", 0) > previous.get("score", 0):
            best_by_link[key] = candidate
    ordered = sorted(best_by_link.values(), key=lambda item: item.get("score", 0), reverse=True)
    return ordered[:MAX_NEWS_ITEMS_PER_SOURCE]


def feed_fallback_for_section(
    *,
    status_name: str,
    fallback_url: str,
    editorial_boost: float,
    editorial_section: str,
    configured_tags: tuple[str, ...],
    cutoff: dt.datetime,
    seen: set[tuple[str, str]],
    limit: int,
) -> list[StoryEntry]:
    try:
        feed = fetch_feed(fallback_url)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return []
    result: list[StoryEntry] = []
    for raw in feed.entries:
        raw_title = str(raw.get("title", "")).strip()
        link = valid_http_url(raw.get("link"))
        if not raw_title or not link:
            continue
        source = extract_publisher(raw, status_name)
        title = clean_google_title(raw_title, source)
        published_at = parse_published(raw)
        if published_at and published_at < cutoff:
            continue
        key = (normalize(title), source.casefold())
        if key in seen or is_blocked_content(title):
            continue
        seen.add(key)
        image_candidates = extract_feed_image_candidates(raw)
        result.append(
            StoryEntry(
                title=compact_text(title, 220),
                link=link,
                source=source,
                platform="news",
                published_at=published_at,
                keywords=keywords(title),
                social_points=editorial_boost,
                metrics={
                    "curated_editorial": True,
                    "editorial_section": editorial_section,
                    "editorial_feed": status_name,
                    "topic_tags": sorted(set(configured_tags)),
                    "source_mode": "google-news-fallback",
                },
                thumbnail=image_candidates[0].url if image_candidates else None,
                image_candidates=image_candidates,
                media_type="article",
            )
        )
        if len(result) >= limit:
            break
    return result


def fetch_direct_section_entries(
    cutoff: dt.datetime,
    seen: set[tuple[str, str]],
) -> tuple[list[StoryEntry], list[str], list[dict[str, Any]]]:
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    for status_name, publisher, section_url, fallback_url, boost, section, tags in DIRECT_SECTION_SOURCES:
        direct_items: list[dict[str, Any]] = []
        direct_error: Exception | None = None
        try:
            payload = fetch_bytes(
                section_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                    "Accept-Language": "es-ES,es;q=0.9",
                },
            )
            direct_items = parse_section_listing(payload, section_url)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            direct_error = exc

        accepted = 0
        for item in direct_items:
            title = clean_section_title(str(item.get("title") or ""))
            link = valid_http_url(item.get("link"))
            if not title or not link or is_blocked_content(title):
                continue
            published_at = item.get("published_at") if isinstance(item.get("published_at"), dt.datetime) else None
            if published_at and published_at < cutoff:
                continue
            key = (normalize(title), publisher.casefold())
            if key in seen:
                continue
            seen.add(key)
            detected_tags = classify_topic_tags(title, tags)
            candidate = make_image_candidate(
                item.get("image"),
                f"section:{item.get('origin', 'html')}",
                94.0,
                alt=item.get("image_alt") or title,
                width=item.get("image_width") or 0,
                height=item.get("image_height") or 0,
                page_url=link,
            )
            image_candidates = dedupe_image_candidates((candidate,))
            entries.append(
                StoryEntry(
                    title=compact_text(title, 220),
                    link=link,
                    source=publisher,
                    platform="news",
                    published_at=published_at,
                    keywords=keywords(title),
                    social_points=boost,
                    metrics={
                        "curated_editorial": True,
                        "editorial_section": section,
                        "editorial_feed": status_name,
                        "topic_tags": sorted(detected_tags),
                        "source_mode": "direct-section",
                    },
                    thumbnail=image_candidates[0].url if image_candidates else None,
                    image_candidates=image_candidates,
                    media_type="article",
                )
            )
            accepted += 1
            if accepted >= MAX_NEWS_ITEMS_PER_SOURCE:
                break

        mode = "directo"
        if accepted < 5:
            fallback = feed_fallback_for_section(
                status_name=status_name,
                fallback_url=fallback_url,
                editorial_boost=boost,
                editorial_section=section,
                configured_tags=tags,
                cutoff=cutoff,
                seen=seen,
                limit=MAX_NEWS_ITEMS_PER_SOURCE - accepted,
            )
            entries.extend(fallback)
            accepted += len(fallback)
            if fallback:
                mode = "directo + respaldo Google News" if direct_items else "respaldo Google News"

        if accepted == 0:
            note = "La portada no devolvió artículos y el respaldo tampoco"
            if direct_error:
                note = f"Portada inaccesible: {compact_text(str(direct_error), 120)}"
            warnings.append(f"{status_name}: {note}")
            statuses.append({"name": status_name, "ok": False, "items": 0, "note": note})
            print(f"[aviso] {status_name}: 0 elementos · {note}")
        else:
            statuses.append({"name": status_name, "ok": True, "items": accepted, "note": mode})
            print(f"[ok] {status_name}: {accepted} elementos · {mode}")
    return entries, warnings, statuses

def fetch_news_entries() -> tuple[list[StoryEntry], list[str], list[dict[str, Any]]]:
    entries: list[StoryEntry] = []
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=NEWS_MAX_AGE_HOURS)
    seen: set[tuple[str, str]] = set()

    direct_entries, direct_warnings, direct_statuses = fetch_direct_section_entries(cutoff, seen)
    entries.extend(direct_entries)
    warnings.extend(direct_warnings)
    statuses.extend(direct_statuses)

    for fallback_source, url, editorial_boost, editorial_section, configured_tags in NEWS_SOURCES:
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

            is_google_news_feed = url.startswith(GOOGLE_NEWS_BASE)
            source = extract_publisher(raw, fallback_source)
            if is_google_news_feed and source == fallback_source and " - " in raw_title:
                source = raw_title.rsplit(" - ", 1)[1].strip() or fallback_source
            title = clean_google_title(raw_title, source) if is_google_news_feed else raw_title
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

            image_candidates = extract_feed_image_candidates(raw)
            detected_tags = classify_topic_tags(title, configured_tags)
            entries.append(
                StoryEntry(
                    title=compact_text(title, 220),
                    link=link,
                    source=source,
                    platform="news",
                    published_at=published_at,
                    keywords=title_keywords,
                    social_points=editorial_boost,
                    metrics={
                        "curated_editorial": bool(editorial_section),
                        "editorial_section": editorial_section or "",
                        "editorial_feed": fallback_source,
                        "topic_tags": sorted(detected_tags),
                    },
                    thumbnail=image_candidates[0].url if image_candidates else None,
                    image_candidates=image_candidates,
                    media_type="article",
                )
            )
            accepted += 1
            if accepted >= MAX_NEWS_ITEMS_PER_SOURCE:
                break

        note = "Sin artículos recientes" if accepted == 0 else None
        statuses.append({"name": fallback_source, "ok": True, "items": accepted, "note": note})
        prefix = "[sin resultados]" if accepted == 0 else "[ok]"
        print(f"{prefix} {fallback_source}: {accepted} elementos")

    return entries, warnings, statuses


def xml_local_name(tag: Any) -> str:
    return str(tag or "").rsplit("}", 1)[-1].split(":")[-1]


def xml_child_text(node: ET.Element, local_name: str) -> str:
    for child in list(node):
        if xml_local_name(child.tag) == local_name:
            return html.unescape("".join(child.itertext()).strip())
    return ""


def parse_rss_datetime(value: str) -> dt.datetime | None:
    if not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def get_google_trends() -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Descarga Trends y conserva sus artículos relacionados.

    El RSS incluye volumen aproximado de búsquedas, una imagen representativa
    y hasta varios ``ht:news_item``. Se conserva su orden y se toma el primer
    artículo válido como noticia principal asociada por Google. El feed no
    proporciona visitas de cada artículo, por lo que no se inventa ese dato.
    """
    warnings: list[str] = []
    try:
        payload = fetch_bytes(GOOGLE_TRENDS_URL)
        feed = feedparser.parse(payload)
        root = ET.fromstring(payload)
    except (
        OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
        ET.ParseError,
    ) as exc:
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
    for item in root.iter():
        if xml_local_name(item.tag) != "item":
            continue
        title = xml_child_text(item, "title").strip()
        normalized = normalize(title)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        traffic_raw = xml_child_text(item, "approx_traffic")
        picture = valid_http_url(xml_child_text(item, "picture"))
        picture_source = xml_child_text(item, "picture_source") or None
        trend_url = valid_http_url(xml_child_text(item, "link"))
        published_at = parse_rss_datetime(xml_child_text(item, "pubDate"))
        now = dt.datetime.now(dt.timezone.utc)
        if not is_within_content_window(published_at, now):
            continue

        related_news: list[dict[str, Any]] = []
        for child in list(item):
            if xml_local_name(child.tag) != "news_item":
                continue
            article_url = valid_http_url(xml_child_text(child, "news_item_url"))
            article_title = compact_text(xml_child_text(child, "news_item_title"), 220)
            article_source = compact_text(xml_child_text(child, "news_item_source"), 90)
            article_snippet = compact_text(xml_child_text(child, "news_item_snippet"), 260)
            if not article_url or not article_title:
                continue
            related_news.append(
                {
                    "title": article_title,
                    "url": article_url,
                    "source": article_source or None,
                    "snippet": article_snippet or None,
                }
            )

        top_news = related_news[0] if related_news else None
        trends.append(
            {
                "name": title,
                "traffic": parse_human_count(traffic_raw),
                "traffic_label": traffic_raw.strip() or None,
                "trend_url": trend_url,
                "published_at": published_at.isoformat().replace("+00:00", "Z") if published_at else None,
                "picture": picture,
                "picture_source": picture_source,
                "news": related_news[:3],
                "top_news": top_news,
            }
        )

    trends = trends[:30]
    with_news = sum(1 for trend in trends if trend.get("top_news"))
    print(f"[ok] Google Trends: {len(trends)} tendencias · {with_news} con noticia asociada")
    return trends, warnings, {
        "name": "Google Trends España",
        "ok": True,
        "items": len(trends),
        "note": f"{with_news} con noticia asociada",
    }


def build_google_trend_entries(trends: list[dict[str, Any]]) -> list[StoryEntry]:
    """Convierte la noticia principal de cada tendencia en candidata al ranking."""
    entries: list[StoryEntry] = []
    for trend in trends:
        article = trend.get("top_news") or {}
        link = valid_http_url(article.get("url"))
        title = compact_text(str(article.get("title") or ""), 220)
        trend_name = compact_text(str(trend.get("name") or ""), 120)
        if not link or not title or not trend_name or is_blocked_content(title):
            continue

        picture = valid_http_url(trend.get("picture"))
        candidate = make_image_candidate(
            picture,
            "google-trends:picture",
            74.0,
            alt=title,
            page_url=link,
        ) if picture else None
        image_candidates = dedupe_image_candidates((candidate,))
        traffic = int(trend.get("traffic") or 0)
        social_points = min(25.0, 6.0 + math.log10(traffic + 1) * 3.1)
        entries.append(
            StoryEntry(
                title=title,
                link=link,
                source=str(article.get("source") or trend.get("picture_source") or "Google Trends"),
                platform="news",
                published_at=None,
                keywords=keywords(f"{trend_name} {title}"),
                social_points=social_points,
                metrics={
                    "google_trends_item": True,
                    "trend_name": trend_name,
                    "search_traffic": traffic,
                    "search_traffic_label": trend.get("traffic_label"),
                    "trend_published_at": trend.get("published_at"),
                    "topic_tags": ["google-trends"],
                },
                thumbnail=image_candidates[0].url if image_candidates else None,
                image_candidates=image_candidates,
                media_type="article",
                seed_trend=trend_name,
            )
        )
    return entries


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


def reddit_image_candidates(data: dict[str, Any]) -> tuple[ImageCandidate, ...]:
    candidates: list[ImageCandidate | None] = []
    title = str(data.get("title") or "")
    preview = data.get("preview")
    if isinstance(preview, dict):
        images = preview.get("images")
        if isinstance(images, list):
            for image in images:
                if not isinstance(image, dict):
                    continue
                source = image.get("source")
                if isinstance(source, dict):
                    candidates.append(
                        make_image_candidate(
                            source.get("url"),
                            "reddit:preview-source",
                            122.0,
                            alt=title,
                            width=source.get("width") or 0,
                            height=source.get("height") or 0,
                        )
                    )
                resolutions = image.get("resolutions")
                if isinstance(resolutions, list):
                    for resolution in reversed(resolutions):
                        if isinstance(resolution, dict):
                            candidates.append(
                                make_image_candidate(
                                    resolution.get("url"),
                                    "reddit:preview-resolution",
                                    118.0,
                                    alt=title,
                                    width=resolution.get("width") or 0,
                                    height=resolution.get("height") or 0,
                                )
                            )
    gallery = data.get("gallery_data")
    metadata = data.get("media_metadata")
    if isinstance(gallery, dict) and isinstance(metadata, dict):
        for item in gallery.get("items", []) if isinstance(gallery.get("items"), list) else []:
            media_id = str(item.get("media_id") or "") if isinstance(item, dict) else ""
            media = metadata.get(media_id)
            if not isinstance(media, dict):
                continue
            source = media.get("s")
            if isinstance(source, dict):
                candidates.append(
                    make_image_candidate(
                        source.get("u") or source.get("gif"),
                        "reddit:gallery-source",
                        123.0,
                        alt=title,
                        width=source.get("x") or 0,
                        height=source.get("y") or 0,
                    )
                )
    direct = data.get("url_overridden_by_dest") or data.get("url")
    if re.search(r"\.(?:jpe?g|png|gif|webp)(?:\?|$)", str(direct), re.I):
        candidates.append(make_image_candidate(direct, "reddit:direct-image", 121.0, alt=title))
    thumbnail = valid_http_url(data.get("thumbnail"))
    if thumbnail and not thumbnail.endswith(("default.png", "self.png", "nsfw.png", "spoiler.png")):
        candidates.append(make_image_candidate(thumbnail, "reddit:thumbnail", 88.0, alt=title))
    return dedupe_image_candidates(candidates)


def reddit_thumbnail(data: dict[str, Any]) -> str | None:
    candidates = reddit_image_candidates(data)
    return candidates[0].url if candidates else None


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
        image_candidates = reddit_image_candidates(data)
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
                thumbnail=image_candidates[0].url if image_candidates else None,
                image_candidates=image_candidates,
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


def bluesky_image_candidates(embed: Any, *, alt_context: str = "") -> tuple[tuple[ImageCandidate, ...], str]:
    if not isinstance(embed, dict):
        return (), "text"
    embed_type = str(embed.get("$type", ""))
    if "recordWithMedia" in embed_type:
        return bluesky_image_candidates(embed.get("media"), alt_context=alt_context)
    candidates: list[ImageCandidate | None] = []
    if "images" in embed_type:
        images = embed.get("images")
        if isinstance(images, list):
            for image in images:
                if not isinstance(image, dict):
                    continue
                alt = image.get("alt") or alt_context
                aspect = image.get("aspectRatio") if isinstance(image.get("aspectRatio"), dict) else {}
                candidates.append(
                    make_image_candidate(
                        image.get("fullsize"),
                        "bluesky:image-fullsize",
                        122.0,
                        alt=alt,
                        width=aspect.get("width") or 0,
                        height=aspect.get("height") or 0,
                    )
                )
                candidates.append(
                    make_image_candidate(
                        image.get("thumb"),
                        "bluesky:image-thumb",
                        120.0,
                        alt=alt,
                        width=aspect.get("width") or 0,
                        height=aspect.get("height") or 0,
                    )
                )
        return dedupe_image_candidates(candidates), "image"
    if "video" in embed_type:
        aspect = embed.get("aspectRatio") if isinstance(embed.get("aspectRatio"), dict) else {}
        candidates.append(
            make_image_candidate(
                embed.get("thumbnail"),
                "bluesky:video-thumbnail",
                121.0,
                alt=alt_context,
                width=aspect.get("width") or 0,
                height=aspect.get("height") or 0,
            )
        )
        return dedupe_image_candidates(candidates), "video"
    if "external" in embed_type:
        external = embed.get("external")
        if isinstance(external, dict):
            candidates.append(
                make_image_candidate(
                    external.get("thumb"),
                    "bluesky:external-card",
                    105.0,
                    alt=external.get("title") or external.get("description") or alt_context,
                    page_url=external.get("uri"),
                )
            )
        return dedupe_image_candidates(candidates), "link"
    return (), "text"


def bluesky_thumbnail(embed: Any) -> tuple[str | None, str]:
    candidates, media_type = bluesky_image_candidates(embed)
    return (candidates[0].url if candidates else None), media_type


def bluesky_post_url(uri: str, handle: str) -> str | None:
    parts = uri.split("/")
    if len(parts) < 5 or not handle:
        return None
    rkey = parts[-1]
    return valid_http_url(f"https://bsky.app/profile/{handle}/post/{rkey}")


def fetch_bluesky_search(params: str) -> tuple[Any | None, int | None, str | None]:
    """Prueba el AppView público con caché y el host directo con backoff."""
    last_code: int | None = None
    last_error: str | None = None
    for attempt, base in enumerate(BLUESKY_SEARCH_URLS):
        try:
            return fetch_json(
                f"{base}?{params}",
                headers={"Accept-Language": "es-ES,es;q=0.9"},
            ), None, None
        except urllib.error.HTTPError as exc:
            last_code = exc.code
            last_error = f"HTTP {exc.code}"
            if exc.code not in {403, 429, 500, 502, 503, 504}:
                break
            time.sleep(0.9 + attempt * 0.8)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = compact_text(str(exc) or exc.__class__.__name__, 120)
            time.sleep(0.5 + attempt * 0.5)
    return None, last_code, last_error


def fetch_bluesky_entries(
    seed_trends: list[str],
) -> tuple[list[StoryEntry], list[str], dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=SOCIAL_MAX_AGE_HOURS)).isoformat().replace("+00:00", "Z")
    seeds: list[str] = []
    normalized_seeds: set[str] = set()
    # Menos consultas y pausas cortas reducen los bloqueos 403 del AppView.
    for candidate in [*seed_trends[:6], "meme", "animales"]:
        candidate = candidate.strip().lstrip("#")
        normalized = normalize(candidate)
        if len(candidate) < 3 or normalized in normalized_seeds:
            continue
        normalized_seeds.add(normalized)
        seeds.append(candidate)
        if len(seeds) >= 8:
            break

    entries: list[StoryEntry] = []
    warnings: list[str] = []
    seen: set[str] = set()
    successful_queries = 0
    limited_seeds: list[str] = []
    other_failures: list[str] = []
    consecutive_access_failures = 0

    for seed in seeds:
        params = urllib.parse.urlencode(
            {
                "q": seed,
                "lang": "es",
                "sort": "top",
                "since": since,
                "limit": 20,
            }
        )
        payload, error_code, error_text = fetch_bluesky_search(params)
        if payload is None:
            if error_code in {403, 429}:
                limited_seeds.append(seed)
                consecutive_access_failures += 1
                if consecutive_access_failures >= 2:
                    break
            else:
                other_failures.append(f"{seed}: {error_text or 'sin respuesta'}")
                consecutive_access_failures = 0
            continue
        consecutive_access_failures = 0
        successful_queries += 1

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
            image_candidates, media_type = bluesky_image_candidates(post.get("embed"), alt_context=text)
            thumbnail = image_candidates[0].url if image_candidates else None
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
                    image_candidates=image_candidates,
                    media_type=media_type,
                    seed_trend=seed,
                )
            )
        time.sleep(0.35)

    if limited_seeds:
        warnings.append(
            "Bluesky limitó temporalmente algunas búsquedas (403/429): "
            + ", ".join(f"«{item}»" for item in limited_seeds)
            + ". Se conservaron los resultados obtenidos antes del límite."
        )
    if other_failures:
        warnings.append("Bluesky tuvo fallos parciales: " + "; ".join(other_failures[:3]))

    ok = successful_queries > 0
    note_parts = [f"{successful_queries}/{len(seeds)} búsquedas respondieron"]
    if limited_seeds:
        note_parts.append(f"{len(limited_seeds)} limitadas")
    print(f"[ok] Bluesky: {len(entries)} publicaciones · {'; '.join(note_parts)}")
    return entries, warnings, {
        "name": "Bluesky España",
        "ok": ok,
        "items": len(entries),
        "note": "; ".join(note_parts) if ok else "No respondió ninguna búsqueda",
    }


def looks_spanish(text: str) -> bool:
    tokens = normalize(text).split()
    if not tokens:
        return False
    common = {
        "que", "para", "como", "esto", "esta", "pero", "porque", "cuando",
        "tambien", "muy", "una", "uno", "unos", "unas", "los", "las", "el",
        "del", "por", "con", "sin", "sobre", "entre", "desde", "hasta", "es",
        "son", "fue", "han", "se", "su", "sus", "al", "y", "en",
    }
    return sum(token in common for token in tokens) >= 2


def likely_spanish_link(title: str, description: str, url: str) -> bool:
    if looks_spanish(f"{title} {description}"):
        return True
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host.endswith(".es") or any(
        domain in host
        for domain in (
            "elpais.com", "lavanguardia.com", "20minutos.es", "elespanol.com",
            "huffingtonpost.es", "publico.es", "antena3.com", "lasexta.com",
            "telecinco.es", "marca.com", "as.com", "infobae.com",
        )
    )


def mastodon_history_totals(history: Any) -> tuple[int, int]:
    uses = 0
    accounts = 0
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        uses += parse_human_count(item.get("uses"))
        accounts += parse_human_count(item.get("accounts"))
    return uses, accounts


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
        host = urllib.parse.urlparse(base).netloc
        name = f"Mastodon · {host}"
        try:
            payload = fetch_json(f"{base}/api/v1/trends/statuses?limit=40")
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            warnings.append(f"No se pudo consultar {name}: {exc}")
            statuses.append({"name": name, "ok": False, "items": 0})
            continue

        accepted_statuses = 0
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
            media_candidates: list[ImageCandidate | None] = []
            media_type = "text"
            if isinstance(media, list) and media:
                for attachment in media:
                    if not isinstance(attachment, dict):
                        continue
                    attachment_type = str(attachment.get("type", ""))
                    if attachment_type in {"video", "gifv"}:
                        media_type = "video"
                    elif media_type != "video":
                        media_type = "image"
                    meta = attachment.get("meta") if isinstance(attachment.get("meta"), dict) else {}
                    small = meta.get("small") if isinstance(meta.get("small"), dict) else {}
                    original = meta.get("original") if isinstance(meta.get("original"), dict) else {}
                    alt = attachment.get("description") or content
                    media_candidates.append(
                        make_image_candidate(
                            attachment.get("preview_url"),
                            "mastodon:preview",
                            121.0,
                            alt=alt,
                            width=small.get("width") or 0,
                            height=small.get("height") or 0,
                            page_url=link,
                        )
                    )
                    media_candidates.append(
                        make_image_candidate(
                            attachment.get("url") or attachment.get("remote_url"),
                            "mastodon:original",
                            118.0,
                            alt=alt,
                            width=original.get("width") or 0,
                            height=original.get("height") or 0,
                            page_url=link,
                        )
                    )
            image_candidates = dedupe_image_candidates(media_candidates)
            thumbnail = image_candidates[0].url if image_candidates else None
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
                    image_candidates=image_candidates,
                    media_type=media_type,
                )
            )
            accepted_statuses += 1

        # Cuando una instancia no tiene posts españoles en tendencias, se prueban
        # enlaces compartidos en tendencia. Este endpoint también es público.
        accepted_links = 0
        if accepted_statuses < 5:
            try:
                link_payload = fetch_json(f"{base}/api/v1/trends/links?limit=20")
            except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                warnings.append(f"No se pudieron consultar enlaces de {name}: {exc}")
                link_payload = []
            for card in link_payload if isinstance(link_payload, list) else []:
                if not isinstance(card, dict):
                    continue
                link = valid_http_url(card.get("url"))
                title = compact_text(str(card.get("title") or ""), 220)
                description = compact_text(str(card.get("description") or ""), 260)
                if not link or link in seen or len(title) < 20 or is_blocked_content(title):
                    continue
                if not likely_spanish_link(title, description, link):
                    continue
                uses, accounts = mastodon_history_totals(card.get("history"))
                if uses < 2 and accounts < 2:
                    continue
                provider = compact_text(str(card.get("provider_name") or card.get("author_name") or host), 80)
                image_candidate = make_image_candidate(
                    card.get("image"),
                    "mastodon:trending-link",
                    112.0,
                    alt=title,
                    width=card.get("width") or 0,
                    height=card.get("height") or 0,
                    page_url=link,
                )
                image_candidates = dedupe_image_candidates((image_candidate,))
                seen.add(link)
                social_points = min(18.0, 3.0 + math.log10(uses + 1) * 4.0 + math.log10(accounts + 1) * 2.0)
                entries.append(
                    StoryEntry(
                        title=title,
                        link=link,
                        source=f"Mastodon · {provider}",
                        platform="mastodon",
                        published_at=None,
                        keywords=keywords(f"{title} {description}"),
                        social_points=social_points,
                        metrics={
                            "favourites": 0,
                            "boosts": 0,
                            "replies": 0,
                            "link_uses": uses,
                            "link_accounts": accounts,
                            "mastodon_trending_link": True,
                        },
                        thumbnail=image_candidates[0].url if image_candidates else None,
                        image_candidates=image_candidates,
                        media_type="article",
                    )
                )
                accepted_links += 1

        accepted = accepted_statuses + accepted_links
        note = f"{accepted_statuses} publicaciones"
        if accepted_links:
            note += f" + {accepted_links} enlaces"
        elif accepted == 0:
            note = "Sin tendencias en español en esta actualización"
        statuses.append({"name": name, "ok": True, "items": accepted, "note": note})
        print(f"[ok] {name}: {accepted} elementos · {note}")

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
        youtube_candidates: list[ImageCandidate | None] = []
        score_by_size = {"maxres": 128.0, "standard": 126.0, "high": 124.0, "medium": 120.0, "default": 104.0}
        for key in ("maxres", "standard", "high", "medium", "default"):
            value = thumbnails.get(key)
            if isinstance(value, dict):
                youtube_candidates.append(
                    make_image_candidate(
                        value.get("url"),
                        f"youtube:{key}",
                        score_by_size[key],
                        alt=title,
                        width=value.get("width") or 0,
                        height=value.get("height") or 0,
                    )
                )
        image_candidates = dedupe_image_candidates(youtube_candidates)
        thumbnail = image_candidates[0].url if image_candidates else None
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
                image_candidates=image_candidates,
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
    tags = classify_topic_tags(entry.title, entry.metrics.get("topic_tags") or [])
    score = 0.0
    if entry.platform != "news":
        score += 5.0
    if entry.metrics.get("curated_editorial"):
        score += 5.0
    if entry.media_type in {"image", "video"}:
        score += 7.0

    specific = tags & CABRONAZI_CORE_TAGS
    score += min(22.0, len(specific) * 4.0)
    score += min(10.0, contains_phrase(entry.title, VIRAL_TERMS) * 2.5)
    if tags & {"humor", "memes", "animales", "insolito"}:
        score += 5.0
    if tags & {"famosos", "television", "reality", "redes"}:
        score += 3.0

    politics_hits = contains_phrase(entry.title, POLITICS_TERMS)
    hard_hits = contains_phrase(entry.title, HARD_NEWS_TERMS)
    institutional_hits = contains_phrase(entry.title, INSTITUTIONAL_TERMS)
    strong_angle = bool(tags & CABRONAZI_STRONG_TAGS) and (entry.media_type in {"image", "video"} or entry.platform != "news")
    if politics_hits:
        score -= 10.0 if strong_angle else 34.0
    if hard_hits:
        score -= 9.0 if strong_angle else 28.0
    score -= min(20.0, institutional_hits * 10.0)

    if entry.source.startswith("Reddit r/yo_elvr") or entry.source.startswith("Reddit r/MemesEnEspanol"):
        score += 5.0
    return max(-45.0, min(38.0, score))


def format_metric(value: int | float) -> str:
    numeric = float(value)
    if numeric >= 1_000_000:
        return f"{numeric / 1_000_000:.1f} M".replace(".0", "")
    if numeric >= 1_000:
        return f"{numeric / 1_000:.1f} k".replace(".0", "")
    return str(int(numeric))


def entry_signal(entry: StoryEntry) -> str | None:
    m = entry.metrics
    if entry.platform == "news" and m.get("google_trends_item"):
        label = f"Google Trends: {m.get('trend_name', entry.seed_trend or '')}"
        if m.get("search_traffic_label"):
            label += f" ({m['search_traffic_label']} búsquedas)"
        return label
    if entry.platform == "news" and m.get("curated_editorial"):
        return f"Selección editorial: {m.get('editorial_feed', entry.source)}"
    if entry.platform == "meneame":
        return (
            f"{format_metric(int(m.get('meneos', 0)))} meneos · "
            f"{format_metric(int(m.get('comments', 0)))} comentarios · "
            f"{format_metric(int(m.get('clicks', 0)))} clics en Menéame"
        )
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
        editorial_feeds = sorted(
            {
                str(item.metrics.get("editorial_feed", "")).strip()
                for item in items
                if item.metrics.get("curated_editorial")
                and str(item.metrics.get("editorial_feed", "")).strip()
            },
            key=str.casefold,
        )
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
        profile = cluster_editorial_profile(items)
        # La actualidad institucional solo entra cuando existe un ángulo viral
        # inequívoco. Así se evita que el feed general se convierta en portada política.
        if profile["politics_hits"] and not profile["strong_viral"]:
            continue
        if profile["hard_news_hits"] and not profile["strong_viral"]:
            continue
        if profile["institutional_hits"] and not profile["specific_tags"]:
            continue

        fit_values = [editorial_fit(item) for item in items]
        fit_score = max(fit_values) + max(0.0, sum(max(0.0, value) for value in fit_values) / max(1, len(fit_values)) * 0.25)
        # Una noticia genérica sin señales sociales ni una categoría compartible
        # no merece ocupar espacio aunque sea muy reciente.
        if not profile["specific_tags"] and not profile["trusted_viral_feed"] and social_score < 10 and len(sources) < 2:
            continue
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
        image_contexts = []
        for item in sorted(
            items,
            key=lambda candidate: (
                candidate is main,
                bool(candidate.image_candidates or candidate.thumbnail),
                candidate.social_points,
            ),
            reverse=True,
        ):
            image_contexts.append(
                {
                    "title": item.title,
                    "link": item.link,
                    "source": item.source,
                    "platform": item.platform,
                    "media_type": item.media_type,
                    "thumbnail": item.thumbnail,
                    "candidates": [serialize_candidate(candidate) for candidate in item.image_candidates],
                    "is_main": item is main,
                    "force_destination_image": item.platform == "meneame",
                }
            )
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

        topic_tag_set = set(profile["tags"])
        if google_match or x_match or len(platforms) >= 2 or social_score >= 24:
            topic_tag_set.add("trending")
        if profile["specific_tags"] or editorial_feeds:
            topic_tag_set.add("viral")
        if profile["politics_hits"]:
            topic_tag_set.add("politica")
        if profile["hard_news_hits"]:
            topic_tag_set.add("sucesos")
        topic_tags = sorted(
            topic_tag_set,
            key=lambda tag: (CABRONAZI_TAG_ORDER.index(tag) if tag in CABRONAZI_TAG_ORDER else 999, tag),
        )

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
                "curated_editorial": bool(editorial_feeds),
                "editorial_feeds": editorial_feeds,
                "topic_tags": topic_tags,
                "primary_tag": next((tag for tag in CABRONAZI_TAG_ORDER if tag in topic_tag_set and tag not in {"trending", "viral"}), "viral"),
                "cabronazi_fit": round(fit_score, 1),
                "politics_related": bool(profile["politics_hits"]),
                "hard_news_related": bool(profile["hard_news_hits"]),
                "num_mentions": len(items),
                "matched_trend": google_match.get("name") if google_match else None,
                "matched_google_trend": google_match.get("name") if google_match else None,
                "matched_x_trend": x_match.get("name") if x_match else None,
                "published_at": main.published_at.isoformat().replace("+00:00", "Z") if main.published_at else None,
                "thumbnail": thumbnail,
                "_image_contexts": image_contexts,
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
    return diversify_ranked(ranked, MAX_STORIES)


def diversify_ranked(stories: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Evita que política, sucesos o una sola cabecera monopolicen el radar."""
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    politics_count = 0
    hard_news_count = 0

    for story in stories:
        tags = set(story.get("topic_tags") or [])
        primary = str(story.get("primary_tag") or "viral")
        sources = story.get("sources") or []
        primary_source = str(sources[0] if sources else "Fuente original")
        if "politica" in tags and politics_count >= 3:
            continue
        if "sucesos" in tags and hard_news_count >= 5:
            continue
        if category_counts.get(primary, 0) >= 24 or source_counts.get(primary_source, 0) >= 10:
            deferred.append(story)
            continue
        selected.append(story)
        category_counts[primary] = category_counts.get(primary, 0) + 1
        source_counts[primary_source] = source_counts.get(primary_source, 0) + 1
        politics_count += int("politica" in tags)
        hard_news_count += int("sucesos" in tags)
        if len(selected) >= limit:
            return selected

    for story in deferred:
        if len(selected) >= limit:
            break
        tags = set(story.get("topic_tags") or [])
        if "politica" in tags and politics_count >= 3:
            continue
        if "sucesos" in tags and hard_news_count >= 5:
            continue
        selected.append(story)
        politics_count += int("politica" in tags)
        hard_news_count += int("sucesos" in tags)
    return selected

def build_google_trend_news(
    trends: list[dict[str, Any]], stories: list[dict[str, Any]], limit: int = 12
) -> list[dict[str, Any]]:
    """Une cada término con la mejor noticia disponible en el radar.

    Se prioriza la historia ya verificada y mejor puntuada del ranking. Si no
    hay una pieza con fecha comprobada dentro de las últimas 24 horas, el
    término se muestra sin noticia asociada.
    """
    cards: list[dict[str, Any]] = []
    for trend in trends[:limit]:
        trend_name = str(trend.get("name") or "").strip()
        normalized = normalize(trend_name)
        matches = [
            story for story in stories
            if normalize(str(story.get("matched_google_trend") or "")) == normalized
        ]
        article: dict[str, Any] | None = None
        if matches:
            best = max(
                matches,
                key=lambda story: (
                    int(story.get("viral_score") or story.get("score") or 0),
                    story.get("published_at") or "",
                ),
            )
            sources = best.get("sources") or []
            article = {
                "title": best.get("title"),
                "url": best.get("link"),
                "source": sources[0] if sources else "Fuente original",
                "viral_score": int(best.get("viral_score") or best.get("score") or 0),
                "thumbnail": best.get("thumbnail"),
                "verified_image": bool(best.get("image_verified")),
                "selection": "radar",
            }

        cards.append(
            {
                "name": trend_name,
                "traffic": int(trend.get("traffic") or 0),
                "traffic_label": trend.get("traffic_label"),
                "trend_url": trend.get("trend_url"),
                "article": article,
            }
        )
    return cards


def build() -> dict[str, Any]:
    warnings: list[str] = []
    source_status: list[dict[str, Any]] = []

    news_entries, news_warnings, news_status = fetch_news_entries()
    warnings.extend(news_warnings)
    source_status.extend(news_status)

    meneame_entries, meneame_warnings, meneame_status = fetch_meneame_entries()
    warnings.extend(meneame_warnings)
    source_status.extend(meneame_status)

    google_trends, trend_warnings, google_status = get_google_trends()
    warnings.extend(trend_warnings)
    source_status.append(google_status)
    google_trend_entries = build_google_trend_entries(google_trends)

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
        *google_trend_entries,
        *news_entries,
        *meneame_entries,
        *reddit_entries,
        *bluesky_entries,
        *mastodon_entries,
        *youtube_entries,
    ]
    raw_entries_count = len(entries)
    entries, publication_date_summary = enrich_missing_publication_dates(entries)
    now = dt.datetime.now(dt.timezone.utc)
    entries, temporal_summary = filter_recent_entries(entries, now)
    if not entries:
        raise RuntimeError(
            "No se obtuvo ningún contenido verificable de las últimas 24 horas. "
            "Se conserva el data.json anterior para no vaciar el panel."
        )

    ranked = build_ranked(entries, google_trends, x_trends)
    ranked, image_summary = enrich_ranked_images(ranked)
    tag_distribution: dict[str, int] = {}
    for story in ranked:
        for tag in story.get("topic_tags") or []:
            tag_distribution[str(tag)] = tag_distribution.get(str(tag), 0) + 1
    editorial_summary = {
        "politics": sum(1 for story in ranked if story.get("politics_related")),
        "hard_news": sum(1 for story in ranked if story.get("hard_news_related")),
        "trending": tag_distribution.get("trending", 0),
        "top_tags": sorted(
            ((tag, count) for tag, count in tag_distribution.items() if tag not in {"viral", "trending", "politica", "sucesos"}),
            key=lambda item: (-item[1], item[0]),
        )[:8],
    }
    print(
        "[ok] Enfoque editorial: "
        f"{editorial_summary['trending']} trending · "
        f"{editorial_summary['politics']} política · "
        f"{editorial_summary['hard_news']} sucesos · "
        + ", ".join(f"#{tag} {count}" for tag, count in editorial_summary["top_tags"][:5])
    )
    google_trend_news = build_google_trend_news(google_trends, ranked)
    active_sources = sum(1 for status in source_status if status.get("ok") is True)
    configured_sources = sum(1 for status in source_status if status.get("ok") is not None)

    return {
        "updated_at": now.isoformat().replace("+00:00", "Z"),
        "trends_google": [item["name"] for item in google_trends[:20]],
        "trends_x": [item["name"] for item in x_trends[:20]],
        "trend_details": {"google": google_trends[:20], "x": x_trends[:20]},
        "google_trend_news": google_trend_news,
        "stories": ranked,
        "warnings": warnings,
        "source_status": source_status,
        "source_summary": {
            "active": active_sources,
            "configured": configured_sources,
            "total": len(source_status),
            "entries_collected": len(entries),
            "entries_before_24h_filter": raw_entries_count,
        },
        "image_summary": image_summary,
        "content_window_hours": CONTENT_MAX_AGE_HOURS,
        "temporal_summary": temporal_summary,
        "publication_date_summary": publication_date_summary,
        "editorial_summary": editorial_summary,
        "tag_distribution": tag_distribution,
        "methodology": (
            "Potencial viral heurístico basado en interacción observable, velocidad, recencia, "
            "presencia en varias plataformas, Google/X Trends y afinidad con humor, memes, animales, famosos, televisión, contenido insólito, redes, tecnología y lifestyle. La actualidad política o de sucesos solo entra cuando tiene un ángulo viral inequívoco y está limitada por cupos de diversidad. Solo se publican contenidos cuya fecha se ha podido verificar dentro de las últimas 24 horas. Las noticias relacionadas de Google Trends se incorporan como candidatas al ranking. "
            "Las previsualizaciones se verifican, se asocian al artículo o publicación y se guardan "
            "localmente; se descartan logos, imágenes pequeñas y candidatos genéricos. "
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
