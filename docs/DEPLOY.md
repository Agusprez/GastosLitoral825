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
* Si usás comprobantes en Drive, verificá que la service account tenga acceso a la
  carpeta (`drive_carpeta_id`).
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

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.headless", "true"]
```

```bash
docker build -t cuentasclaras .
docker run -d --name cuentasclaras -p 8501:8501 \
  -v "$PWD/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
  -v "$PWD/data:/app/data" \
  cuentasclaras
```

Si usás SQLite, el volumen `data` es obligatorio y contiene la clave de cifrado.

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
| `CUENTASCLARAS_MEDIOS` | `local` \| `drive` | Comprobantes |
| `CUENTASCLARAS_DRIVE_CARPETA_ID` | `1AbC…` | Carpeta de Drive |
| `CUENTASCLARAS_PRECIO_MENSUAL` | `4.900` | Precio mostrado |
| `CUENTASCLARAS_PRECIO_ANUAL` | `49.000` | Precio mostrado |
| `CUENTASCLARAS_DEMO` | `1` | Datos de ejemplo (nunca en producción) |

## Checklist antes de abrir al público

- [ ] `clave_cifrado` configurada y guardada fuera del servidor.
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
