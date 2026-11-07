# Despliegue

## Opción A — Streamlit Community Cloud (más rápido, gratis)

1. Subí el repo a GitHub.
2. En <https://share.streamlit.io> → *New app* → repo, rama y `app.py`.
3. *Settings → Secrets* y pegá el contenido de `.streamlit/secrets.toml`
   (`sheet_url_gastos`, `gcp_service_account`, `clave_cifrado`, `admins`…).
4. *Advanced settings → Python version*: 3.11.
5. Deploy. La primera carga tarda ~1 minuto (instala dependencias).

Consideraciones:

* **El disco es efímero.** Por eso la base es Google Sheets y no SQLite. Con
  `almacen = "sqlite"` se pierde todo en cada reinicio.
* La app se duerme tras un rato sin uso; el primer acceso tarda unos segundos.
* **Comprobantes:** con `imgbb_api_key` se suben a imgbb (como en la v1) y
  sobreviven a los reinicios. Con `drive_carpeta_id` van a tu Drive, pero la
  carpeta tiene que estar compartida con el `client_email` de la service account.
  Si no configurás ninguno, se guardan en el disco del servidor y **se pierden** al
  reiniciar: en la nube, elegí imgbb o Drive.
* No uses el plan gratuito para datos de clientes que paguen: no hay SLA.

## Opción B — VPS propio (más control)

Requisitos: Python 3.11+, 1 GB de RAM (sobra), un dominio y HTTPS (Caddy o Nginx).

```bash
git clone <repo> cuentasclaras && cd cuentasclaras
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# editar secretos: sheet_url_gastos, gcp_service_account, clave_cifrado, admins
.venv/bin/python tools/generar_clave.py     # pegarla en clave_cifrado
```

`/etc/systemd/system/cuentasclaras.service`:

```ini
[Unit]
Description=Cuentas Claras
After=network.target

[Service]
User=cuentas
WorkingDirectory=/srv/cuentasclaras
ExecStart=/srv/cuentasclaras/.venv/bin/streamlit run app.py \
  --server.port 8501 --server.headless true --server.enableXsrfProtection true
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cuentasclaras
sudo journalctl -u cuentasclaras -f
```

`/etc/caddy/Caddyfile`:

```
cuentasclaras.tudominio.com {
    reverse_proxy 127.0.0.1:8501
}
```

Con VPS tenés disco propio: podés usar `almacen = "sqlite"` y comprobantes locales
(`medios = "local"`), con la ventaja de que no dependés de Google. En ese caso:

* Backup: `cp data/cuentasclaras.db` + `data/comprobantes/` + `data/clave.key`.
* Permisos: `chmod 600 data/clave.key` y la base también.

### Docker

El repo ya trae un `Dockerfile` listo (instala dependencias, expone 8501 y define
un healthcheck en `/_stcore/health`):

```bash
docker build -t cuentasclaras .
docker run -d --name cuentasclaras -p 8501:8501 \
  -e CUENTASCLARAS_HOJA_URL="https://docs.google.com/spreadsheets/d/XXXX/edit" \
  -e CUENTASCLARAS_GCP_CREDENCIALES="$(cat service-account.json | tr -d '\n')" \
  -e CUENTASCLARAS_CLAVE_CIFRADO="la-clave" \
  -e CUENTASCLARAS_IMGBB_API_KEY="la-api-key" \
  cuentasclaras
```

Si usás SQLite o comprobantes en disco, montá un volumen en `/app/data` (ahí viven
la base, la clave y las imágenes).

## Opción C — landing estática en GitHub Pages (gratis)

GitHub Pages **sólo sirve archivos estáticos**: no puede correr Streamlit (necesita
Python, sesiones y las credenciales de Google). Lo que sí conviene publicar ahí es
la landing de venta, que ya está lista en `web/index.html`.

1. En GitHub: *Settings → Pages*.
2. *Source*: **Deploy from a branch** → *Branch*: `main` → carpeta **`/web`** → *Save*.
3. En un minuto queda en `https://agusprez.github.io/GastosLitoral825/`.

Los botones de esa landing ya apuntan a la app (`litoral825.streamlit.app`). Si
cambiás de dominio, buscá y reemplazá esa URL en `web/index.html`.

## ¿Hostear la app gratis? Comparación

La app es **sin estado** (los datos viven en Google Sheets y las fotos en imgbb), así
que cualquier host que corra Python sirve. Los límites de los planes gratuitos
cambian seguido: confirmalos en la página del proveedor antes de decidir.

| Servicio | Gratis | Se duerme | Memoria | Secretos | Cuándo conviene |
| --- | --- | --- | --- | --- | --- |
| **Streamlit Community Cloud** | Sí | Tras varias horas sin uso | ~1 GB | Secrets (TOML) | Es donde ya está. Cero configuración, pero sin SLA. **La única opción gratis 100 % sin tarjeta para correr la app.** |
| **Hugging Face Spaces** | Sólo *Static* | — | — | — | Desde 2026 los Spaces que ejecutan código (Gradio/Docker, y con ellos Streamlit) requieren **PRO, USD 9/mes** ([precios](https://huggingface.co/pricing)). Sirve gratis para la landing. |
| **Render** (free web service) | Sí | A los ~15 min sin tráfico | 512 MB | *Environment* | Se conecta al repo; el arranque en frío tarda ~30-60 s. Confirmá el plan free en [su doc](https://render.com/docs/free). |
| **Google Cloud Run** | Cupo mensual gratis (pide tarjeta) | Scale to zero | configurable | Secret Manager / env | Si ya usás Google Cloud y querés HTTPS propio. |
| **Fly.io** | Cupo chico (pide tarjeta) | No | 256-512 MB | `fly secrets` | Control fino, regiones cercanas. |
| **Oracle Cloud Always Free** | Sí (VM ARM, pide tarjeta) | No | hasta 24 GB | variables de entorno | "Siempre encendido" sin pagar, pero administrás el sistema operativo. |
| **VPS chico** | No (~USD 4-5/mes) | No | 1 GB | archivo | Lo más predecible para vender el servicio. |

**Recomendación:** si el objetivo es cero costo y cero tarjeta, **quedate en
Streamlit Cloud** (ya funciona; el sueño sólo agrega unos segundos al primer
acceso) y publicá la landing en GitHub Pages o en un Space *Static* de HF. Si te
molesta el sueño, la salida gratis "de verdad" es una VM Oracle Always Free o un VPS
de ~USD 4.

### Receta: Hugging Face Spaces (requiere PRO)

Detalle completo en [`HUGGINGFACE.md`](HUGGINGFACE.md). Resumen: Space con SDK
**Docker** (el repo trae `Dockerfile`), cabecera `sdk: docker` + `app_port: 8501`,
secretos en *Settings → Variables and secrets* y `python tools/publicar_space.py`
para copiar sólo lo necesario.

### Receta: Hugging Face Space estático (gratis, para la landing)

1. `huggingface.co/new-space` → SDK **Static** → plantilla **Blank**.
2. Subí `web/index.html` como `index.html`.
3. `README.md` con `sdk: static`.
4. Queda en `https://TU-USUARIO-cuentas-claras.static.hf.space`.

### Receta: Render

1. *New → Web Service* → conectá el repo.
2. Runtime **Docker** (usa el `Dockerfile` del repo) o **Python** con
   `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.
3. *Environment*: las mismas variables `CUENTASCLARAS_*` del ejemplo de arriba.
4. Plan **Free** → *Deploy*. La primera visita después de 15 minutos tarda en
   despertar.

## Variables de entorno (alternativa a los secretos)

Cualquier clave de configuración se puede pasar como `CUENTASCLARAS_*`:

| Variable | Ejemplo | Para qué |
| --- | --- | --- |
| `CUENTASCLARAS_ALMACEN` | `sheets` \| `sqlite` | Base de datos |
| `CUENTASCLARAS_SQLITE_RUTA` | `data/cuentasclaras.db` | Archivo local |
| `CUENTASCLARAS_HOJA_URL` | `https://docs.google.com/...` | Planilla |
| `CUENTASCLARAS_GCP_CREDENCIALES` | JSON en una línea | Service account |
| `CUENTASCLARAS_CLAVE_CIFRADO` | base64 | Clave maestra |
| `CUENTASCLARAS_CLAVE_ARCHIVO` | `data/clave.key` | Dónde está la clave local |
| `CUENTASCLARAS_CIFRADO` | `0` para desactivar | Sólo pruebas |
| `CUENTASCLARAS_ADMINS` | `a@x.com,b@x.com` | Panel de plataforma |
| `CUENTASCLARAS_REGISTRO_ABIERTO` | `0` | Cerrar inscripciones |
| `CUENTASCLARAS_MEDIOS` | `imgbb` \| `drive` \| `local` | Comprobantes |
| `CUENTASCLARAS_IMGBB_API_KEY` | `abc123…` | Subir comprobantes a imgbb |
| `CUENTASCLARAS_DRIVE_CARPETA_ID` | `1AbC…` | Carpeta de Drive |
| `CUENTASCLARAS_URL_PUBLICA` | `https://…` | Link que va en las invitaciones |
| `CUENTASCLARAS_PRECIO_MENSUAL` | `4.900` | Precio mostrado |
| `CUENTASCLARAS_PRECIO_ANUAL` | `49.000` | Precio mostrado |
| `CUENTASCLARAS_DEMO` | `1` | Datos de ejemplo (nunca en producción) |

`CUENTASCLARAS_GCP_CREDENCIALES` acepta el JSON completo en una sola línea (es la
forma práctica en hosts con contenedores): la app lo detecta y lo parsea.

## Checklist antes de abrir al público

- [ ] `clave_cifrado` configurada y guardada fuera del servidor.
- [ ] Backend de comprobantes elegido: `imgbb_api_key` (persistente) o `drive_carpeta_id` (privado). Si no, se guardan en disco y se pierden al reiniciar.
- [ ] Planilla compartida **sólo** con la service account.
- [ ] `admins` con tu email; probaste el panel de plataforma.
- [ ] `registro_abierto` decidido (abierto o sólo por invitación).
- [ ] Backup probado: exportar JSON de un hogar y abrirlo.
- [ ] Precios reales en `precio_mensual` / `precio_anual`.
- [ ] Términos y privacidad revisados (`docs/TERMINOS.md`).
- [ ] Soporte: `soporte_email` con alguien que responda.
- [ ] Probaste en celular (la app es responsive, pero revisá las tablas).
- [ ] Un usuario de prueba completo: registro → código → gasto → saldo → CSV.

## Problemas frecuentes

| Síntoma | Causa probable |
| --- | --- |
| "No pudimos conectarnos al almacenamiento" | Credenciales de Google mal pegadas, planilla no compartida con la service account o API deshabilitada. |
| "No se pudieron descifrar los datos" | `clave_cifrado` distinta a la que cifró los datos. |
| Los datos aparecen vacíos después de reiniciar | Estás en Streamlit Cloud con `almacen = "sqlite"` (disco efímero). |
| "El archivo supera los 5 MB" | Bajá la foto o subí `max_comprobante_mb`. |
| Las pestañas no aparecen en la planilla | La app las crea al primer uso; verificá que la service account sea Editor. |
| `APIError: A sheet with the name "gastos" already exists` | Versión anterior con el prefijo sin aplicar. Actualizá a la última: la app usa `cc_*` y renombra solas las pestañas sueltas. Si persiste, revisá que no haya una `cc_gastos` con otro encabezado. |
| Pestañas `usuarios`, `hogares`… sin prefijo | Las creó esa versión anterior. En el próximo arranque la app las renombra a `cc_usuarios`, `cc_hogares`, etc. conservando los datos. |
| "La planilla ya tiene una pestaña X con otro formato" | Hay una pestaña con el nombre que la app necesita pero con encabezado ajeno. Renombrala (`X_viejo`) o cambiá `prefijo_hojas`. |
| "imgbb respondió 400. Invalid API key" | La `imgbb_api_key` no es válida o falta. Revisá los Secrets; mientras tanto los comprobantes se guardan en disco. |
| Los comprobantes desaparecen después de reiniciar | Están en disco (`medios = "local"`). Configurá `imgbb_api_key` o `drive_carpeta_id`. |
