"""
fetch_news.py

Busca noticias recientes en fuentes españolas, agrupa titulares que hablan
del mismo tema, les da una puntuación de "viralidad" combinando:
  - en cuántos medios/fuentes distintas aparece
  - cuántas veces aparece en total
  - si coincide con los términos en tendencia de Google Trends España

y escribe el resultado ordenado en docs/data.json, que luego lee el
dashboard (docs/index.html).

Pensado para ejecutarse periódicamente vía GitHub Actions.
"""

import datetime
import json
import re

import feedparser

# --- Fuentes -----------------------------------------------------------

SOURCES = {
    "Google News España": "https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es",
    "Meneame": "https://www.meneame.net/rss2",
}

STOPWORDS = set(
    """de la el en y a los que del las un por con no una su para es al lo
    como más pero sus le ya o este si porque esta entre cuando muy sin
    sobre también me hasta hay donde quien desde todo nos durante todos
    uno les ni contra otros ese eso ante ellos e esto mi antes algunos
    que unos yo otro otras otra el tanto esa estos mucho quienes nada
    muchos cual poco ella estar estas algunas algo nosotros mi mis tu
    tus ellas nosotras vosotros vosotras os mio mia mios mias tuyo tuya
    tuyos tuyas suyo suya suyos suyas nuestro nuestra nuestros nuestras
    vuestro vuestra vuestros vuestras esos esas para tras dice dijo
    segun""".split()
)


def fetch_entries():
    entries = []
    for source, url in SOURCES.items():
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = e.get("title", "").strip()
            if not title:
                continue
            entries.append(
                {
                    "title": title,
                    "link": e.get("link"),
                    "source": source,
                    "published": e.get("published", ""),
                }
            )
    return entries


def get_trends():
    """Términos en tendencia en Google Trends España. Si falla (la API
    de Google Trends cambia a menudo y pytrends se rompe con frecuencia),
    devuelve una lista vacía y el resto del script sigue funcionando."""
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="es-ES", tz=60)
        df = pytrends.trending_searches(pn="spain")
        return [str(t).lower() for t in df[0].tolist()]
    except Exception as exc:  # noqa: BLE001
        print(f"[aviso] no se pudieron obtener Google Trends: {exc}")
        return []


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-záéíóúñü0-9\s]", " ", text)
    return text


def keywords(title):
    words = normalize(title).split()
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def similarity(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / min(len(a), len(b))


def cluster_entries(entries):
    clusters = []
    for entry in entries:
        kw = keywords(entry["title"])
        if not kw:
            continue
        placed = False
        for c in clusters:
            if similarity(kw, c["keywords"]) > 0.5:
                c["items"].append(entry)
                c["sources"].add(entry["source"])
                c["keywords"] |= kw
                placed = True
                break
        if not placed:
            clusters.append(
                {"items": [entry], "sources": {entry["source"]}, "keywords": kw}
            )
    return clusters


def score_cluster(cluster, trends):
    s = len(cluster["sources"]) * 10 + len(cluster["items"]) * 2
    matched_trend = None
    for t in trends:
        if keywords(t) & cluster["keywords"]:
            s += 25
            matched_trend = t
            break
    return s, matched_trend


def build():
    entries = fetch_entries()
    trends = get_trends()
    clusters = cluster_entries(entries)

    ranked = []
    for c in clusters:
        sc, matched_trend = score_cluster(c, trends)
        main = max(c["items"], key=lambda e: len(e["title"]))
        ranked.append(
            {
                "title": main["title"],
                "link": main["link"],
                "score": sc,
                "sources": sorted(c["sources"]),
                "num_mentions": len(c["items"]),
                "matched_trend": matched_trend,
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)

    return {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "trends_google": trends[:20],
        "stories": ranked[:40],
    }


if __name__ == "__main__":
    data = build()
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Escritas {len(data['stories'])} noticias en docs/data.json")
