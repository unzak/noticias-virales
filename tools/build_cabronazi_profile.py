"""Construye un perfil editorial agregado desde una exportación de Meta.

Uso: python tools/build_cabronazi_profile.py ruta/al/informe.csv
El CSV original no se copia al repositorio; solo se guarda el perfil agregado.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "cabronazi_performance_profile.json"

KPI_WEIGHTS = {
    "share_rate": 0.40,
    "engagement_rate": 0.25,
    "reach": 0.15,
    "click_rate": 0.10,
    "comment_rate": 0.10,
}

STOPWORDS = {
    "para", "como", "pero", "porque", "desde", "hasta", "sobre", "entre", "cuando",
    "donde", "esta", "este", "estos", "estas", "segun", "tras", "ante", "durante",
    "tambien", "solo", "cada", "todo", "todos", "toda", "todas", "unas", "unos",
    "del", "las", "los", "una", "uno", "que", "con", "por", "sus", "han", "hay",
    "fue", "son", "sin", "más", "mas", "muy", "ese", "esa", "eso", "habria",
    "habría", "sera", "será", "años", "despues", "después", "nuevo", "nueva",
}

CATEGORY_TERMS = {
    "humor-curiosidades": ("humor", "meme", "broma", "viral", "surreal", "insolito", "curioso", "risa", "divertid"),
    "famosos-corazon": ("famos", "actor", "actriz", "cantant", "pareja", "boda", "ruptura", "television", "reality", "influencer"),
    "redes-tecnologia": ("tiktok", "instagram", "redes", "streamer", "tecnolog", "inteligencia artificial", "videojuego", "gaming"),
    "animales": ("animal", "perro", "gato", "mascota", "caballo", "ave", "tiburon"),
    "deportes": ("futbol", "barcelona", "madrid", "deport", "jugador", "fichaje", "partido", "velada"),
    "vida-bienestar": ("comida", "receta", "viaje", "turismo", "historia", "salud", "trabajo", "empresa", "nostalgia", "bienestar"),
}

PATTERN_TERMS = {
    "sorpresa": ("sorprende", "nadie esperaba", "increible", "insolito", "descubre", "revela"),
    "emocion": ("emotivo", "lagrimas", "familia", "homenaje", "reencuentro", "gesto"),
    "indignacion": ("indignacion", "polemica", "denuncia", "criticas", "maltrato", "injusticia"),
    "identificacion": ("todos", "alguna vez", "quien no", "cuando eres", "nos pasa", "tipico"),
    "nostalgia": ("recuerda", "nostalgia", "decadas", "infancia", "vuelve", "años despues"),
    "ternura": ("tierno", "cachorro", "bebe", "mascota", "adopta", "rescata"),
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.sub(r"[^a-z0-9ñ]+", " ", "".join(ch for ch in value if not unicodedata.combining(ch))).split())


def number(value: object) -> float:
    try:
        return float(str(value or "0").replace(",", "."))
    except ValueError:
        return 0.0


def percentile_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    if len(values) <= 1:
        return ranks
    for rank, index in enumerate(order):
        ranks[index] = rank / (len(values) - 1)
    return ranks


def features(text: str) -> set[str]:
    tokens = [token for token in normalize(text).split() if len(token) >= 4 and token not in STOPWORDS and not token.isdigit()]
    result = set(tokens)
    result.update(f"{left} {right}" for left, right in zip(tokens, tokens[1:]) if left not in STOPWORDS and right not in STOPWORDS)
    return result


def classify(text: str) -> str:
    normalized = normalize(text)
    return next((category for category, terms in CATEGORY_TERMS.items() if any(term in normalized for term in terms)), "otros")


def main(csv_path: Path) -> None:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("Fecha") == "Total"]
    if not rows:
        raise SystemExit("El CSV no contiene filas agregadas con Fecha=Total")

    metrics: dict[str, list[float]] = defaultdict(list)
    negative_rates: list[float] = []
    for row in rows:
        reach = max(1.0, number(row.get("Alcance")))
        interactions = number(row.get("Reacciones, comentarios y veces que se compartió"))
        metrics["share_rate"].append(number(row.get("Veces que se compartió")) / reach)
        metrics["engagement_rate"].append(interactions / reach)
        metrics["reach"].append(reach)
        metrics["click_rate"].append(number(row.get("Total de clics")) / reach)
        metrics["comment_rate"].append(number(row.get("Comentarios")) / reach)
        negatives = number(row.get("Comentarios negativos de los usuarios: Ocultar todo")) + number(row.get("Comentarios negativos de los usuarios: Ocultar"))
        negative_rates.append(negatives / reach)

    ranks = {name: percentile_ranks(values) for name, values in metrics.items()}
    negative_ranks = percentile_ranks(negative_rates)
    scores = [
        max(0.0, min(1.0, sum(KPI_WEIGHTS[name] * ranks[name][index] for name in KPI_WEIGHTS) - 0.10 * negative_ranks[index]))
        for index in range(len(rows))
    ]

    titled = [(row, scores[index]) for index, row in enumerate(rows) if str(row.get("Título") or "").strip()]
    baseline = sum(score for _, score in titled) / max(1, len(titled))
    feature_scores: dict[str, list[float]] = defaultdict(list)
    category_scores: dict[str, list[float]] = defaultdict(list)
    pattern_scores: dict[str, list[float]] = defaultdict(list)
    for row, score in titled:
        title = str(row.get("Título") or "")
        normalized = normalize(title)
        for feature in features(title):
            feature_scores[feature].append(score)
        category_scores[classify(title)].append(score)
        for pattern, terms in PATTERN_TERMS.items():
            if any(term in normalized for term in terms):
                pattern_scores[pattern].append(score)

    def learned_weights(
        groups: dict[str, list[float]],
        minimum: int,
        positive_limit: int | None = None,
        negative_limit: int | None = None,
    ) -> dict[str, float]:
        weighted: list[tuple[str, float]] = []
        for name, values in groups.items():
            if len(values) < minimum:
                continue
            shrinkage = len(values) / (len(values) + 8)
            lift_points = ((sum(values) / len(values)) - baseline) * 100 * shrinkage
            weighted.append((name, round(max(-12.0, min(12.0, lift_points)), 2)))
        if positive_limit is not None and negative_limit is not None:
            positives = sorted((item for item in weighted if item[1] > 0), key=lambda item: item[1], reverse=True)[:positive_limit]
            negatives = sorted((item for item in weighted if item[1] < 0), key=lambda item: item[1])[:negative_limit]
            weighted = sorted((*positives, *negatives), key=lambda item: abs(item[1]), reverse=True)
        else:
            weighted.sort(key=lambda item: abs(item[1]), reverse=True)
        return dict(weighted)

    profile = {
        "version": 1,
        "source": csv_path.name,
        "period": "2026-07-01/2026-08-03",
        "posts": len(rows),
        "posts_with_text": len(titled),
        "posts_without_text": len(rows) - len(titled),
        "post_format": "Fotos",
        "kpi_weights": KPI_WEIGHTS,
        "negative_feedback_penalty": 0.10,
        "baseline_score": round(baseline * 100, 2),
        "feature_weights": learned_weights(feature_scores, 3, 250, 100),
        "category_weights": learned_weights(category_scores, 5),
        "pattern_weights": learned_weights(pattern_scores, 3),
        "pattern_terms": {name: list(terms) for name, terms in PATTERN_TERMS.items()},
        "visual_prior": round(sum(scores[index] for index, row in enumerate(rows) if not str(row.get("Título") or "").strip()) / max(1, len(rows) - len(titled)) * 100, 2),
    }
    OUTPUT.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Perfil escrito en {OUTPUT}: {len(titled)}/{len(rows)} posts con texto · {len(profile['feature_weights'])} rasgos")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/build_cabronazi_profile.py ruta/al/informe.csv")
    main(Path(sys.argv[1]).resolve())
