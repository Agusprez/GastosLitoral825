---
title: Cuentas Claras
emoji: 💸
colorFrom: teal
colorTo: green
sdk: docker
app_port: 8501
pinned: false
short_description: Gastos compartidos del hogar, sin planillas
---

# Cuentas Claras 💸

Gestión de **gastos compartidos del hogar** lista para ofrecerse como servicio:
varias personas, varios hogares, planes, límites, comprobantes privados y datos
cifrados. Nació de una app familiar de dos usuarios atada a una planilla de Google
(ver [`legacy/`](legacy/)) y ahora es un producto multiusuario.

> La cabecera YAML de arriba es la que necesita **Hugging Face Spaces** para correr
> el repo como app con el `Dockerfile` incluido (HF cobra eso: PRO, USD 9/mes; los
> Spaces *Static* son los únicos gratis). En GitHub se ve como una tabla chiquita y
> no afecta nada. Detalle y alternativas gratis en [`docs/DEPLOY.md`](docs/DEPLOY.md).

* **Base de datos:** Google Sheets (la misma planilla de siempre, en pestañas
  propias `cc_*`), o SQLite para desarrollo.
* **Datos cifrados** con ChaCha20 + HMAC-SHA256: si alguien abre la planilla, ve
  texto cifrado.
* **Arquitectura MVC** con tests: modelo (`cuentasclaras/modelos`), controladores
  (`cuentasclaras/controladores`) y vistas (`vistas`).
* **Streamlit** para la interfaz: se usa desde el navegador, sin instalar nada.

---

## Lo que resuelve

| Situación | Cómo queda |
| --- | --- |
| Compras del súper, servicios, salidas | Se cargan en segundos desde el celular, sacando la foto del ticket con la cámara. |
| "Yo puse más que vos" | El sistema reparte cada gasto y muestra quién le debe a quién, con el monto exacto. |
| Varias casas o familias | Cada hogar es independiente y una persona puede pertenecer a varios. |
| Invitar a alguien | Código de 6 caracteres + mensaje listo para copiar y pegar en WhatsApp (o abrir WhatsApp con el texto cargado). |
| Comprobantes | Con acceso controlado desde la app. Backend elegible: **imgbb** (el de siempre), Drive privado o disco. |
| Datos sensibles | Se guardan cifrados; las contraseñas con `scrypt`. |

## Qué cambió respecto de la versión 1

| Versión 1 (legacy) | Versión 2 |
| --- | --- |
| 2 usuarios fijos en el código | Registro abierto, usuarios ilimitados, contraseñas con hash `scrypt` |
| `st.secrets["passwords"]` comparado en texto plano | Hash por usuario + bloqueo tras 5 intentos fallidos |
| Cookie con el nombre del usuario (se podía editar) | Cookie con token opaco; la sesión vive hasheada en la base y se puede revocar |
| Una sola planilla, una sola casa | Multi-hogar con roles (propietario/admin/miembro) e invitaciones |
| Comprobantes en imgbb, sólo accesibles por link | Se mantiene imgbb (mismo `imgbb_api_key`) pero las imágenes se muestran sólo dentro del hogar; también se puede elegir Drive o disco |
| Sin planes ni límites | Plan Gratis y Pro con límites aplicados en el modelo |
| Sin exportación | CSV por período, JSON completo del hogar |
| Sin tests | 123 tests (modelo, controladores, vistas, cifrado, end-to-end) |

## Arquitectura (MVC)

```
app.py                      Punto de entrada: set_page_config + router de secciones
cuentasclaras/
  modelos/                  M · datos y reglas
    configuracion.py        Configuración desde secretos + entorno
    dinero.py               Fechas, montos, formato es-AR
    almacen.py              Persistencia: SheetsStore / SqliteStore / MemoryStore
    cifrado.py              ChaCha20 + HMAC (cifrado autenticado, sin dependencias)
    fabrica.py              Arma el almacén y le aplica cifrado
    autenticacion.py        scrypt, sesiones, bloqueo por intentos
    saldos.py               Reparto de gastos y cálculo de deudas
    planes.py               Planes, límites y precios
    archivos.py             Comprobantes (imgbb, Drive o disco)
    repositorio.py          Reglas de negocio + control de acceso por hogar
    datos_demo.py           Datos de ejemplo
  controladores/            C · casos de uso
    base.py                 Resultado + traducción de errores
    sesion.py               Login, registro, invitaciones, sesiones
    gastos.py               Alta/edición/baja, comprobantes, exportación
    compras.py              Lista de compras
    hogar.py                Personas, invitaciones, ajustes, pagos
    resumen.py              Tablero del período
    cuenta.py               Perfil, contraseña, baja
    planes.py               Estado de la suscripción y pedido de upgrade
    admin.py               Panel de plataforma
vistas/                     V · pantallas Streamlit
  componentes.py            Bootstrap de sesión, estilos, helpers
  navegacion.py             Barra lateral
  landing.py inicio.py gastos.py compras.py hogar.py cuenta.py planes.py admin.py
tools/                      Clave, importación de la v1, cifrado de datos existentes
tests/                      Modelo, controladores, vistas (dobles), end-to-end
web/index.html              Landing estática para publicar en GitHub Pages
legacy/                     La app original, como referencia
```

**Flujo de una acción** (por ejemplo, cargar un gasto):

1. La vista arma el formulario y llama a `ControladorGastos.agregar(...)`.
2. El controlador valida, guarda el comprobante y llama a `Repositorio.agregar_gasto`.
3. El repositorio verifica que la persona pertenezca al hogar, aplica el límite del
   plan, reparte el monto entre los participantes y escribe en el almacén.
4. El almacén cifra los campos y los guarda en la planilla.
5. El controlador devuelve un `Resultado` (ok/mensaje/datos) y la vista lo muestra.

Las vistas no deciden reglas de negocio y no acceden al almacén: eso hace que las
reglas se puedan testear sin Streamlit (y por eso este repo tiene 123 tests que
corren sin interfaz).

## Modelo de datos

Todo se guarda como filas de texto (una pestaña por tabla). Las columnas son
estables y el cifrado se aplica a todos los valores salvo `id`.

| Tabla | Contenido | Campos principales |
| --- | --- | --- |
| `usuarios` | Cuentas | `email`, `nombre`, `hash_clave`, `rol`, `activo`, `intentos_fallidos`, `bloqueado_hasta` |
| `hogares` | Casas / grupos | `nombre`, `moneda`, `plan`, `creado_por` |
| `miembros` | Quién pertenece a qué hogar | `hogar_id`, `usuario_id`, `rol`, `estado` |
| `gastos` | Movimientos | `fecha`, `concepto`, `monto`, `categoria`, `pagado_por`, `division`, `comprobante`, `estado` |
| `compras` | Lista de compras | `texto`, `estado`, `anotado_por`, `comprado_por` |
| `pagos` | Transferencias entre personas | `de_usuario`, `a_usuario`, `monto`, `fecha`, `nota` |
| `invitaciones` | Códigos para sumar gente | `codigo`, `rol`, `expira_en`, `usos`, `usos_max` |
| `sesiones` | Sesiones abiertas (token hasheado) | `usuario_id`, `expira_en`, `revocada`, `hogar_activo` |
| `eventos` | Auditoría del hogar | `accion`, `detalle`, `creado_en` |

`division` guarda un JSON `{usuario_id: monto}` con la parte exacta de cada persona,
calculada al cargar el gasto (así editar el hogar después no cambia la historia).

## Roles

| Rol | Puede |
| --- | --- |
| **Propietario/a** | Todo, incluido transferir la propiedad y eliminar el hogar. |
| **Administrador/a** | Invitar, quitar personas, cambiar roles, renombrar, ver actividad. |
| **Miembro** | Cargar/editar sus gastos, ver todo el hogar, usar la lista de compras. |

Los permisos se verifican en `Repositorio.exigir()`; si una vista olvidara filtrar,
el modelo igual rechaza la operación. Hay tests específicos de aislamiento entre
hogares (`TestAislamiento`).

## Seguridad

| Riesgo | Mitigación |
| --- | --- |
| Contraseñas filtradas | `scrypt` con sal por usuario (`hashlib.scrypt`), comparación en tiempo constante. |
| Fuerza bruta | 5 intentos → 15 minutos de bloqueo, mensaje genérico (no revela si el email existe). |
| Robo de cookie | La cookie lleva un token aleatorio; en la base sólo el SHA-256. Se revoca al cerrar sesión o cambiar la contraseña. |
| Planilla leída por terceros | Cifrado ChaCha20 + HMAC de todos los valores (autenticado: detecta ediciones a mano). |
| Comprobantes | Se muestran sólo a integrantes del hogar (verificación de membresía en el controlador). Con imgbb el link directo queda público-no-listado; con Drive o disco, privado. |
| Fuga entre hogares | Cada operación recibe el usuario y valida membresía antes de tocar datos. |
| Archivos maliciosos | Se validan formato, firma del archivo y tamaño máximo (5 MB por defecto). |

Detalles y límites en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Empezar en local (sin credenciales)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

set CUENTASCLARAS_DEMO=1        # PowerShell: $env:CUENTASCLARAS_DEMO=1
streamlit run app.py
```

Sin credenciales de Google, la app usa SQLite en `data/cuentasclaras.db`, genera
una clave de cifrado en `data/clave.key` y crea el hogar demo:

* Usuario: `demo@cuentasclaras.app`
* Contraseña: `CasaFuerte2026`

## Usar Google Sheets como base de datos (producción)

1. **Service account** en Google Cloud → habilitar *Google Sheets API* y *Google
   Drive API* → crear clave JSON.
2. **Planilla**: creá una hoja de cálculo y compartila con el `client_email` de la
   service account como **Editor**. La app va a crear ahí las pestañas `cc_*`.
3. **Secretos**: copiá `.streamlit/secrets.toml.example` a
   `.streamlit/secrets.toml` y completá `sheet_url_gastos` y `gcp_service_account`.
4. **Clave de cifrado**: `python tools/generar_clave.py` y pegá el resultado en
   `clave_cifrado`. Guardala también en un gestor de contraseñas: sin ella no se
   pueden leer los datos.
5. **Administración**: poné tu email en `admins` para ver el panel de plataforma.
6. **Arrancar** y registrarte.

> **Importante:** la planilla queda privada (sólo la service account). Si la
> compartís con las personas usuarias, pueden *ver* texto cifrado y *editar* filas
> (la app detectaría la manipulación, pero podrían romper datos). Para ofrecer el
> servicio, la planilla es infraestructura tuya, no del cliente.

Si ya tenías datos de la versión 1, seguí [`docs/MIGRACION.md`](docs/MIGRACION.md).

## Despliegue

Guía completa en [`docs/DEPLOY.md`](docs/DEPLOY.md): Streamlit Community Cloud
(con Secrets), landing gratis en GitHub Pages, comparación de hosts gratuitos
(Hugging Face Spaces, Render, Cloud Run, VPS) y despliegue con Docker.

## Planes

| | Gratis | Pro |
| --- | --- | --- |
| Hogares por cuenta | 1 | 5 |
| Personas por hogar | 3 | 15 |
| Gastos por mes | 200 | Ilimitados |
| Historial | 12 meses | Completo |
| Comprobantes | 20/mes | Ilimitados |
| Precio | $0 | $4.900/mes o $49.000/año |

Los límites se aplican en el modelo (`planes.LIMITES`), no en la interfaz. El cobro
hoy es manual: la persona pide el upgrade desde *Plan*, se coordina la
transferencia y el plan se activa desde el panel de plataforma. Para automatizarlo
hay que enchufar Mercado Pago/Stripe en `controladores/planes.py` (punto de
integración único).

## Operación

* **Backups:** *Hogar → Ajustes → Respaldo completo (JSON)* y el CSV por período.
  Además, la planilla se puede copiar desde Google Drive.
* **Rotar la clave de cifrado:** no está automatizado a propósito (requiere
  re-cifrar todo). Cambiarla sin re-cifrar deja los datos ilegibles; el paso a paso
  está en `docs/OPERACION.md`.
* **Límites de Google Sheets:** ~10 millones de celdas y cuotas de API por minuto.
  Con hogares de 2 a 10 personas y cientos de gastos por mes, sobra. Para miles de
  hogares hay que migrar a Postgres (el `Store` es una interfaz: se agrega un
  `PostgresStore` sin tocar el resto).
* **Comprobantes:** tres backends, en este orden de prioridad si no se fuerza
  `medios`: **imgbb** (si hay `imgbb_api_key`, es el servicio de la v1 — la imagen
  queda con link público-no-listado), **Drive** (privado, en la carpeta que se
  comparte con la service account) o **disco** (`data/comprobantes`, privado pero
  efímero en Streamlit Cloud: se pierde al reiniciar).
  En `docs/DEPLOY.md` está cómo elegir uno u otro.

## Tests

```bash
python -m unittest discover -s tests -t .
```

| Archivo | Qué cubre |
| --- | --- |
| `tests/test_core.py` | Dinero/fechas, `scrypt`, sesiones, contrato de almacenes, saldos, reglas, aislamiento entre hogares, cifrado (incluye vector RFC 8439). |
| `tests/test_controladores.py` | Casos de uso: registro, permisos, comprobantes, planes, admin, importador. |
| `tests/test_vistas.py` | Smoke de todas las pantallas con dobles de Streamlit/pandas; detecta parámetros inválidos de widgets. |
| `tests/test_app.py` | End-to-end: arranque real, demo, navegación por secciones y datos cifrados en disco. |

## Limitaciones conocidas

* La landing vive dentro de Streamlit (no tiene SEO). `web/index.html` es la versión
  estática para GitHub Pages (ver `docs/DEPLOY.md`, Opción C).
* No hay recuperación de contraseña automática (no hay servidor de correo): se
  resuelve por soporte. El campo `codigo_recuperacion` está previsto para hacerlo
  sin email.
* El cobro de planes es manual.
* Google Sheets no tiene transacciones: si dos personas escriben exactamente al
  mismo tiempo, se puede perder una escritura. Para uso familiar es aceptable; para
  equipos grandes, migrar a Postgres.
* Streamlit ejecuta el script completo en cada interacción: con muchas filas conviene
  paginar (hoy se filtra por mes).

## Licencia y marca

Código propio del proyecto. El nombre «Cuentas Claras» y los textos comerciales son
del autor; revisá los términos legales antes de publicar el servicio
(`docs/TERMINOS.md`).
