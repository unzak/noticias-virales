# Radar viral para GitHub Pages

Proyecto estático que consulta feeds RSS/Atom, genera `docs/data.json` y publica la carpeta `docs` en GitHub Pages cada 15 minutos.

## Subirlo a GitHub

```bash
git init
git add .
git commit -m "Publicar radar viral"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

Después, en GitHub:

1. Abre **Settings → Pages**.
2. En **Build and deployment → Source**, selecciona **GitHub Actions**.
3. Abre **Actions → Actualizar y publicar radar viral**.
4. Pulsa **Run workflow** para comprobarlo inmediatamente.

La web quedará normalmente en:

```text
https://TU_USUARIO.github.io/TU_REPOSITORIO/
```

## Programación

El cron está en `.github/workflows/update.yml`:

```yaml
- cron: '7,22,37,52 * * * *'
```

GitHub interpreta los calendarios en UTC. Como se trata de un intervalo fijo de 15 minutos, el cambio horario no afecta a la frecuencia.

## Prueba local

```bash
python fetch_news.py
python -m http.server 8000 --directory docs
```

Abre `http://localhost:8000`.

## Diagnóstico

Si la ejecución manual falla, abre la pestaña **Actions**, entra en la ejecución roja y revisa el primer paso fallido. El archivo `docs/last-update.txt` permite comprobar qué versión se publicó.
