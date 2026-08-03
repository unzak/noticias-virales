# Pulso Viral v2.4 — radar social para España

Dashboard estático para detectar contenidos con **potencial editorial viral**:
humor, curiosidades, animales, entretenimiento, televisión, deporte y formatos
visuales. El ranking combina interacción observable, velocidad, recencia,
presencia en varias plataformas, coincidencia con tendencias y afinidad con
formatos compartibles.

> El score es una heurística. No predice ni garantiza likes, alcance o ingresos.

## Fuentes

### Funcionan sin claves

- Google News España y búsquedas temáticas mediante RSS.
- Selecciones editoriales de medios españoles: EL PAÍS (incluido su RSS
  oficial de «Lo más visto»), MARCA Tiramillas, 20minutos Virales, El HuffPost
  Virales, Cribeo Viral, AS Tikitakas, Antena 3 Virales, laSexta Virales,
  Telecinco Curioso/Virales, EL ESPAÑOL Virales y Público Tremending.
- Menéame mediante las secciones públicas **Populares** y **Más visitadas**.
- Google Trends España mediante RSS.
- Bluesky mediante sus endpoints públicos.
- Tendencias públicas de Mastodon en `masto.es` y `mastodon.social`.

Las secciones editoriales, salvo el RSS oficial de «Lo más visto» de EL PAÍS,
se consultan mediante búsquedas restringidas de Google News RSS. El panel no
raspa directamente el HTML de esos medios y solo conserva titular, enlace,
fecha, miniatura disponible y etiqueta de fuente. La interfaz incorpora el
filtro **Medios virales** para aislar estas piezas.

### Opcionales

- **Reddit:** votos, comentarios, recencia y publicaciones visuales de
  comunidades españolas y globales. Requiere credenciales OAuth.
- **YouTube:** vídeos populares en España con visualizaciones, likes y
  comentarios. Requiere una clave de YouTube Data API.
- **X:** tendencias de España y volumen de publicaciones cuando está disponible.
  Requiere un token de la API de X, que puede tener coste.

Facebook no está incluido como rastreo general: Meta no ofrece un feed público
de “tendencias de España” para este uso. El acceso automatizado a páginas
públicas requiere una aplicación de Meta, permisos aprobados y, según el caso,
revisión de la aplicación. No se recomienda hacer scraping de Facebook.



## Previsualizaciones verificadas

Esta versión no entrega directamente al navegador las miniaturas remotas. En
cada actualización, el workflow selecciona y descarga una imagen asociada al
contenido, la valida y la publica dentro de `docs/media/`. Esto evita enlaces
caducados, bloqueos de hotlink y miniaturas genéricas.

La selección se adapta a cada tipo de fuente:

- **Medios y Menéame:** consulta `og:image`, Twitter Card, Schema.org,
  `media:content`, enclosures e imágenes del cuerpo del artículo.
- **Reddit:** prioriza la imagen original de `preview`, galerías y resoluciones
  alternativas antes que la miniatura pequeña.
- **Bluesky:** usa imágenes, miniaturas de vídeo o tarjetas externas del embed.
- **Mastodon:** compara los adjuntos y sus tamaños `preview` y `original`.
- **YouTube:** prueba `maxres`, `standard`, `high` y tamaños inferiores hasta
  encontrar la mejor miniatura válida.

Se rechazan logos, avatares, placeholders, píxeles de seguimiento, imágenes
pequeñas, proporciones extremas y archivos excesivamente pesados. Entre los
candidatos válidos se favorecen la fuente principal, los metadatos editoriales,
la coincidencia del texto alternativo con el titular y una resolución adecuada.
Si no hay una imagen fiable, el panel muestra un placeholder en vez de una
imagen posiblemente incorrecta.

## Diseño de lectura

La interfaz muestra **una noticia por fila**. En escritorio, cada fila separa
claramente la posición, la imagen, el titular y señales, y el score con el botón
para abrir el original. En móvil se reorganiza en una sola columna sin perder
la posición ni el potencial viral.

## Instalar esta versión en el repositorio

Sustituye los archivos del repositorio por los de esta carpeta y ejecuta:

```bash
git add -A
git commit -m "Verificar y almacenar previsualizaciones"
git push origin main
```

El `push` inicia el workflow automáticamente. También se puede ejecutar desde:

`Actions → Actualizar y publicar radar viral → Run workflow`

En **Settings → Pages**, la fuente debe estar configurada como
**GitHub Actions**.

## Activar Reddit

Antes de utilizar Reddit, revisa sus condiciones de la Data API y solicita u
obtén las credenciales correspondientes. Para un proyecto editorial o
comercial pueden existir requisitos adicionales.

En GitHub abre:

`Settings → Secrets and variables → Actions → Secrets → New repository secret`

Crea estos secretos:

```text
REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET
```

Opcionalmente, en la pestaña **Variables**, crea:

```text
REDDIT_USER_AGENT
```

Ejemplo de valor:

```text
PulsoNoticias/2.0 by u/TU_USUARIO
```

Comunidades configuradas inicialmente:

```text
spain, Espana, es, askspain, yo_elvr, MemesEnEspanol,
HistoriasDeReddit, Asi_va_Espana
```

Y para contenido visual global:

```text
Unexpected, AnimalsBeingDerps, ContagiousLaughter, MadeMeSmile
```

Puedes cambiarlas añadiendo variables de repositorio separadas por comas:

```text
REDDIT_SUBREDDITS_ES
REDDIT_SUBREDDITS_GLOBAL
```

## Activar YouTube

1. Crea o elige un proyecto en Google Cloud.
2. Activa **YouTube Data API v3**.
3. Crea una API key y restríngela a esa API.
4. Añádela como secreto del repositorio:

```text
YOUTUBE_API_KEY
```

El generador consulta `videos.list` con `chart=mostPopular` y `regionCode=ES`.

## Activar tendencias de X

Añade como secreto:

```text
X_BEARER_TOKEN
```

El código consulta el endpoint oficial de tendencias para España. Comprueba
antes el precio y el acceso disponibles en tu cuenta de desarrollador de X.

## Cómo se calcula el potencial

El score, de 1 a 100, pondera:

- votos, likes, reposts, comentarios, visualizaciones e impulsos;
- interacción por hora y antigüedad;
- aparición del mismo tema en varias plataformas o fuentes;
- aparición en una sección editorial viral o en «Lo más visto»;
- coincidencia con Google Trends y, si está configurado, X Trends;
- presencia de imagen o vídeo;
- afinidad con entretenimiento, humor, animales, curiosidades y cultura popular;
- penalización de política, sucesos duros y contenido sensible.

Los pesos están en `fetch_news.py` y pueden ajustarse a partir del rendimiento
real de las publicaciones. Conviene guardar, fuera de este panel, el score de
cada candidato y los resultados posteriores para recalibrarlo con datos propios.

## Publicación responsable

El panel es una herramienta de descubrimiento y siempre enlaza al original.
Antes de republicar contenido de una red social:

- verifica que la historia sea cierta y conserve su contexto;
- confirma los derechos de uso de imagen, vídeo y texto;
- acredita al autor y a la plataforma cuando corresponda;
- evita exponer datos personales o amplificar contenido retirado;
- revisa las condiciones de la API y de la plataforma, especialmente para usos
  comerciales.

## Probarlo localmente

```bash
python -m venv .venv
```

Activa el entorno e instala las dependencias:

```bash
# Git Bash / macOS / Linux
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate

python -m pip install -r requirements.txt
python fetch_news.py
python -m http.server 8000 --directory docs
```

Abre `http://localhost:8000`.

## Archivos principales

- `fetch_news.py`: consulta, filtra, agrupa y puntúa las fuentes.
- `docs/index.html`: interfaz y filtros del panel.
- `docs/data.json`: datos generados antes de cada despliegue.
- `docs/media/`: previsualizaciones verificadas y almacenadas por el workflow.
- `.github/workflows/update.yml`: actualización y publicación cada ~45 minutos.

Si todas las fuentes fallan, el proceso termina sin sustituir el despliegue
anterior. Si falla solo una fuente, el panel sigue publicándose y muestra su
estado y los avisos de la actualización.
