"""Comprobantes y fotos de tickets.

Antes las imágenes se subían a imgbb: quedaban en un link público adivinable y
sin relación con el hogar. Acá se guardan privadas, con dos backends:

* `local`  — `data/comprobantes/<hogar>/<uuid>.jpg` en el servidor.
* `drive`  — Google Drive con la cuenta de servicio (el archivo no se comparte
             con nadie: sólo la app lo puede leer).

La referencia guardada en el gasto es `local:...`, `drive:<file_id>` o una URL
`http...` de la versión anterior (sólo se muestra, no se puede leer).
"""

from __future__ import annotations

import base64
import io
import mimetypes
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from .configuracion import Config

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
}
LADO_MAXIMO = 1600
CALIDAD_JPEG = 82
# Firmas de archivo: evita que suban un .exe renombrado a .jpg.
FIRMAS = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"RIFF", ".webp"),
)

# Caché de imágenes bajadas de un servicio externo (imgbb).
_CACHE_DESCARGAS: dict[str, bytes] = {}
_CACHE_LOCK = threading.Lock()


class ErrorArchivo(Exception):
    """Archivo inválido o demasiado grande."""


def _extension(nombre: str) -> str:
    return Path(nombre or "").suffix.lower()


# Una foto de celular puede pesar 3-8 MB antes de comprimir: se acepta más en la
# entrada y el límite de `max_comprobante_mb` se aplica al archivo ya optimizado.
FACTOR_ENTRADA = 4
MAX_ENTRADA_MB = 40


def validar(datos: bytes, nombre: str, max_mb: int = 5) -> str:
    """Devuelve la extensión normalizada o lanza `ErrorArchivo`.

    `max_mb` es el límite del archivo *guardado*; la entrada tolera más porque se
    recomprime antes (una foto de celular ronda los 5 MB y no queremos rechazarla).
    """
    if not datos:
        raise ErrorArchivo("El archivo está vacío.")
    limite_entrada = min(MAX_ENTRADA_MB, max(1, int(max_mb)) * FACTOR_ENTRADA) * 1024 * 1024
    if len(datos) > limite_entrada:
        raise ErrorArchivo(
            f"La imagen es muy grande ({len(datos) / 1024 / 1024:.1f} MB). "
            f"Probá con una foto más chica o subila desde el archivo."
        )
    ext = _extension(nombre)
    if ext not in EXTENSIONES:
        raise ErrorArchivo("Formato no admitido. Usá JPG, PNG o WEBP.")
    if not any(datos.startswith(firma) for firma, _ in FIRMAS):
        raise ErrorArchivo("El archivo no parece una imagen válida.")
    return ".jpg" if ext == ".jpeg" else ext


def comprimir(datos: bytes, nombre: str, max_mb: int = 5) -> tuple[bytes, str]:
    """Valida, optimiza y controla el tamaño final. Devuelve (bytes, mime)."""
    ext = validar(datos, nombre, max_mb)
    contenido, mime = optimizar(datos, ext)
    limite = max(1, int(max_mb)) * 1024 * 1024
    if len(contenido) > limite:
        raise ErrorArchivo(
            f"La imagen sigue superando los {max_mb} MB después de comprimirla."
        )
    return contenido, mime


def optimizar(datos: bytes, ext: str) -> tuple[bytes, str]:
    """Achica la imagen si Pillow está disponible (viene con matplotlib)."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow siempre está en la nube
        return datos, MIMES.get(ext, "image/jpeg")
    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen = imagen.convert("RGB")
        imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
        salida = io.BytesIO()
        imagen.save(salida, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
        return salida.getvalue(), "image/jpeg"
    except Exception:  # archivo raro: lo guardamos tal cual
        return datos, MIMES.get(ext, "image/jpeg")


def tipo(ref: str) -> str:
    """`local`, `drive`, `http` o `desconocido`."""
    ref = (ref or "").strip()
    if ref.startswith("local:"):
        return "local"
    if ref.startswith("drive:"):
        return "drive"
    if ref.startswith(("http://", "https://")):
        return "http"
    return "desconocido"


class Medios:
    """Interfaz común."""

    def guardar(self, hogar_id: str, datos: bytes, nombre: str) -> str: ...
    def leer(self, ref: str) -> bytes | None: ...
    def borrar(self, ref: str) -> None: ...

    def descripcion(self) -> str:
        return type(self).__name__


class MediosLocal(Medios):
    def __init__(self, carpeta: str | Path, max_mb: int = 5) -> None:
        self.carpeta = Path(carpeta)
        self.max_mb = max_mb
        self.carpeta.mkdir(parents=True, exist_ok=True)

    def _ruta(self, ref: str) -> Path:
        resto = ref.split("local:", 1)[1]
        limpio = re.sub(r"[^A-Za-z0-9_./-]", "", resto).lstrip("./")
        destino = (self.carpeta / limpio).resolve()
        base = self.carpeta.resolve()
        if not str(destino).startswith(str(base)):
            raise ErrorArchivo("Referencia de archivo inválida.")
        return destino

    def guardar(self, hogar_id: str, datos: bytes, nombre: str) -> str:
        contenido, _mime = comprimir(datos, nombre, self.max_mb)
        carpeta_hogar = self.carpeta / re.sub(r"[^A-Za-z0-9_-]", "", hogar_id)
        carpeta_hogar.mkdir(parents=True, exist_ok=True)
        archivo = f"{uuid.uuid4().hex}.jpg"
        (carpeta_hogar / archivo).write_bytes(contenido)
        return f"local:{carpeta_hogar.name}/{archivo}"

    def leer(self, ref: str) -> bytes | None:
        if tipo(ref) != "local":
            return None
        try:
            return self._ruta(ref).read_bytes()
        except (OSError, ErrorArchivo):
            return None

    def borrar(self, ref: str) -> None:
        if tipo(ref) != "local":
            return
        try:
            self._ruta(ref).unlink(missing_ok=True)
        except (OSError, ErrorArchivo):
            pass

    def descripcion(self) -> str:
        return f"disco ({self.carpeta})"


class MediosDrive(Medios):
    def __init__(
        self,
        credenciales: Mapping[str, Any],
        carpeta_id: str,
        max_mb: int = 5,
    ) -> None:
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover
            raise ErrorArchivo(
                "Faltan dependencias de Google para guardar comprobantes en Drive."
            ) from exc
        scopes = ["https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(dict(credenciales), scopes=scopes)
        self._servicio = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.carpeta_id = carpeta_id
        self.max_mb = max_mb

    def guardar(self, hogar_id: str, datos: bytes, nombre: str) -> str:
        from googleapiclient.http import MediaIoBaseUpload

        contenido, mime = comprimir(datos, nombre, self.max_mb)
        metadatos = {
            "name": f"{hogar_id[:8]}-{uuid.uuid4().hex[:10]}.jpg",
            "parents": [self.carpeta_id] if self.carpeta_id else [],
        }
        archivo = (
            self._servicio.files()
            .create(
                body=metadatos,
                media_body=MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mime, resumable=False),
                fields="id",
            )
            .execute()
        )
        return f"drive:{archivo['id']}"

    def leer(self, ref: str) -> bytes | None:
        if tipo(ref) != "drive":
            return None
        try:
            identificador = ref.split("drive:", 1)[1]
            return self._servicio.files().get_media(fileId=identificador).execute()
        except Exception:  # pragma: no cover - red/permisos
            return None

    def borrar(self, ref: str) -> None:
        if tipo(ref) != "drive":
            return
        try:
            self._servicio.files().delete(fileId=ref.split("drive:", 1)[1]).execute()
        except Exception:  # pragma: no cover
            pass

    def descripcion(self) -> str:
        return "google drive"


def _descargar(url: str, cliente: Any, timeout: int) -> bytes | None:
    """Descarga una imagen remota, con caché en memoria.

    El diálogo del gasto se redibuja en cada interacción: sin caché, abrir un
    ticket dispararía una descarga por rerun.
    """
    with _CACHE_LOCK:
        if url in _CACHE_DESCARGAS:
            return _CACHE_DESCARGAS[url]
    try:
        respuesta = cliente.get(url, timeout=timeout)
    except Exception:  # noqa: BLE001 - red caída, DNS, timeout
        return None
    if getattr(respuesta, "status_code", 0) != 200:
        return None
    contenido = getattr(respuesta, "content", None)
    if not isinstance(contenido, bytes) or not contenido:
        return None
    with _CACHE_LOCK:
        if len(_CACHE_DESCARGAS) > 64:
            _CACHE_DESCARGAS.clear()
        _CACHE_DESCARGAS[url] = contenido
    return contenido


class MediosImgbb(Medios):
    """Sube los comprobantes a imgbb (el servicio que usaba la versión 1).

    Se conserva `imgbb_api_key` de los secretos, así que migrar no requiere
    configurar nada nuevo. La referencia guardada es la URL directa de la imagen
    (`https://i.ibb.co/...`), igual que en la v1: eso hace que los comprobantes
    históricos se sigan viendo sin conversión.

    Ojo: en imgbb la imagen queda accesible para quien tenga el link (no es
    privada como Drive o el disco). La app la muestra sólo a las personas del
    hogar, pero el link no está protegido por contraseña.
    """

    URL_SUBIDA = "https://api.imgbb.com/1/upload"

    def __init__(
        self,
        clave: str,
        cliente: Any | None = None,
        timeout: int = 25,
        max_mb: int = 5,
    ) -> None:
        clave = (clave or "").strip()
        if not clave:
            raise ErrorArchivo(
                "Falta `imgbb_api_key` en los secretos: sin esa clave no se pueden "
                "subir comprobantes a imgbb."
            )
        self.clave = clave
        self._cliente = cliente
        self.timeout = timeout
        self.max_mb = max_mb

    # --- infraestructura ---------------------------------------------------- #
    def _http(self):
        if self._cliente is None:
            try:
                import requests
            except ImportError as exc:  # pragma: no cover - depende del despliegue
                raise ErrorArchivo(
                    "Falta el paquete `requests` para subir imágenes a imgbb."
                ) from exc
            self._cliente = requests
        return self._cliente

    # --- interfaz ----------------------------------------------------------- #
    def guardar(self, hogar_id: str, datos: bytes, nombre: str) -> str:
        contenido, _mime = comprimir(datos, nombre, self.max_mb)
        carga = {
            "key": self.clave,
            "image": base64.b64encode(contenido).decode("ascii"),
        }
        try:
            respuesta = self._http().post(self.URL_SUBIDA, data=carga, timeout=self.timeout)
        except ErrorArchivo:
            raise
        except Exception as exc:  # noqa: BLE001 - red caída, timeout, SSL
            raise ErrorArchivo(f"No se pudo subir la imagen a imgbb: {exc}") from exc

        estado = getattr(respuesta, "status_code", 0)
        if estado != 200:
            detalle = ""
            try:
                detalle = str(respuesta.json().get("error", {}).get("message", ""))[:160]
            except Exception:  # noqa: BLE001
                detalle = str(getattr(respuesta, "text", ""))[:160]
            raise ErrorArchivo(f"imgbb respondió {estado}. {detalle}".strip())

        try:
            cuerpo = respuesta.json()
            info = cuerpo["data"]
            url = info.get("url") or info.get("display_url") or info.get("image", {}).get("url")
        except Exception as exc:  # noqa: BLE001
            raise ErrorArchivo("imgbb devolvió una respuesta que no se entiende.") from exc
        if not url:
            raise ErrorArchivo("imgbb no devolvió la URL de la imagen.")
        return str(url)

    def leer(self, ref: str) -> bytes | None:
        if tipo(ref) != "http":
            return None
        return _descargar(ref, self._http(), self.timeout)

    def borrar(self, ref: str) -> None:
        """imgbb no permite borrar sin el token de borrado: se deja la imagen."""
        return None

    def descripcion(self) -> str:
        return "imgbb"


def construir(config: Config) -> Medios:
    tope = getattr(config, "max_comprobante_mb", 10)
    if config.medios == "imgbb":
        return MediosImgbb(config.imgbb_api_key, max_mb=tope)
    if config.medios == "drive" and config.gcp_credenciales and config.drive_carpeta_id:
        return MediosDrive(config.gcp_credenciales, config.drive_carpeta_id, max_mb=tope)
    return MediosLocal(config.medios_dir, max_mb=tope)


def mime_de(ref: str, datos: bytes | None = None) -> str:
    """MIME para mostrar/descargar un comprobante."""
    if datos:
        try:
            firma = datos[:12]
        except TypeError:
            firma = b""
        if firma.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if firma.startswith(b"\x89PNG"):
            return "image/png"
        if firma.startswith(b"RIFF"):
            return "image/webp"
    return mimetypes.guess_type(ref or "foto.jpg")[0] or "image/jpeg"


def nombre_descarga(concepto: str, ref: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9]+", "_", (concepto or "comprobante").strip()).strip("_")
    ext = ".png" if (ref or "").lower().endswith(".png") else ".jpg"
    return f"{limpio[:40] or 'comprobante'}{ext}"
