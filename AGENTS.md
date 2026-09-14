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
- **Ninguno de los dos JSON se versiona.** Están en `.gitignore` desde que se comprobó que la copia del repositorio nunca llegaba a usarse: el workflow los genera en el runner y los despliega a Pages sin hacer commit de vuelta, así que solo se actualizaban cuando alguien ejecutaba el generador en local. La que había versionada era del 20 de agosto, con 1.079 entradas y **cero dentro de la ventana de 72 h**; `filter_recent_entries()` las descartaba todas al cargarlas. Costaba 1,74 MB por commit y no aportaba nada.
- En Actions, `load_history_entries()` carga el historial publicado en Pages, que sí está al día. Si no existiera, el panel reconstruye su ventana de 72 h solo, en 72 horas.
- Consecuencia para quien trabaje en local: hay que ejecutar `python fetch_news.py` antes de abrir `docs/index.html`, o el panel mostrará el mensaje de error por falta de `data.json`.
- El generador principal es `fetch_news.py`. Dependencia única: `feedparser==6.0.11`.
- El único workflow es `.github/workflows/update.yml`, que se dispara por `workflow_dispatch` y por push. **No declara `schedule`**: la actualización periódica la lanza un cronjob externo en cron-job.org que llama cada quince minutos a la API de Actions. El scheduler de GitHub se retiró porque entregaba 31-45 ejecuciones de las 48 pedidas y llegó a estar trece horas sin disparar ninguna. No añadir un `schedule` de vuelta sin comprobar antes que el problema se ha corregido.
- **No hay límite global de resultados.** La vista `Cabronazi` debe contener todas las piezas válidas del historial: es la antigua `Sin filtro`, sin ranking ni cupos.
- Ventanas temporales vigentes (`fetch_news.py`): consulta incremental de **3 h** (`FETCH_MAX_AGE_HOURS`), historial móvil de **72 h** (`CONTENT_MAX_AGE_HOURS`), panel abierto por defecto en **24 h** (`DEFAULT_PANEL_AGE_HOURS`). Se rechazan fechas ausentes, antiguas o futuras que no puedan verificarse.
- Máximo de `MAX_NEWS_ITEMS_PER_SOURCE = 35` piezas por fuente. En cada vertical, `VERTICAL_SOURCE_LIMIT = 14` piezas por medio y `VERTICAL_STORY_LIMIT = 300` en total.
- La interfaz muestra una noticia por fila y usa numeración `#01`, `#02`, etc.
- Cinco categorías en el panel: `Cabronazi` (por defecto, historial completo, más recientes primero), las tres verticales `Cabropeludos`, `Cabromotor` y `Cabrogamer`, y `TT ForoCoches`.
- `build_ranked()` se sigue ejecutando y `stories` se sigue publicando en `data.json` porque alimentan `build_google_trend_news()`, `editorial_summary` y `tag_distribution`, pero **ninguna vista del panel los muestra**. No borrar esa maquinaria sin comprobar antes esos tres consumidores.
- Las verticales se construyen sobre `unfiltered_stories`, nunca sobre `build_ranked`: ese filtro está afinado para una portada de virales generalista y descarta actualidad de motor o de videojuegos que en su vertical es justamente el material bueno.
- En `data.json`, `vertical_stories` contiene **listas de enlaces**, no fichas. Duplicar las fichas engordaba el archivo en ~1,7 MB. El panel las resuelve contra `unfiltered_stories`.
- La descarga de RSS va en paralelo (`NEWS_FEED_WORKERS`) pero el procesado sigue siendo secuencial y en el orden de `NEWS_SOURCES`: la deduplicación depende de ese orden.
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
- motor, cuando el ángulo es compartible (las verticales sí admiten actualidad sectorial);
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

## Verticales temáticas

`CABROPELUDOS`, `CABROMOTOR` y `CABROGAMER` se alimentan del mismo historial que el resto del panel. Una pieza entra en una vertical si:

1. viene de un feed declarado en `CABROPELUDOS_SOURCES`, `CABROMOTOR_SOURCES` o `CABROGAMER_SOURCES`, **o**
2. su titular contiene alguna de las palabras de `VERTICAL_KEYWORD_RULES`, venga del medio que venga.

Excepción importante: las fuentes cuyo feed es una búsqueda de Google News (`VERTICAL_KEYWORD_REQUIRED`) **exigen además la coincidencia en el titular**. Google busca en el texto completo del artículo y el operador `site:` con ruta se le escapa, así que sin esa condición se colaban programaciones de televisión y sucesos sin relación.

`story_vertical()` recalcula la vertical en cada ejecución en lugar de confiar en lo que guardó el historial: al cambiar una regla, las piezas de las 72 h anteriores se reclasifican solas en la siguiente pasada. Es el único sitio donde vive esa decisión.

Al elegir palabras clave, comprobar que no sean también otra cosa en español. Ya se descartaron por falsos positivos: `leon` (ciudad), `mono` (prenda), `mario` y `paloma` (nombres de pila), `fifa` (fútbol), `panda` (coche), `granja` (de criptomonedas), `especie` («una especie de…») y `trafico` (de drogas).

La prensa española de mascotas casi no tiene RSS vivo: al montar la vertical, Notas de Mascotas llevaba 40 días sin publicar, Bekia Mascotas 58, Etología Veterinaria 86, Curiosfera y PetDarling más de dos años. `CABROPELUDOS` se apoya por eso en la cobertura animal de la prensa generalista y será siempre la vertical con menos volumen. Antes de añadir un feed de animales, comprobar cuándo publicó por última vez.

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

- El workflow compila `fetch_news.py`, genera los datos, valida los JSON, comprueba las previsualizaciones enlazadas, comprueba que cada enlace de `vertical_stories` exista en el historial y despliega Pages.
- No hay turnos ni `schedule`: la actualización periódica la lanza el cronjob externo descrito más arriba.
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
