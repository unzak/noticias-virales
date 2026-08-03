# Pulso — noticias en tendencia en España

Dashboard estático que agrupa titulares recientes, detecta temas repetidos y
les asigna un **score heurístico** combinando:

- número de medios distintos;
- número de menciones del tema;
- recencia;
- coincidencia con Google Trends España.

> El score no mide compartidos, visitas ni interacciones reales en redes sociales.

## Publicarlo en GitHub Pages

1. Sube esta carpeta completa a un repositorio de GitHub.
2. Abre **Settings → Pages**.
3. En **Build and deployment → Source**, selecciona **GitHub Actions**.
4. Abre **Actions → Actualizar y publicar noticias trending**.
5. Pulsa **Run workflow**, elige la rama `main` y vuelve a pulsar
   **Run workflow**.
6. Cuando termine en verde, abre el trabajo y entra en la URL mostrada en
   **deployments**, o prueba:
   `https://TU_USUARIO.github.io/TU_REPOSITORIO/`.

No selecciones `Deploy from a branch`: el workflow genera `docs/data.json` y
publica la carpeta `docs` directamente como artefacto de GitHub Pages.

No hacen falta tokens personales ni claves API. GitHub crea automáticamente el
`GITHUB_TOKEN` temporal que necesita el despliegue.

## Archivos principales

- `fetch_news.py`: descarga, limpia, agrupa y puntúa las noticias.
- `docs/index.html`: interfaz pública.
- `docs/data.json`: marcador inicial; el workflow lo sustituye antes de publicar.
- `.github/workflows/update.yml`: generación y despliegue manual, con cada push
  relevante y cada ~45 minutos.

## Probarlo localmente

```bash
python -m venv .venv
```

Activa el entorno:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Instala y ejecuta:

```bash
python -m pip install -r requirements.txt
python fetch_news.py
python -m http.server 8000 --directory docs
```

Abre `http://localhost:8000`.

## Notas operativas

- Si falla una fuente pero otra funciona, el panel se actualiza y deja el aviso
  en el JSON desplegado.
- Si fallan todas las fuentes de noticias, el job termina con error y GitHub
  conserva el despliegue anterior.
- Las ejecuciones programadas pueden retrasarse; el cron está desplazado del
  minuto cero para reducir ese riesgo.
