"""Autenticación: hashing de contraseñas, sesiones y bloqueo por intentos.

Sin dependencias externas:
* `hashlib.scrypt` para las contraseñas (con sal aleatoria por usuario).
* Token de sesión opaco (32 bytes) guardado HASHEADO en la base: si alguien lee
  la planilla o el archivo SQLite, no puede reutilizar las sesiones.
* Comparaciones en tiempo constante con `hmac.compare_digest`.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .dinero import ahora, iso
from .almacen import Store, nuevo_id

# Parámetros de scrypt: ~50 ms por verificación, suficiente contra fuerza bruta.
_N = 2 ** 14
_R = 8
_P = 1
_DKLEN = 32
_SALT = 16

DIAS_SESION = 30
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
MIN_CLAVE = 8
MAX_CLAVE = 200

CLAVES_PROHIBIDAS = {
    "12345678", "123456789", "contrasena", "contraseña", "password", "qwertyui",
    "1234567890", "abcdefgh", "gastos123", "cuentasclaras", "casasanpedro",
}


# --------------------------------------------------------------------------- #
# Contraseñas
# --------------------------------------------------------------------------- #
def _b64(crudo: bytes) -> str:
    import base64

    return base64.b64encode(crudo).decode("ascii")


def _de_b64(texto: str) -> bytes:
    import base64

    return base64.b64decode(texto.encode("ascii"))


def hash_clave(clave: str) -> str:
    """Devuelve `scrypt$n$r$p$sal$hash` (todo en base64 salvo los parámetros)."""
    sal = secrets.token_bytes(_SALT)
    derivada = hashlib.scrypt(
        clave.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(derivada)}"


def verificar_clave(clave: str, guardado: str) -> bool:
    """Comparación en tiempo constante. Nunca lanza excepción."""
    if not guardado or not clave:
        return False
    partes = str(guardado).split("$")
    if len(partes) != 6 or partes[0] != "scrypt":
        return False
    try:
        n, r, p = int(partes[1]), int(partes[2]), int(partes[3])
        sal, esperado = _de_b64(partes[4]), _de_b64(partes[5])
    except (ValueError, TypeError):
        return False
    try:
        calculada = hashlib.scrypt(
            clave.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=len(esperado)
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(calculada, esperado)


def _sin_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def revisar_clave(clave: str, email: str = "", nombre: str = "") -> list[str]:
    """Devuelve la lista de problemas (vacía = contraseña aceptable)."""
    problemas: list[str] = []
    clave = clave or ""
    if len(clave) < MIN_CLAVE:
        problemas.append(f"Usá al menos {MIN_CLAVE} caracteres.")
    if len(clave) > MAX_CLAVE:
        problemas.append(f"Máximo {MAX_CLAVE} caracteres.")
    if clave and not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", clave):
        problemas.append("Sumá al menos una letra.")
    if _sin_acentos(clave) in CLAVES_PROHIBIDAS:
        problemas.append("Esa contraseña es demasiado común.")
    local = _sin_acentos((email or "").split("@")[0])
    if local and len(local) >= 4 and local in _sin_acentos(clave):
        problemas.append("No uses tu email como contraseña.")
    nombre_norm = _sin_acentos(nombre).strip()
    if nombre_norm and len(nombre_norm) >= 4 and nombre_norm in _sin_acentos(clave):
        problemas.append("No uses tu nombre como contraseña.")
    return problemas


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def email_valido(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", normalizar_email(email)))


# --------------------------------------------------------------------------- #
# Sesiones
# --------------------------------------------------------------------------- #
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def crear_sesion(store: Store, usuario_id: str, dias: int = DIAS_SESION) -> str:
    """Crea la sesión y devuelve el token en claro (va a la cookie)."""
    token = secrets.token_urlsafe(32)
    store.insert(
        "sesiones",
        {
            "id": _hash_token(token),
            "usuario_id": usuario_id,
            "creado_en": iso(),
            "expira_en": iso(ahora() + timedelta(days=dias)),
            "revocada": "No",
            "hogar_activo": "",
            "huella": "",
        },
    )
    return token


def _vigente(fila: dict[str, Any]) -> bool:
    from .dinero import desde_iso

    if (fila.get("revocada") or "No").lower() in {"si", "sí", "true", "1"}:
        return False
    return desde_iso(fila.get("expira_en", "")) > ahora()


def sesion_por_token(store: Store, token: str) -> dict[str, str] | None:
    if not token:
        return None
    fila = store.uno("sesiones", _hash_token(token))
    if fila is None or not _vigente(fila):
        return None
    return fila


def revocar(store: Store, token: str) -> None:
    if not token:
        return
    fila = store.uno("sesiones", _hash_token(token))
    if fila:
        store.update("sesiones", fila["id"], {"revocada": "Si"})


def revocar_todas(store: Store, usuario_id: str, excepto: str = "") -> int:
    excepto_id = _hash_token(excepto) if excepto else ""
    total = 0
    for fila in store.filtrar("sesiones", usuario_id=usuario_id):
        if fila["id"] != excepto_id and (fila.get("revocada") or "No") != "Si":
            store.update("sesiones", fila["id"], {"revocada": "Si"})
            total += 1
    return total


def recordar_hogar(store: Store, token: str, hogar_id: str) -> None:
    fila = sesion_por_token(store, token)
    if fila:
        store.update("sesiones", fila["id"], {"hogar_activo": hogar_id})


def limpiar_sesiones(store: Store, dias_gracia: int = 7) -> int:
    """Borra sesiones vencidas hace más de `dias_gracia`."""
    from .dinero import desde_iso

    limbo = ahora() - timedelta(days=dias_gracia)
    borradas = 0
    for fila in store.all("sesiones"):
        if desde_iso(fila.get("expira_en", "")) < limbo:
            store.delete("sesiones", fila["id"])
            borradas += 1
    return borradas


# --------------------------------------------------------------------------- #
# Intentos fallidos
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoLogin:
    ok: bool
    usuario: dict[str, str] | None = None
    mensaje: str = ""
    bloqueado_hasta: str = ""


def _bloqueado(usuario: dict[str, str]) -> bool:
    from .dinero import desde_iso

    hasta = usuario.get("bloqueado_hasta") or ""
    return bool(hasta) and desde_iso(hasta) > ahora()


def autenticar(store: Store, email: str, clave: str) -> ResultadoLogin:
    """Valida credenciales y administra el bloqueo progresivo.

    El mensaje de error es siempre el mismo para no revelar si el email existe.
    """
    generico = "Email o contraseña incorrectos."
    email = normalizar_email(email)

    candidatos = store.filtrar("usuarios", email=email)
    if not candidatos:
        # Gastamos tiempo similar al de una verificación real (anti-enumeración).
        verificar_clave(clave or "", "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAA")
        return ResultadoLogin(False, mensaje=generico)

    usuario = candidatos[0]
    if usuario.get("activo", "Si") in {"No", "no", "0"}:
        return ResultadoLogin(False, mensaje="La cuenta está deshabilitada. Escribinos a soporte.")
    if _bloqueado(usuario):
        return ResultadoLogin(
            False,
            mensaje="Demasiados intentos fallidos. Probá de nuevo en unos minutos.",
            bloqueado_hasta=usuario.get("bloqueado_hasta", ""),
        )

    if verificar_clave(clave or "", usuario.get("hash_clave", "")):
        store.update(
            "usuarios",
            usuario["id"],
            {
                "intentos_fallidos": "0",
                "bloqueado_hasta": "",
                "ultimo_login": iso(),
            },
        )
        usuario = store.uno("usuarios", usuario["id"]) or usuario
        return ResultadoLogin(True, usuario=usuario)

    intentos = int(usuario.get("intentos_fallidos") or 0) + 1
    campos: dict[str, Any] = {"intentos_fallidos": str(intentos)}
    if intentos >= MAX_INTENTOS:
        campos["bloqueado_hasta"] = iso(ahora() + timedelta(minutes=MINUTOS_BLOQUEO))
        campos["intentos_fallidos"] = "0"
    store.update("usuarios", usuario["id"], campos)
    restantes = MAX_INTENTOS - intentos
    if 0 < restantes <= 2:
        return ResultadoLogin(
            False, mensaje=f"{generico} Te quedan {restantes} intento(s)."
        )
    return ResultadoLogin(False, mensaje=generico)
