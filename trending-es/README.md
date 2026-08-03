# Pulso — trending news España

Dashboard que agrupa titulares de varios medios españoles, les pone una
puntuación de "viralidad" y los muestra en una web, actualizándose solo
cada ~45 minutos con GitHub Actions.

## Cómo ponerlo en marcha (10 minutos)

1. **Crea un repo en GitHub** (puede ser privado o público) y sube esta
   carpeta entera tal cual está:
   ```bash
   cd trending-es
   git init
   git add .
   git commit -m "Primer commit: pulso de noticias"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
   git push -u origin main
   ```

2. **Activa GitHub Pages**: en el repo, ve a *Settings → Pages*, y en
   "Build and deployment" elige *Deploy from a branch*, rama `main`,
   carpeta `/docs`. Guarda. En 1-2 minutos tu dashboard estará en
   `https://TU_USUARIO.github.io/TU_REPO/`.

3. **Lanza el workflow una vez a mano** para generar el primer
   `data.json`: en el repo ve a la pestaña *Actions* → "Actualizar
   noticias trending" → *Run workflow*. A partir de ahí se ejecutará
   solo cada ~45 minutos.

4. Si el repo es **privado**: revisa en *Settings → Actions → General*
   que los workflows tengan permiso de "Read and write permissions"
   (para poder commitear `data.json` automáticamente).

## Notas

- **Fuentes**: Google News España (RSS) y Meneame (RSS), sin necesidad
  de API key. Google Trends España se consulta con `pytrends`; esta
  librería depende de una API no oficial de Google que a veces cambia,
  así que el script está preparado para seguir funcionando (sin ese
  dato extra) si Trends falla un día.
- **Cómo se calcula el score**: nº de fuentes distintas × 10 + nº de
  menciones × 2, con un extra de +25 si el tema coincide con algo en
  tendencia en Google Trends España. Es un punto de partida simple:
  puedes ajustar los pesos en `score_cluster()` dentro de
  `fetch_news.py`.
- **Añadir más medios**: añade entradas al diccionario `SOURCES` en
  `fetch_news.py` con la URL del RSS de cada medio (El País, ABC, La
  Vanguardia, Marca... casi todos tienen RSS público).
- **Coste**: con la cadencia de 45 min configurada en el workflow, el
  consumo mensual de minutos de GitHub Actions ronda 1.000-2.000 min,
  dentro de la cuota gratuita incluso en repos privados.
