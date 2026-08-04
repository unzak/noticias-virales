# Pulso Viral v3.0.1 — enfoque entretenimiento y contenido compartible

Panel estático para detectar contenidos con potencial editorial viral en España.
Publica hasta 100 resultados y exige que la fecha de publicación pueda
verificarse dentro de las **últimas 24 horas**.

> El score es una heurística editorial. No predice ni garantiza likes, alcance o ingresos.

## Cambios de esta versión

- Se elimina el feed general de Google News España, que introducía demasiada
  política y actualidad institucional.
- Se añaden búsquedas específicas para humor, memes, animales, famosos,
  televisión, realities, contenido insólito, redes, tecnología e IA,
  videojuegos, deporte viral, comida, viajes, historias positivas y nostalgia.
- Se añade LOS40 como fuente especializada de entretenimiento y virales.
- Las consultas de Google News incluyen exclusiones de política, instituciones,
  guerra, tribunales y economía, además del filtro temporal de un día.
- El clasificador asigna etiquetas editoriales automáticamente a partir del
  titular y de la sección de origen.
- Las piezas políticas o de sucesos se descartan salvo que tengan un ángulo
  viral inequívoco. Incluso entonces quedan limitadas a un máximo de 3 piezas
  políticas y 5 de sucesos dentro del ranking.
- Se aplican límites de diversidad para impedir que una sola categoría o un
  único medio monopolicen la lista.
- La interfaz incorpora filtros y etiquetas `#Trending`, `#Humor`, `#Memes`,
  `#Animales`, `#Famosos`, `#TV`, `#Reality`, `#Insólito`, `#Redes`,
  `#Tecnología`, `#Gaming`, `#Deportes`, `#Comida`, `#Viajes`, `#Historias`,
  `#Nostalgia` y `#Lifestyle`.

## Fuentes sin claves

- Secciones virales y de entretenimiento de EL PAÍS, MARCA Tiramillas,
  20minutos, HuffPost, Cribeo, AS Tikitakas, Antena 3, laSexta, Telecinco,
  EL ESPAÑOL, Público, Infobae y LOS40, entre otras.
- Búsquedas temáticas restringidas a medios españoles mediante Google News RSS.
- Menéame: Populares y Más visitadas.
- Google Trends España y sus noticias relacionadas.
- Bluesky y tendencias públicas de Mastodon.

## Fuentes opcionales

- Reddit: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` y, opcionalmente,
  `REDDIT_USER_AGENT`.
- YouTube España: `YOUTUBE_API_KEY`.
- Tendencias de X: `X_BEARER_TOKEN`.

El panel sigue funcionando sin estas claves.

## Selección editorial

El ranking favorece contenido que pueda convertirse en una publicación visual y
compartible: humor, memes, animales, situaciones insólitas, famosos, televisión,
realities, creadores, redes sociales, tecnología curiosa, deporte viral,
nostalgia e historias humanas.

La actualidad institucional solo entra cuando concurren señales adicionales,
como una imagen o vídeo, interacción social, presencia en varias plataformas o
una categoría viral clara. Los artículos genéricos sin categoría ni señales
sociales se descartan.

## Ventana temporal

Antes de agrupar y puntuar, el generador:

1. Recupera las fechas ausentes desde el artículo destino.
2. Descarta contenidos anteriores a 24 horas.
3. Descarta contenidos sin fecha verificable.
4. Descarta fechas futuras con más de 20 minutos de desviación.
5. Conserva el despliegue anterior si ninguna fuente produce resultados válidos.

## Previsualizaciones

Las imágenes se verifican y almacenan en `docs/media/`. Para Menéame se abre
siempre el artículo original y se extrae la imagen del destino, evitando la
miniatura de Menéame. Se descartan logos, avatares, placeholders, imágenes
pequeñas y candidatos genéricos.

## Instalar esta versión

Copia el contenido de esta carpeta en la raíz del repositorio y ejecuta:

```bash
git add -A
git commit -m "Priorizar contenido viral y reducir política"
git push origin main
```

El `push` inicia el workflow. También puede ejecutarse manualmente desde:

`Actions → Actualizar y publicar radar viral → Run workflow`

En `Settings → Pages`, la fuente debe ser **GitHub Actions**.

## Probar localmente

```bash
python -m venv .venv
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
python -m pip install -r requirements.txt
python fetch_news.py
python -m http.server 8000 --directory docs
```

Abre `http://localhost:8000`.

## Archivos

- `fetch_news.py`: consulta, verifica fechas, clasifica, filtra, agrupa y puntúa.
- `docs/index.html`: interfaz del panel.
- `docs/data.json`: datos generados.
- `docs/media/`: imágenes verificadas.
- `.github/workflows/update.yml`: actualización y despliegue cada ~45 minutos.


## Corrección 3.0.1

Corrige una colisión entre dos definiciones de `best_srcset_url` que podía detener el workflow al resolver imágenes o enlaces de Menéame. La resolución de un destino individual de Menéame ahora también queda aislada para que una página inesperada no cancele toda la actualización.
