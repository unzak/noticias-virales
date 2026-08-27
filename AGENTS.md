# AGENTS.md — Pulso Viral / noticias-virales

## Objetivo del proyecto

Mantener un panel editorial estático para detectar contenidos con potencial viral en España, orientado a un estilo de entretenimiento compartible similar a Cabronazi. No es un agregador generalista de actualidad.

## Regla crítica: las imágenes NUNCA se descargan

El panel **enlaza siempre la URL editorial remota** de cada imagen. No se descarga, no se cachea y no se versiona ningún archivo de imagen de terceros.

Las peticiones a una imagen sirven **solo para verificarla** (tipo, dimensiones, proporción); sus bytes nunca se guardan en disco.

Esto no es una preferencia de estilo:

- `.github/workflows/update.yml` comprueba que todo `thumbnail` empiece por `http://` o `https://`, con `media/forocoches.svg` como única excepción. **Cualquier imagen descargada rompe el CI y bloquea el despliegue.**
- Versionar imágenes hincha el historial de git de forma irreversible.

Única imagen local permitida: `docs/media/forocoches.svg`, asset propio del repositorio.

## Estado funcional que debe conservarse

- El repositorio se publica mediante GitHub Pages y GitHub Actions.
- La web está en `docs/index.html`, sin framework y con CSS y JavaScript en línea.
- Los datos publicados están en `docs/data.json` y el historial móvil en `docs/history.json`.
- Ambos JSON están versionados **a propósito**: en Actions, `load_history_entries()` fusiona el historial publicado en Pages con el versionado en el repositorio. El primero aporta las novedades de los cron anteriores; el segundo puede restaurar correcciones o metadatos que una copia desplegada antigua no tenga. No añadirlos a `.gitignore`.
- El generador principal es `fetch_news.py`. Dependencia única: `feedparser==6.0.11`.
- Los workflows son `.github/workflows/update.yml` (minutos `:11` y `:41`) y `.github/workflows/update-half-hour.yml` (minutos `:26` y `:56`, mediante `workflow_call`). Se declaran cuatro disparos por hora para obtener dos o tres: GitHub retrasa o descarta los eventos `schedule` cuando hay carga. El cron corre siempre en UTC; la clave `timezone` no existe en Actions.
- **No hay límite global de resultados.** La vista `Sin filtro` debe contener todas las piezas válidas del historial. La `Selección Cabronazi` sí aplica ranking y límites de diversidad.
- Ventanas temporales vigentes (`fetch_news.py`): consulta incremental de **3 h** (`FETCH_MAX_AGE_HOURS`), historial móvil de **72 h** (`CONTENT_MAX_AGE_HOURS`), panel abierto por defecto en **24 h** (`DEFAULT_PANEL_AGE_HOURS`). Se rechazan fechas ausentes, antiguas o futuras que no puedan verificarse.
- Máximo de `MAX_NEWS_ITEMS_PER_SOURCE = 35` piezas por fuente.
- La interfaz muestra una noticia por fila y usa numeración `#01`, `#02`, etc.
- Tres vistas independientes: `Sin filtro` (por defecto, más recientes primero), `Selección Cabronazi` y `Trending ForoCoches`.
- Google Trends aporta señales internas al ranking, pero **ya no ocupa un panel propio** en la interfaz.
- Menéame debe consultar `Populares` y `Más visitadas`; la imagen debe extraerse del artículo destino, nunca de una miniatura genérica de Menéame.
- Bluesky y Mastodon están desactivados por configuración editorial y no realizan ninguna petición.
- TikTokApi está eliminado. Se permiten noticias de medios sobre TikTok, pero no scraping directo del feed de TikTok.
- Las fuentes opcionales que requieren secretos son Reddit, YouTube y X. El panel debe seguir funcionando cuando esos secretos no existan.

## Enfoque editorial

Priorizar:

- humor y memes;
- animales y mascotas;
- famosos, televisión y realities;
- vídeos, reacciones y situaciones insólitas;
- redes sociales, influencers y streamers;
- tecnología curiosa, inteligencia artificial y videojuegos;
- deporte viral;
- comida, trucos, nostalgia e historias humanas o positivas.

Reducir fuertemente:

- política institucional;
- economía generalista;
- tribunales, guerra y sucesos sin ángulo claramente viral;
- viajes y turismo, meteorología, recetas, festivales, sorteos y loterías;
- programaciones y agendas locales;
- titulares total o parcialmente en inglés;
- actualidad local de Latinoamérica sin ángulo español;
- noticias duplicadas o titulares equivalentes.

Las piezas políticas solo deben entrar en la selección cuando tengan un ángulo viral inequívoco. `Sin filtro` puede conservar contenidos generalistas procedentes de fuentes sin prefiltrado, como HuffPost. Mantener los límites de diversidad por medio y categoría para evitar que una fuente monopolice el ranking.

## Fuentes principales

Conservar y revisar periódicamente:

- secciones virales y de entretenimiento de medios españoles;
- búsquedas temáticas mediante Google News RSS, restringidas a medios con edición española;
- RSS oficiales de Antena 3 (Noticias y Sociedad) y HuffPost (Portada);
- Lecturas y Semana mediante RSS con Google News como respaldo;
- Menéame `Populares` y `Más visitadas`;
- Google Trends España como señal de ranking;
- ForoCoches Trending como vista independiente;
- integraciones opcionales de Reddit, YouTube y X.

No asumir que una fuente funciona porque devuelve HTTP 200. Registrar por fuente: elementos brutos, elementos válidos dentro de la ventana, fallos y fallback usado.

## Imágenes

Releer antes la regla crítica del principio de este documento: **no se descargan**.

Orden de preferencia de la URL remota:

1. `og:image`
2. `twitter:image`
3. JSON-LD
4. Imagen del RSS
5. Imagen relevante del cuerpo del artículo

Rechazar logos, avatares, banners, placeholders, píxeles, imágenes pequeñas o genéricas y fotos de noticias relacionadas. Umbrales vigentes: mínimo 300x150 px, área mínima 90.000 px², proporción entre 0,28 y 4,0, archivo máximo 2,5 MB (constantes `IMAGE_*` en `fetch_news.py`). Se enriquecen como máximo `IMAGE_ENRICH_LIMIT = 150` fichas por ejecución.

Para Menéame, resolver siempre el artículo destino. Los envoltorios de Google News se resuelven al artículo original antes de buscar la imagen.

Si no existe una URL fiable, usar el placeholder del panel antes que una imagen incorrecta.

### Excepción de HuffPost

`DEFER_UNTIL_IMAGE_FEEDS` contiene `El HuffPost · Portada RSS`. HuffPost publica antes de exponer su imagen definitiva, así que:

- se ingiere sin prefiltrado editorial: todas las piezas válidas de su RSS;
- se revisan sus artículos durante una ventana de 24 h;
- el `og:image` prevalece sobre JSON-LD, imágenes del cuerpo y noticias relacionadas;
- un `og:image` ya guardado se reutiliza en actualizaciones posteriores, sin repetir la petición;
- si todavía no hay imagen editorial, la pieza **queda pendiente y se reintenta**; nunca se publica como ficha "Sin imagen".

## Historial y deduplicación

Se deduplica por URL canónica y equivalencia de titulares. Cuando una URL reaparece, prevalece la entrada con, por este orden:

1. fecha verificable más reciente;
2. metadatos editoriales;
3. feed y sección editorial;
4. mayor número de etiquetas temáticas;
5. imagen válida;
6. más candidatos visuales.

Esto evita que una copia antigua elimine etiquetas, afinidad, feed o prioridad de una noticia corregida. Si ninguna fuente produce resultados válidos, se conserva el despliegue anterior.

## Ranking

Combina señales editoriales, etiquetas temáticas, presencia en varias fuentes o plataformas, tendencias, afinidad con `cabronazi_performance_profile.json` y bonus de `editorial_selection_profile.json`, con límites de diversidad por fuente y categoría. El perfil se regenera con `tools/build_cabronazi_profile.py`.

La puntuación es una heurística editorial: no predice ni garantiza alcance, interacciones ni ingresos.

## Reglas de implementación

- Antes de editar, leer `README.md`, `fetch_news.py`, `docs/index.html` y `.github/workflows/update.yml`, y revisar `git status`.
- Buscar helpers existentes antes de añadir funciones nuevas.
- Hacer cambios pequeños y localizados; evitar reescrituras masivas de `fetch_news.py`.
- No introducir secretos, tokens, cookies ni credenciales en archivos versionados.
- No añadir scraping que incumpla las condiciones de una plataforma.
- Mantener compatibilidad con Python 3.11.
- No editar manualmente `docs/data.json` ni `docs/history.json` como solución permanente; deben regenerarse ejecutando `fetch_news.py`.
- Mantener la web sin framework y compatible con GitHub Pages, salvo petición expresa.
- Cuando cambie el comportamiento visible, actualizar `README.md`.
- No hacer `git commit`, `git push`, crear PR ni desplegar sin autorización explícita del usuario.

## Workflow y despliegue

- El workflow compila `fetch_news.py`, genera los datos, valida los JSON, comprueba las previsualizaciones enlazadas y despliega Pages.
- Los dos turnos existen por separado porque GitHub agrupa u omite varios `cron` declarados en un mismo workflow.
- Mantener siempre:

```yaml
concurrency:
  group: pages
  cancel-in-progress: false
```

Serializa generación y despliegue para que cada ejecución pueda fusionar el `history.json` publicado por la anterior sin perder noticias.

## Comprobaciones obligatorias

Antes de dar una tarea por terminada:

```bash
python -m py_compile fetch_news.py tools/build_cabronazi_profile.py tools/fetch_forocoches_trending.py
python fetch_news.py
python -m json.tool docs/data.json > /dev/null
python -m json.tool docs/history.json > /dev/null
git diff --check
```

Cuando se modifique la interfaz:

- revisar que `docs/index.html` cargue `data.json`;
- comprobar que no haya errores de JavaScript;
- probar la vista de escritorio y una anchura móvil;
- confirmar una noticia por fila y el funcionamiento de filtros, ordenación y las tres vistas.

Si las consultas de red impiden una prueba local completa, ejecutar pruebas sobre las funciones modificadas y declarar con precisión qué queda pendiente de verificar en GitHub Actions.

## Fuente de verdad

Ante cualquier contradicción entre este documento y el comportamiento observado, **manda el código**: `fetch_news.py`, los workflows, `README.md` y los JSON generados, por ese orden. No dar por vigente una regla histórica solo porque aparezca en documentación antigua. Si detectas que este archivo se ha quedado atrás, corrígelo en el mismo cambio.

## Forma de trabajar en cada tarea

1. Inspeccionar el estado real del repositorio y `git status`.
2. Explicar brevemente el diagnóstico y el plan.
3. Implementar el cambio.
4. Ejecutar las comprobaciones pertinentes.
5. Revisar el diff buscando regresiones, funciones duplicadas y cambios accidentales.
6. Entregar un resumen con archivos modificados, pruebas realizadas y riesgos pendientes.
7. Esperar autorización antes de commit, push o despliegue.
