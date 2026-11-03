# Arquitectura

## Capas (MVC)

```
vistas/           (V)  Streamlit: widgets, mensajes, navegación. Sin reglas.
controladores/    (C)  Casos de uso: validan, orquestan, devuelven Resultado.
modelos/          (M)  Datos, reglas de negocio, cifrado y persistencia.
```

**Regla de oro:** la vista nunca importa `almacen` ni escribe datos. Siempre pasa
por un controlador, que devuelve `Resultado(ok, mensaje, tipo, datos)`.

Consecuencias prácticas:

* Las reglas se testean sin Streamlit (120 tests de modelo/controladores).
* Cambiar de interfaz (por ejemplo, a una API HTTP o a React) no toca las reglas.
* Cambiar de base de datos sólo requiere otra implementación de `Store`.

### Por qué `Resultado` y no excepciones en la vista

En Streamlit una excepción no capturada muestra un traceback al usuario final y
corta la página. El controlador traduce `ErrorNegocio`/`NoAutorizado`/`ErrorAlmacen`
a mensajes en español, y cualquier error inesperado se muestra como "Ocurrió un
error inesperado" con el detalle en un `caption`. Nunca se rompe la pantalla.

## Persistencia

La interfaz `Store` tiene cuatro operaciones: `all`, `insert`, `update`, `delete`.
Las filas son diccionarios `str -> str` (todas las columnas del esquema, vacías si
faltan). Implementaciones:

| Clase | Uso | Notas |
| --- | --- | --- |
| `SheetsStore` | Producción | Una pestaña por tabla, lee con `get_all_values()` para evitar coerciones de gspread, cachea 5 s en memoria. |
| `SqliteStore` | Local / VPS | Una tabla por entidad con `(id TEXT, datos TEXT)`. WAL habilitado. |
| `MemoryStore` | Tests y demo | Sin persistencia. |

`SheetsStore` usa **pestañas con prefijo** (`cc_usuarios`, `cc_gastos`, …) para no
pisar las pestañas de la versión 1 (`Gastos`, `Lista_Compras`). El prefijo se
configura con `prefijo_hojas`.

### Por qué no SQLAlchemy ni un ORM

El proyecto corre en Streamlit Community Cloud, donde el disco es efímero: si la
base es un archivo, se pierde en cada reinicio. Google Sheets resuelve persistencia
sin infraestructura y ya era la base de la v1. Para miles de hogares el camino es
un `PostgresStore` (misma interfaz), no reescribir el modelo.

## Cifrado

Formato de un valor cifrado:

```
enc1:<base64(nonce[12] || ciphertext || tag[16])>
```

* **ChaCha20** (RFC 8439) en Python puro, sin dependencias. Tests con el vector
  oficial de la RFC.
* **HMAC-SHA256** sobre `tabla.columna || nonce || ciphertext` (encrypt-then-MAC).
  El AAD por columna impide mover un valor cifrado de una columna o tabla a otra.
* Claves derivadas con **HKDF-SHA256** de una clave maestra (32 bytes en base64).
* Nonce aleatorio por valor: el mismo email dos veces se ve distinto.
* Se cifran **todas** las columnas menos `id` (UUID sin datos personales y usado
  para ubicar la fila en la planilla).

Comportamiento con datos viejos: si un valor no empieza con `enc1:`, se devuelve
tal cual. Así se puede activar el cifrado sobre una planilla existente y re-cifrar
a mano con `tools/cifrar_existente.py`.

**Riesgos asumidos y mitigaciones**

| Riesgo | Estado |
| --- | --- |
| Se pierde la clave | Los datos no se pueden leer. La app falla con un mensaje claro; hay que restaurar la clave desde el backup. |
| Alguien con edición en la planilla borra filas | El cifrado autenticado detecta cambios de valor, no borrados. Mitigación: planilla privada + versionado de Drive. |
| Metadatos visibles | Cantidad de filas, fechas de alta de filas y el `id`. No hay montos ni nombres legibles. |
| Fuga por memoria del servidor | Fuera de alcance: quien controle el proceso ve los datos descifrados. |

## Autenticación

* `hashlib.scrypt(n=2^14, r=8, p=1, dklen=32)` con sal de 16 bytes por usuario.
* Formato guardado: `scrypt$n$r$p$sal$hash` (permite subir parámetros después).
* Sesión: token de 32 bytes (`secrets.token_urlsafe`), se guarda `sha256(token)` en
  `sesiones` con vencimiento (30 días, o 1 si no se marca "recordarme").
* Cambiar contraseña o deshabilitar la cuenta revoca todas las sesiones.
* Cookie `cc_sesion` con el token; Streamlit la maneja con
  `streamlit-cookies-controller`. Si el navegador las bloquea, la sesión sigue
  funcionando en la pestaña abierta.
* Bloqueo: 5 intentos fallidos → 15 minutos. El mensaje no distingue email
  inexistente de contraseña incorrecta, y en el caso inexistente se gasta el mismo
  tiempo (anti-enumeración).

## Contabilidad

* Cada gasto tiene un pagador y una división (`{usuario_id: monto}`) calculada al
  momento con reparto exacto al centavo (el resto va al de mayor peso/primero).
* Saldo de una persona = `pagado + enviado − parte − recibido`.
  Positivo: le deben. Negativo: debe.
* `pagos` registra transferencias reales, así el saldo puede quedar en cero.
* El "a quién le paga quién" se calcula con un algoritmo voraz que genera como
  mucho `n−1` transferencias.

## Planes y límites

`planes.LIMITES` define topes por plan; `Repositorio` los consulta en cada alta
(`crear_hogar`, `invitar`, `agregar_gasto`) y devuelve `LimiteAlcanzado`. La UI sólo
muestra el mensaje. El plan es por hogar; el plan "efectivo" de una cuenta es el
mejor entre sus hogares (para permitir más de un hogar si alguno es Pro).

## Comprobantes

* `local`: `data/comprobantes/<hogar>/<uuid>.jpg`, servido sólo por la app.
* `drive`: sube a una carpeta privada de la service account; se lee con
  `files().get_media`.
* Validación: extensión + firma del archivo (JPEG/PNG/WEBP) + 5 MB. Se re-comprimen
  a 1600 px con Pillow si está disponible.
* Compatibilidad: los links `http…` de la v1 se muestran tal cual (no se descargan).

## Escalabilidad

| Dimensión | Hoy | Cuándo migrar |
| --- | --- | --- |
| Hogares | Decenas | Miles → Postgres |
| Filas por tabla | Miles | Decenas de miles → Postgres + índices |
| Escrituras concurrentes | Bajas | Sheets no transacciona; para equipos grandes, Postgres |
| Comprobantes | GB | Drive o S3 (la interfaz `Medios` ya lo abstrae) |

Consultas: cada rerun de Streamlit lee sólo las tablas que usa, con caché de 5 s en
`SheetsStore`. Un rerun típico del tablero hace ~4 lecturas y 0 escrituras.

## Decisiones registradas

1. **Streamlit** en lugar de una SPA: el equipo es chico, el producto es de uso
   ocasional (cargar un gasto y mirar), y así no hay frontend que mantener.
2. **Google Sheets** en lugar de una base gestionada: cero costo operativo y
   persistencia en el plan gratuito de Streamlit Cloud.
3. **Cifrado propio** en lugar de depender de `cryptography`: el entorno de
   despliegue no siempre tiene compiladores y la primitiva es verificable contra la
   RFC. Si más adelante se prefiere AES-GCM, se cambia sólo `cifrado.py`.
4. **Diccionarios** en lugar de dataclasses: menos capas de conversión entre
   almacén, controlador y vista, y los datos son texto plano por definición.
