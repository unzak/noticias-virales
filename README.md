# Pulso Viral v3.0.1 — enfoque entretenimiento y contenido compartible

Panel estático para detectar contenidos con potencial editorial viral en España.
La selección Cabronazi publica hasta 150 resultados; la vista sin filtro muestra
todas las piezas cuya fecha pueda verificarse dentro de las **últimas 24 horas**.

Las búsquedas temáticas de Google News se limitan a medios con edición española.
El ranking refuerza además las piezas vinculadas a España y descarta actualidad
local extranjera sin un ángulo español, aunque el titular esté escrito en español.
El filtro también excluye ediciones regionales mexicanas identificadas en las
URL (por ejemplo, rutas `/mx/`, `/mexico/` y dominios `.mx`) antes de construir
ambas vistas.
La interfaz clara en rosa permite ordenar por prioridad, tiempo ascendente o
tiempo descendente sin perder los filtros de periodo y categoría. Ambas vistas
se abren por defecto con las noticias más recientes primero. Google
Trends sigue aportando señales internas al ranking, pero ya no ocupa un panel
propio en la interfaz.

El menú superior abre por defecto `Sin filtro`, que muestra todas las piezas con
fecha válida de las últimas 24 horas, y deja `Selección Cabronazi`, con ranking
editorial y diversidad, como segunda opción. La ausencia de imagen ya no elimina una noticia: el panel
abre el artículo, enlaza la URL de su imagen editorial y usa un placeholder rosa
solo cuando el medio no expone ninguna imagen fiable. Nunca descarga la imagen.

> El score es una heurística editorial. No predice ni garantiza likes, alcance o ingresos.

## Cambios de esta versión

- Se elimina el feed general de Google News España, que introducía demasiada
  política y actualidad institucional.
- Se añaden búsquedas específicas para humor, memes, animales, famosos,
  televisión, realities, contenido insólito, redes, tecnología e IA,
  videojuegos, deporte viral, comida, viajes, historias positivas y nostalgia.
- Se añaden LOS40 y cabeceras españolas de prensa del corazón como fuentes
  especializadas de entretenimiento.
- 20minutos, HuffPost, Telecinco, Público Tremending y LOS40 se consultan
  desde sus secciones directas, con Google News como respaldo.
- Las consultas de Google News incluyen exclusiones de política, instituciones,
  guerra, tribunales y economía, además del filtro temporal de un día.
- El clasificador asigna etiquetas editoriales automáticamente a partir del
  titular y de la sección de origen.
- Los titulares total o parcialmente en inglés se descartan antes del ranking.
- La interfaz permite limitar el panel a la última hora, las últimas 4 horas
  o las últimas 24 horas, sin relajar la ventana máxima de verificación.
- Las piezas políticas o de sucesos se descartan salvo que tengan un ángulo
  viral inequívoco. La nueva consulta de sucesos en España permite hasta 12
  piezas, siempre separadas en el filtro `Sucesos`; la política continúa residual.
- Se aplican límites de diversidad para impedir que una sola categoría o un
  único medio monopolicen la lista.
- La interfaz engloba las etiquetas detalladas en seis categorías: `Humor y
  curiosidades`, `Famosos y corazón`, `Redes y tecnología`, `Animales`,
  `Deportes` y `Vida y bienestar`.
- El ranking compara cada titular con un perfil agregado de 834 publicaciones
  reales de Cabronazi y muestra la `Afinidad Cabronazi` de cada coincidencia.

## Fuentes sin claves

- Secciones virales y de entretenimiento de EL PAÍS, MARCA Tiramillas,
  20minutos, HuffPost, AS Tikitakas, Antena 3, laSexta, Público y LOS40, entre
  otras. La sección global de Infobae queda excluida para evitar
  actualidad local latinoamericana.
- RSS oficiales de Mundo Deportivo `El Otro Mundo`, Infobae España, Telecinco,
  EL ESPAÑOL y La Vanguardia. Las dos portadas generalistas parten sin impulso
  ni etiquetas preasignadas; solo después de superar el prefiltrado estricto
  reciben el bonus de fuente editorial filtrada. Si una noticia coincide con
  Google News, el grupo conserva como principal el enlace original del medio.
  El feed de Infobae utiliza su endpoint oficial de Arc porque la URL corta
  `/espana/rss` redirige actualmente a 404. Cribeo y EL ESPAÑOL `Offbeat` se
  excluyen porque han dejado de publicar.
- Prensa del corazón: HOLA, Lecturas, Semana, Diez Minutos y Vanitatis mediante
  búsquedas restringidas a sus dominios.
- Búsquedas temáticas restringidas a medios españoles mediante Google News RSS.
- Menéame: Populares y Más visitadas.
- Google Trends España y sus noticias relacionadas.
- Bluesky y Mastodon están desactivados por configuración editorial y no
  realizan peticiones.

Los enlaces de Google News se resuelven al artículo original antes de localizar
la imagen. El panel enlaza directamente la mejor URL editorial del artículo,
comparando sus tags `img` con `og:image`, Twitter Card y JSON-LD, sin descargar
ni versionar archivos de terceros. Si no se encuentra una URL utilizable, se
muestra un placeholder ligero. En la selección editorial solo se descartan los
envoltorios de Google News cuyo destino original no puede resolverse.

## Fuentes opcionales

- Reddit: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` y, opcionalmente,
  `REDDIT_USER_AGENT`.
- YouTube España: `YOUTUBE_API_KEY`.
- Tendencias de X: `X_BEARER_TOKEN`.

El panel sigue funcionando sin estas claves.

## Rendimiento histórico de Cabronazi

`cabronazi_performance_profile.json` resume el informe de Meta del 1 de julio al
3 de agosto de 2026 sin incluir el CSV original, identificadores ni métricas por
publicación. El perfil se construye con 834 posts —560 con texto analizable— y
usa este score: 40% compartidos sobre alcance, 25% interacción sobre alcance,
15% alcance, 10% clics sobre alcance y 10% comentarios sobre alcance. Las
señales negativas incluidas en la exportación de Meta aplican una penalización.

El generador compara los titulares nuevos con categorías, patrones narrativos y
expresiones del histórico. Para evitar falsos positivos, un nombre propio o un
lugar aislado no eleva el ranking: la coincidencia debe estar respaldada por una
categoría editorial y otro patrón, o por dos expresiones históricas. La afinidad
modifica el ranking un máximo de siete puntos y no aporta puntos positivos a
política o sucesos. Por tanto, nunca puede saltarse los filtros editoriales,
temporales o de diversidad.

Los formatos narrativos claramente cómicos —expectativa contra realidad,
errores, confusiones o situaciones absurdas que terminan mal— reciben una señal
editorial propia cuando el histórico no contiene las mismas palabras exactas.

`editorial_selection_profile.json` agrega 158 enlaces seleccionados manualmente
en recuentos por dominio y sección, sin guardar las URLs originales. El ranking
aplica un bonus máximo de ocho puntos: prioriza especialmente `El Otro Mundo` de
Mundo Deportivo y `Tiramillas` de MARCA, pero no puede saltarse los filtros de
España, idioma, fecha, diversidad o calidad editorial.

Para actualizar el perfil con una exportación posterior:

```bash
python tools/build_cabronazi_profile.py ruta/al/informe.csv
```

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

1. Recupera las fechas ausentes desde el `datePublished` del artículo destino,
   priorizando el bloque cuyo URL coincide y contrastando la fecha codificada
   en la propia URL para no usar fechas de noticias relacionadas.
2. Descarta contenidos anteriores a 24 horas.
3. Descarta contenidos sin fecha verificable.
4. Descarta fechas futuras con más de 20 minutos de desviación.
5. Conserva el despliegue anterior si ninguna fuente produce resultados válidos.

La ingesta también excluye recetas, sorteos y loterías, contenidos centrados
en precios, y programaciones, fiestas o agendas locales de escaso interés viral.

## Previsualizaciones

Para Menéame se abre siempre el artículo original y se enlaza la imagen del
destino, evitando la miniatura de Menéame. Los tags `img` de `article` y `main`
se comparan por relevancia con la imagen declarada en los metadatos; banners,
logos, píxeles y placeholders quedan excluidos. Las imágenes no se descargan
en `docs/media/`. Este proceso también se aplica en paralelo a la vista sin
filtro; cuando el artículo no proporciona una imagen fiable, la tarjeta indica
`Sin imagen` y permanece en el listado.

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
- `tools/build_cabronazi_profile.py`: genera el perfil agregado desde Meta.
- `cabronazi_performance_profile.json`: pesos históricos sin datos por post.
- `editorial_selection_profile.json`: recuentos agregados de fuentes y secciones seleccionadas.
- `docs/index.html`: interfaz del panel.
- `docs/data.json`: datos generados.
- `docs/media/`: recursos locales heredados; las noticias nuevas enlazan la imagen remota.
- `.github/workflows/update.yml`: actualización y despliegue cada 10 minutos en
  horario de Madrid, con pausa entre las 02:00 y las 05:59 y reanudación a las
  06:00.


## Corrección 3.0.1

Corrige una colisión entre dos definiciones de `best_srcset_url` que podía detener el workflow al resolver imágenes o enlaces de Menéame. La resolución de un destino individual de Menéame ahora también queda aislada para que una página inesperada no cancele toda la actualización.
