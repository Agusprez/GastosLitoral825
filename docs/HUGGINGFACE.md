# Desplegar en Hugging Face Spaces (gratis)

HF Spaces es la alternativa gratuita más cómoda para esta app: **16 GB de RAM y
2 vCPU** en el plan free, el Space duerme recién después de ~48 h sin visitas y los
secretos se cargan desde el navegador. Con el sueño de Streamlit Community Cloud
(horas) esta app puede quedarse dormida en pleno uso familiar.

## 1. Crear el Space

1. Entrá a <https://huggingface.co/new-space>.
2. Nombre: `cuentas-claras`.
3. **SDK: Streamlit** (importante; no Gradio, no Docker).
4. Hardware: *CPU basic · FREE*.
5. Visibilidad: **Public** (los Spaces privados free no sirven para compartir con
   otras personas).
6. *Create Space*.

## 2. Subir el código

El repo ya trae la cabecera que HF necesita en `README.md` (`sdk: streamlit`,
`app_file: app.py`, `sdk_version: 1.37.0`), así que alcanza con copiar los archivos.

**Opción rápida (navegador):** *Files → Add file → Upload files* y subí:

```
app.py
requirements.txt
.streamlit/config.toml
cuentasclaras/…      (la carpeta completa)
vistas/…             (la carpeta completa)
```

**Opción git** (recomendada, y la única que actualiza bien después):

```bash
git clone https://huggingface.co/spaces/TU-USUARIO/cuentas-claras ../space-cc
python tools/publicar_space.py --destino ../space-cc
cd ../space-cc
git add -A && git commit -m "Cuentas Claras v2" && git push
```

`tools/publicar_space.py` copia sólo lo que el Space necesita (`app.py`,
`requirements.txt`, `.streamlit/config.toml`, `cuentasclaras/`, `vistas/`, `README.md`)
y **nunca** secretos, la base local ni las pruebas. Con `--verificar` revisa la
carpeta sin escribir nada.

> No subas `.streamlit/secrets.toml`, `data/` ni la clave de cifrado: en un Space
> público esos archivos los ve cualquiera y la service account da acceso a tu Drive.

## 3. Cargar los secretos

*Settings → Variables and secrets → New secret*. HF los inyecta como variables de
entorno con el nombre exacto que escribas. Nombres recomendados (la app los acepta
con y sin el prefijo `CUENTASCLARAS_`):

| Nombre | Valor |
| --- | --- |
| `CUENTASCLARAS_HOJA_URL` | URL de la planilla de Google (la de siempre) |
| `CUENTASCLARAS_GCP_CREDENCIALES` | El JSON completo de la service account, en una línea |
| `CUENTASCLARAS_CLAVE_CIFRADO` | La clave de `tools/generar_clave.py` |
| `CUENTASCLARAS_IMGBB_API_KEY` | Tu API key de imgbb (opcional, para comprobantes) |
| `CUENTASCLARAS_ADMINS` | Tu email, para ver el panel de plataforma |
| `CUENTASCLARAS_URL_PUBLICA` | `https://TU-USUARIO-cuentas-claras.hf.space` |

Si el JSON no entra en un secreto (algunos paneles tienen tope de tamaño), cargá
las partes y la app las arma sola:

| Nombre | Valor |
| --- | --- |
| `CUENTASCLARAS_GCP_CLIENT_EMAIL` | `cuentas-claras@tu-proyecto.iam.gserviceaccount.com` |
| `CUENTASCLARAS_GCP_PRIVATE_KEY` | La clave privada completa (los `\n` literales están bien) |
| `CUENTASCLARAS_GCP_PROJECT_ID` | `tu-proyecto` (opcional) |

Después de cargarlos: *Settings → Factory rebuild* (o *Restart Space*).

## 4. Verificar

1. El Space arranca en `https://TU-USUARIO-cuentas-claras.hf.space`.
2. Aparece la landing de Cuentas Claras y podés registrarte.
3. En la planilla se crean las pestañas `cc_*`.
4. *Hogar → Invitaciones → Generar código*: el mensaje de WhatsApp debe traer el
   link del Space (por eso `CUENTASCLARAS_URL_PUBLICA`).

## Cosas a tener en cuenta

* **Misma base, misma clave.** Si dejás Streamlit Cloud y HF apuntando a la misma
  planilla, los dos tienen que usar **la misma `clave_cifrado`**; si no, cada uno
  escribe datos que el otro no puede leer.
* **Sueño.** A las ~48 h sin visitas el Space se duerme; la primera visita tarda
  ~30 s en despertarlo. Es mucho más benigno que las pocas horas de Streamlit.
* **Disco efímero.** Igual que en Streamlit Cloud: la base va en Google Sheets y las
  fotos en imgbb (o Drive). Si las dejás en disco, se pierden al reiniciar.
* **Un Space = un despliegue.** Para clientes distintos, usá el plan Pro y más
  Spaces, o pasá a un VPS cuando el volumen lo justifique.
* **Dominio propio.** HF permite asociar un dominio (función de pago); con el plan
  free quedás en `*.hf.space`.

## Volver atrás

El Space no toca las pestañas viejas (`Gastos`, `Lista_Compras`) ni la app de
Streamlit: si algo sale mal, borrás el Space y seguís usando la otra. Los datos
siguen en la planilla.
