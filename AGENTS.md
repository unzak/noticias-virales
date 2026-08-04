# AGENTS.md — Pulso Viral / noticias-virales

## Objetivo del proyecto

Mantener un panel editorial estático para detectar contenidos con potencial viral en España, orientado a un estilo de entretenimiento compartible similar a Cabronazi. No es un agregador generalista de actualidad.

## Estado funcional que debe conservarse

- El repositorio se publica mediante GitHub Pages y GitHub Actions.
- La web está en `docs/index.html`.
- Los datos generados están en `docs/data.json`.
- Las imágenes verificadas se guardan en `docs/media/`.
- El generador principal es `fetch_news.py`.
- Las dependencias están en `requirements.txt`.
- El workflow está en `.github/workflows/update.yml`.
- El panel publica como máximo 100 resultados.
- Solo admite contenidos cuya fecha pueda verificarse dentro de las últimas 24 horas.
- La interfaz muestra una noticia por fila y usa numeración `#01`, `#02`, etc.
- Google Trends debe mostrar cada tendencia con una noticia asociada cuando exista una noticia válida de las últimas 24 horas.
- Menéame debe consultar `Populares` y `Más visitadas`; la imagen debe extraerse del artículo destino, nunca de una miniatura genérica de Menéame.
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
- comida, viajes, trucos, nostalgia e historias positivas.

Reducir fuertemente:

- política institucional;
- economía generalista;
- tribunales, guerra y sucesos sin ángulo claramente viral;
- noticias duplicadas o titulares equivalentes;
- contenidos sin imagen útil o sin fecha verificable.

Las piezas políticas solo deben entrar cuando tengan un ángulo viral inequívoco. Mantener límites de diversidad por medio y categoría para evitar que una fuente monopolice el ranking.

## Fuentes principales

Conservar y revisar periódicamente:

- secciones virales y de entretenimiento de medios españoles;
- búsquedas temáticas mediante Google News RSS;
- Menéame `Populares` y `Más visitadas`;
- Google Trends España y noticias relacionadas;
- Bluesky y Mastodon públicos;
- integraciones opcionales de Reddit, YouTube y X.

No asumir que una fuente funciona porque devuelve HTTP 200. Registrar por fuente: elementos brutos, elementos válidos de 24 horas, fallos y fallback usado.

## Imágenes

Para cada contenido, seleccionar la imagen que mejor represente el artículo:

1. Resolver el destino final real.
2. Comparar `og:image`, `twitter:image`, JSON-LD, RSS y fotos del cuerpo.
3. Para Menéame, abrir siempre la noticia destino.
4. Rechazar logos, avatares, banners, placeholders, píxeles, imágenes pequeñas o genéricas.
5. Verificar tipo, dimensiones, proporción y relación semántica con el titular.
6. Guardar localmente las imágenes válidas en `docs/media/`.
7. Si no hay una imagen fiable, usar el placeholder del panel antes que una imagen incorrecta.

## Reglas de implementación

- Antes de editar, leer `README.md`, `fetch_news.py`, `docs/index.html` y `.github/workflows/update.yml`.
- Buscar funciones duplicadas antes de añadir helpers nuevos.
- Hacer cambios pequeños y localizados; evitar reescrituras masivas de `fetch_news.py` sin necesidad.
- No introducir secretos, tokens, cookies ni credenciales en archivos versionados.
- No añadir scraping que incumpla las condiciones de una plataforma.
- Mantener compatibilidad con Python 3.11.
- No editar manualmente `docs/data.json` como solución permanente; debe generarlo `fetch_news.py`.
- Mantener la web sin framework y compatible con GitHub Pages, salvo petición expresa.
- Cuando cambie el comportamiento visible, actualizar `README.md`.
- No hacer `git push`, crear PR ni desplegar sin autorización explícita del usuario.

## Workflow y despliegue

- Validar que `.github/workflows/update.yml` use acciones compatibles con Node.js 24.
- El workflow debe compilar `fetch_news.py`, generar datos, validar JSON, comprobar `docs/media/` y desplegar Pages.
- Usar:

```yaml
concurrency:
  group: pages
  cancel-in-progress: false
```

para evitar cancelaciones repetidas durante despliegues concurrentes.

## Comprobaciones obligatorias

Antes de dar una tarea por terminada, ejecutar como mínimo:

```bash
python -m py_compile fetch_news.py
python fetch_news.py
python -m json.tool docs/data.json > /dev/null
```

Cuando se modifique la interfaz:

- revisar que `docs/index.html` cargue `data.json`;
- comprobar que no haya errores evidentes de JavaScript;
- probar la vista de escritorio y una anchura móvil;
- confirmar una noticia por fila y funcionamiento de filtros.

Cuando se modifique el workflow:

```bash
git diff --check
```

Si las consultas de red impiden una prueba local completa, ejecutar pruebas unitarias o simuladas sobre las funciones modificadas y declarar con precisión qué queda pendiente de verificar en GitHub Actions.

## Forma de trabajar en cada tarea

1. Inspeccionar el estado real del repositorio y `git status`.
2. Explicar brevemente el diagnóstico y el plan.
3. Implementar el cambio.
4. Ejecutar las comprobaciones pertinentes.
5. Revisar el diff buscando regresiones, funciones duplicadas y cambios accidentales.
6. Entregar un resumen con archivos modificados, pruebas realizadas y riesgos pendientes.
7. Esperar autorización antes de commit, push o despliegue, salvo que el usuario lo pida explícitamente.
