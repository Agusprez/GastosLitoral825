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

import io
import mimetypes
import os
import re
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


class ErrorArchivo(Exception):
    """Archivo inválido o demasiado grande."""


def _extension(nombre: str) -> str:
    return Path(nombre or "").suffix.lower()


def validar(datos: bytes, nombre: str, max_mb: int = 5) -> str:
    """Devuelve la extensión normalizada o lanza `ErrorArchivo`."""
    if not datos:
        raise ErrorArchivo("El archivo está vacío.")
    limite = max(1, int(max_mb)) * 1024 * 1024
    if len(datos) > limite:
        raise ErrorArchivo(f"El archivo supera los {max_mb} MB.")
    ext = _extension(nombre)
    if ext not in EXTENSIONES:
        raise ErrorArchivo("Formato no admitido. Usá JPG, PNG o WEBP.")
    if not any(datos.startswith(firma) for firma, _ in FIRMAS):
        raise ErrorArchivo("El archivo no parece una imagen válida.")
    return ".jpg" if ext == ".jpeg" else ext


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
    def __init__(self, carpeta: str | Path) -> None:
        self.carpeta = Path(carpeta)
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
        ext = validar(datos, nombre)
        contenido, _ = optimizar(datos, ext)
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
    def __init__(self, credenciales: Mapping[str, Any], carpeta_id: str) -> None:
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

    def guardar(self, hogar_id: str, datos: bytes, nombre: str) -> str:
        from googleapiclient.http import MediaIoBaseUpload

        ext = validar(datos, nombre)
        contenido, mime = optimizar(datos, ext)
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


def construir(config: Config) -> Medios:
    if config.medios == "drive" and config.gcp_credenciales and config.drive_carpeta_id:
        return MediosDrive(config.gcp_credenciales, config.drive_carpeta_id)
    return MediosLocal(config.medios_dir)


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
