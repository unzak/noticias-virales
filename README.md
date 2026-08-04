# Pulso Viral v3.0.1 — enfoque entretenimiento y contenido compartible

Panel estático para detectar contenidos con potencial editorial viral en España.
Publica hasta 150 resultados y exige que la fecha de publicación pueda
verificarse dentro de las **últimas 24 horas**.

Las búsquedas temáticas de Google News se limitan a medios con edición española.
El ranking refuerza además las piezas vinculadas a España y descarta actualidad
local extranjera sin un ángulo español, aunque el titular esté escrito en español.
La interfaz clara en rosa permite ordenar por prioridad, tiempo ascendente o
tiempo descendente sin perder los filtros de periodo y categoría. Google
Trends sigue aportando señales internas al ranking, pero ya no ocupa un panel
propio en la interfaz.

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
- Cada noticia admite un voto positivo o negativo. El navegador aprende pesos
  por categoría, fuente y etiquetas internas y reordena el panel sin alterar
  el score editorial original.
- El ranking compara cada titular con un perfil agregado de 834 publicaciones
  reales de Cabronazi y muestra la `Afinidad Cabronazi` de cada coincidencia.

## Fuentes sin claves

- Secciones virales y de entretenimiento de EL PAÍS, MARCA Tiramillas,
  20minutos, HuffPost, Cribeo, AS Tikitakas, Antena 3, laSexta, Telecinco,
  EL ESPAÑOL, Público, Infobae y LOS40, entre otras.
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
ni versionar archivos de terceros. Si no se encuentra ninguna URL de imagen
utilizable o no puede resolverse el enlace original fuera de Google News, la
noticia no se publica.

## Fuentes opcionales

- Reddit: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` y, opcionalmente,
  `REDDIT_USER_AGENT`.
- YouTube España: `YOUTUBE_API_KEY`.
- Tendencias de X: `X_BEARER_TOKEN`.

El panel sigue funcionando sin estas claves.

## Aprendizaje editorial

Los botones `Positivo` y `Negativo` alimentan un modelo ligero que suma o resta
preferencia a las características de cada pieza: categoría general, cabecera y
etiquetas editoriales detalladas. La prioridad aprendida se calcula sobre el
score viral base y se utiliza para reordenar los resultados visibles.

La respuesta visual se guarda primero en `localStorage`, por lo que el panel
sigue reaccionando aunque la red falle. Cuando Supabase está configurado, cada
cambio de voto se registra también como evento compartido. En la siguiente
actualización, `fetch_news.py` resume los votos más recientes, reduce
progresivamente el peso de los antiguos y limita a 200 piezas la influencia de
un mismo navegador. El resultado ajusta moderadamente el ranking y añade hasta
tres búsquedas temáticas basadas en las etiquetas con mejor respuesta.

La beta es abierta y no exige contraseña. La tabla solo concede al navegador
permiso de inserción: la lectura completa queda reservada al workflow mediante
la clave de servicio. Los límites editoriales, la ventana estricta de 24 horas,
la diversidad y las reglas contra política y sucesos se aplican después del
aprendizaje y no pueden ser anulados por los votos.

Para activarlo:

1. Ejecuta `supabase/schema.sql` en el editor SQL de un proyecto Supabase.
2. Añade `SUPABASE_URL` y `SUPABASE_ANON_KEY` como variables del repositorio.
3. Añade `SUPABASE_SERVICE_ROLE_KEY` como secreto de GitHub Actions.

Sin esas variables se conserva automáticamente el aprendizaje local anterior.

## Rendimiento histórico de Cabronazi

`cabronazi_performance_profile.json` resume el informe de Meta del 1 de julio al
3 de agosto de 2026 sin incluir el CSV original, identificadores ni métricas por
publicación. El perfil se construye con 834 posts —560 con texto analizable— y
usa este score: 40% compartidos sobre alcance, 25% interacción sobre alcance,
15% alcance, 10% clics sobre alcance y 10% comentarios sobre alcance. El
feedback negativo aplica una penalización adicional.

El generador compara los titulares nuevos con categorías, patrones narrativos y
expresiones del histórico. Para evitar falsos positivos, un nombre propio o un
lugar aislado no eleva el ranking: la coincidencia debe estar respaldada por una
categoría editorial y otro patrón, o por dos expresiones históricas. La afinidad
modifica el ranking un máximo de siete puntos y no aporta puntos positivos a
política o sucesos. Por tanto, nunca puede saltarse los filtros editoriales,
temporales o de diversidad.

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

1. Recupera las fechas ausentes desde el artículo destino.
2. Descarta contenidos anteriores a 24 horas.
3. Descarta contenidos sin fecha verificable.
4. Descarta fechas futuras con más de 20 minutos de desviación.
5. Conserva el despliegue anterior si ninguna fuente produce resultados válidos.

## Previsualizaciones

Para Menéame se abre siempre el artículo original y se enlaza la imagen del
destino, evitando la miniatura de Menéame. Los tags `img` de `article` y `main`
se comparan por relevancia con la imagen declarada en los metadatos; banners,
logos, píxeles y placeholders quedan excluidos. Las imágenes no se descargan
en `docs/media/`.

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
- `docs/index.html`: interfaz del panel.
- `docs/data.json`: datos generados.
- `docs/media/`: recursos locales heredados; las noticias nuevas enlazan la imagen remota.
- `.github/workflows/update.yml`: actualización y despliegue cada ~45 minutos.


## Corrección 3.0.1

Corrige una colisión entre dos definiciones de `best_srcset_url` que podía detener el workflow al resolver imágenes o enlaces de Menéame. La resolución de un destino individual de Menéame ahora también queda aislada para que una página inesperada no cancele toda la actualización.
