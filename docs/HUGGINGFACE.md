# Hugging Face Spaces

> **Actualizado 2026:** Hugging Face dejó de ofrecer cómputo gratis. Los Spaces
> **Static** siguen siendo gratuitos; los que ejecutan código (Gradio, Docker —
> y con ellos cualquier app Python como ésta) requieren **PRO, USD 9/mes**
> ([precios](https://huggingface.co/pricing)). Con la cuenta free, el selector de
> SDK muestra Static habilitado y Gradio/Docker con la etiqueta *Paid*.
>
> Conclusión práctica: **HF ya no sirve para hostear la app gratis**, pero sí para
> publicar la landing.

## A. Landing gratis en un Space estático (lo que sí es gratis)

1. <https://huggingface.co/new-space> → nombre `cuentas-claras` → **SDK: Static** →
   plantilla **Blank** → visibilidad pública.
2. Subí el contenido de `web/` a la raíz del Space: `index.html` (y nada más).
3. El `README.md` del Space necesita esta cabecera:

   ```yaml
   ---
   title: Cuentas Claras
   emoji: 💸
   sdk: static
   ---
   ```

4. Queda en `https://TU-USUARIO-cuentas-claras.static.hf.space`.
   Los botones de la landing ya apuntan a la app en Streamlit Cloud.

Es la misma landing que podés publicar en GitHub Pages
(`docs/DEPLOY.md`, Opción C). Elegí uno; los dos son gratis.

## B. La app en un Space de cómputo (requiere PRO)

Si en algún momento pagás PRO, el camino más sólido es **Docker**, porque el SDK de
Streamlit no siempre aparece en el selector:

1. El repo ya trae `Dockerfile` con el puerto 8501 y el healthcheck.
2. El `README.md` del Space tiene que declarar:

   ```yaml
   ---
   title: Cuentas Claras
   emoji: 💸
   colorFrom: teal
   colorTo: green
   sdk: docker
   app_port: 8501
   pinned: false
   ---
   ```

   (Ésa es exactamente la cabecera que tiene el README de este repo.)

3. `python tools/publicar_space.py --destino ../space-cc` copia al Space sólo lo
   necesario; después `git add -A && git commit && git push`.
4. *Settings → Variables and secrets*, con estos nombres (la app acepta con y sin
   el prefijo `CUENTASCLARAS_`):

   | Nombre | Valor |
   | --- | --- |
   | `CUENTASCLARAS_HOJA_URL` | URL de la planilla de Google |
   | `CUENTASCLARAS_GCP_CREDENCIALES` | JSON de la service account en una línea |
   | `CUENTASCLARAS_CLAVE_CIFRADO` | Clave de `tools/generar_clave.py` |
   | `CUENTASCLARAS_IMGBB_API_KEY` | API key de imgbb |
   | `CUENTASCLARAS_ADMINS` | Tu email |
   | `CUENTASCLARAS_URL_PUBLICA` | `https://TU-USUARIO-cuentas-claras.hf.space` |

   Si el JSON no entra en un secreto, usá las partes:
   `CUENTASCLARAS_GCP_CLIENT_EMAIL`, `CUENTASCLARAS_GCP_PRIVATE_KEY` y
   `CUENTASCLARAS_GCP_PROJECT_ID`.

5. *Factory rebuild*.

### Cuidados (válidos para cualquier host)

* **Misma planilla, misma clave.** Si convivís con Streamlit Cloud, los dos tienen
  que usar la misma `clave_cifrado`; si no, cada uno escribe datos que el otro no
  puede leer.
* **No subas** `.streamlit/secrets.toml`, `data/` ni la clave: en un Space público
  los ve cualquiera, y la service account da acceso a tu Drive.
* **Disco efímero:** la base va en Google Sheets y las fotos en imgbb o Drive.
