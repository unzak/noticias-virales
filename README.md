# Pulso Viral v3.0.1 — enfoque entretenimiento y contenido compartible

Panel estático para detectar contenidos con potencial editorial viral en España.
La vista sin filtro y la selección editorial se construyen sobre un historial
móvil con todas las piezas cuya fecha pueda verificarse dentro de las **últimas
72 horas**, sin imponer un límite global de resultados.
Una tercera vista, `Trending ForoCoches`, muestra por separado todos los hilos del
ranking público actual, en su orden original y sin comprobar su fecha.

Las búsquedas temáticas de Google News se limitan a medios con edición española.
El ranking refuerza además las piezas vinculadas a España y descarta actualidad
local extranjera sin un ángulo español, aunque el titular esté escrito en español.
El filtro también excluye medios y ediciones de Latinoamérica identificados por
dominio territorial, URL o cabecera antes de construir ambas vistas. `Infobae`
solo se conserva para su edición España bajo `/espana/`.
También se reconocen explícitamente `lasestrellas.tv` y los dominios de
República Dominicana (`.do`).
La interfaz clara en rosa permite ordenar por prioridad, tiempo ascendente o
tiempo descendente sin perder los filtros de periodo y categoría. Ambas vistas
se abren por defecto con las noticias más recientes primero. Google
Trends sigue aportando señales internas al ranking, pero ya no ocupa un panel
propio en la interfaz.

El menú superior abre por defecto `Sin filtro`, limitado visualmente a las piezas
de las últimas 24 horas, y deja `Selección Cabronazi`, con ranking
editorial y diversidad, como segunda opción. La ausencia de imagen ya no elimina una noticia: el panel
abre el artículo, enlaza la URL de su imagen editorial y usa un placeholder rosa
solo cuando el medio no expone ninguna imagen fiable. Nunca descarga la imagen.

> El score es una heurística editorial. No predice ni garantiza likes, alcance o ingresos.

## Cambios de esta versión

- Se elimina el feed general de Google News España, que introducía demasiada
  política y actualidad institucional.
- Se añaden búsquedas específicas para humor, memes, animales, famosos,
  televisión, realities, contenido insólito, redes, tecnología e IA,
  videojuegos, deporte viral, comida, historias positivas y nostalgia.
- Se añaden LOS40 y cabeceras españolas de prensa del corazón como fuentes
  especializadas de entretenimiento.
- HuffPost se consulta desde su RSS de portada y Antena 3 desde los RSS oficiales
  de Noticias y Sociedad. Lecturas y Semana prueban primero sus RSS; si el medio
  bloquea la petición, se conserva Google News como respaldo.
- El RSS de portada de HuffPost se incorpora completo dentro de cada ventana de
  actualización, sin prefiltrado editorial; el ranking decide después qué piezas
  entran en la selección, pero todas permanecen disponibles en `Sin filtro`.
- Las fichas de HuffPost que no obtienen imagen durante la fase concurrente se
  reintentan secuencialmente para recuperar su `og:image` editorial, sin recurrir
  a miniaturas de noticias relacionadas de la propia página.
- Los `og:image` de HuffPost ya guardados se reutilizan en updates posteriores;
  así se evitan peticiones repetidas al medio y se reserva la extracción para
  noticias nuevas o fichas que todavía carecen de imagen.
- 20minutos, Público Tremending y LOS40 se consultan desde sus secciones
  directas, con Google News como respaldo.
- Las consultas de Google News incluyen exclusiones de política, instituciones,
  guerra, tribunales y economía, además del filtro temporal de un día.
- El clasificador asigna etiquetas editoriales automáticamente a partir del
  titular y de la sección de origen.
- Los titulares total o parcialmente en inglés se descartan antes del ranking.
- Los artículos de viajes, turismo, hoteles, aeropuertos y vuelos se descartan
  antes de construir tanto la selección como la vista completa.
- La interfaz permite limitar el panel a la última hora, las últimas 4, 24, 48
  o 72 horas. Se abre por defecto en 24 horas.
- Cada update consulta una ventana solapada de 3 horas, la fusiona con
  `docs/history.json`, elimina duplicados y poda automáticamente lo anterior a
  72 horas.
- Cuando una URL reaparece, prevalece la copia nueva o la que conserve más
  metadatos editoriales, evitando que una entrada histórica pierda etiquetas,
  afinidad o prioridad en la selección.
- En GitHub Actions se fusionan el historial publicado y el historial versionado:
  el primero aporta las novedades de cada cron y el segundo puede restaurar
  correcciones o metadatos editoriales que una copia desplegada antigua no tenga.
- Las noticias meteorológicas se descartan en toda la ingesta, incluidas las
  previsiones, alertas y piezas sobre AEMET, temperaturas, lluvias o borrascas.
- Los sucesos españoles disponen de una consulta y un impulso editorial propios,
  con hasta 24 piezas separadas en el filtro `Sucesos`; la política continúa residual.
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
- Prensa del corazón: Lecturas y Semana mediante RSS con respaldo restringido a
  su dominio; HOLA, Diez Minutos y Vanitatis mediante búsquedas restringidas.
- Búsquedas temáticas restringidas a medios españoles mediante Google News RSS.
- Menéame: Populares y Más visitadas.
- Google Trends España y sus noticias relacionadas.
- La Razón Sociedad mediante su RSS público, sometido a los mismos filtros.
- ForoCoches Trending como vista independiente: no mezcla sus hilos con `Sin
  filtro` ni con `Selección Cabronazi`; publica el ranking actual completo con
  sus títulos, enlaces y la imagen local FOROCOCHES, sin verificar fechas. Los
  temas también actúan como señal para noticias coincidentes.
- Bluesky y Mastodon están desactivados por configuración editorial y no
  realizan peticiones.

Los enlaces de Google News se resuelven al artículo original antes de localizar
la imagen. El panel enlaza directamente la mejor URL editorial del artículo,
comparando sus tags `img` con `og:image`, Twitter Card y JSON-LD, sin descargar
ni versionar archivos de terceros. Si no se encuentra una URL utilizable, se
muestra un placeholder ligero. En ambas vistas se descartan los envoltorios de
Google News cuyo destino original no puede resolverse.

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

El clima se excluye de todas las vistas. Los sucesos en España cuentan con un
impulso específico y un cupo ampliado, manteniendo el bloqueo de contenido
gráfico y los límites por fuente para evitar que una cabecera monopolice el panel.

## Ventana temporal

Antes de agrupar y puntuar, el generador:

1. Recupera las fechas ausentes desde el `datePublished` del artículo destino,
   priorizando el bloque cuyo URL coincide y contrastando la fecha codificada
   en la propia URL para no usar fechas de noticias relacionadas. Una fecha
   antigua explícita en la URL invalida también una fecha reciente del RSS.
2. En cada update admite novedades de las últimas 3 horas y las fusiona con el
   historial previamente publicado.
3. Deduplica por destino canónico y por equivalencia de titulares.
4. Descarta del historial contenidos anteriores a 72 horas.
5. Descarta contenidos sin fecha verificable.
6. Descarta fechas futuras con más de 20 minutos de desviación.
7. Conserva el despliegue anterior si ninguna fuente produce resultados válidos.

La ingesta también excluye recetas, festivales, sorteos y loterías, viajes y turismo,
contenidos centrados en precios, y programaciones, fiestas o agendas locales de
escaso interés viral.

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
- `tools/fetch_forocoches_trending.py`: obtiene los hilos públicos del ranking,
  abre cada hilo para verificar la fecha del primer mensaje y puede ejecutarse
  de forma independiente con `--limit`.
- `cabronazi_performance_profile.json`: pesos históricos sin datos por post.
- `editorial_selection_profile.json`: recuentos agregados de fuentes y secciones seleccionadas.
- `docs/index.html`: interfaz del panel.
- `docs/data.json`: datos generados.
- `docs/history.json`: historial móvil generado de las últimas 72 horas.
- `docs/media/`: recursos locales heredados; las noticias nuevas enlazan la imagen remota.
- `.github/workflows/update.yml`: generación principal a las `:07` de cada hora
  y definición reutilizable del proceso completo.
- `.github/workflows/update-half-hour.yml`: segundo turno a las `:37`, separado
  para que GitHub no agrupe varios cron del mismo workflow. Juntos solicitan una
  actualización cada 30 minutos, durante las 24 horas y en horario de Madrid.
  La generación y el despliegue se serializan con el grupo `pages` para que cada
  ejecución fusione el historial publicado por la anterior sin perder noticias.


## Corrección 3.0.1

Corrige una colisión entre dos definiciones de `best_srcset_url` que podía detener el workflow al resolver imágenes o enlaces de Menéame. La resolución de un destino individual de Menéame ahora también queda aislada para que una página inesperada no cancele toda la actualización.
