"""Cifrado de los datos guardados en la planilla (o en SQLite).

Motivo: si la base es una planilla de Google, cualquiera con el link puede leer
todo. Con esto, lo que se escribe es texto cifrado y sin la clave no se puede
leer nada: ni nombres, ni emails, ni conceptos de gastos.

Diseño
------
* **ChaCha20** (RFC 8439) implementado en Python puro → cero dependencias.
* **HMAC-SHA256** sobre (tabla + nonce + ciphertext) → cifrado autenticado:
  si alguien edita una celda, la app lo detecta en vez de mostrar basura.
* Claves derivadas con **HKDF-SHA256** a partir de una clave maestra.
* Cada valor se cifra con un nonce aleatorio: el mismo email dos veces se ve
  distinto en la planilla.
* Formato guardado: `enc1:<base64(nonce || cifrado || etiqueta)>`. Los valores
  históricos sin el prefijo se leen tal cual (migración transparente).

Lo que NO se cifra: el `id` de cada fila (es un UUID sin datos personales y se
usa para ubicar la fila en la planilla).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

from .almacen import Store, TABLAS, normalizar

PREFIJO = "enc1:"
NONCE = 12
ETIQUETA = 16
CONSTANTES = b"expand 32-byte k"
MASCARA = 0xFFFFFFFF
SAL_HKDF = b"cuentasclaras/v1"
COLUMNA_EXENTA = "id"


class ErrorCifrado(Exception):
    """Clave incorrecta o dato manipulado."""


# --------------------------------------------------------------------------- #
# ChaCha20
# --------------------------------------------------------------------------- #
def _rotar(valor: int, bits: int) -> int:
    return ((valor << bits) | (valor >> (32 - bits))) & MASCARA


def _cuarto(x: list[int], a: int, b: int, c: int, d: int) -> None:
    x[a] = (x[a] + x[b]) & MASCARA
    x[d] = _rotar(x[d] ^ x[a], 16)
    x[c] = (x[c] + x[d]) & MASCARA
    x[b] = _rotar(x[b] ^ x[c], 12)
    x[a] = (x[a] + x[b]) & MASCARA
    x[d] = _rotar(x[d] ^ x[a], 8)
    x[c] = (x[c] + x[d]) & MASCARA
    x[b] = _rotar(x[b] ^ x[c], 7)


def bloque_chacha20(clave: bytes, nonce: bytes, contador: int = 1) -> bytes:
    """Un bloque de 64 bytes de keystream (vector de RFC 8439 §2.3.2)."""
    if len(clave) != 32:
        raise ValueError("La clave ChaCha20 debe tener 32 bytes.")
    if len(nonce) != 12:
        raise ValueError("El nonce ChaCha20 debe tener 12 bytes.")
    estado = (
        list(struct.unpack("<4I", CONSTANTES))
        + list(struct.unpack("<8I", clave))
        + [contador & MASCARA]
        + list(struct.unpack("<3I", nonce))
    )
    x = estado[:]
    for _ in range(10):
        _cuarto(x, 0, 4, 8, 12)
        _cuarto(x, 1, 5, 9, 13)
        _cuarto(x, 2, 6, 10, 14)
        _cuarto(x, 3, 7, 11, 15)
        _cuarto(x, 0, 5, 10, 15)
        _cuarto(x, 1, 6, 11, 12)
        _cuarto(x, 2, 7, 8, 13)
        _cuarto(x, 3, 4, 9, 14)
    return struct.pack("<16I", *[(x[i] + estado[i]) & MASCARA for i in range(16)])


def _aplicar(clave: bytes, nonce: bytes, datos: bytes, contador: int = 1) -> bytes:
    salida = bytearray()
    for posicion in range(0, len(datos), 64):
        trozo = datos[posicion : posicion + 64]
        keystream = bloque_chacha20(clave, nonce, contador + posicion // 64)
        salida.extend(a ^ b for a, b in zip(trozo, keystream))
    return bytes(salida)


def _hkdf(material: bytes, info: bytes, largo: int = 32) -> bytes:
    """HKDF-SHA256 (RFC 5869) con sal fija de la aplicación."""
    prk = hmac.new(SAL_HKDF, material, hashlib.sha256).digest()
    salida, bloque, contador = b"", b"", 1
    while len(salida) < largo:
        bloque = hmac.new(prk, bloque + info + bytes([contador]), hashlib.sha256).digest()
        salida += bloque
        contador += 1
        if contador > 255:  # pragma: no cover
            break
    return salida[:largo]


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii")


def _de_b64(texto: str) -> bytes:
    relleno = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + relleno)


def generar_clave() -> str:
    """32 bytes aleatorios en base64 (formato que espera la configuración)."""
    return _b64(os.urandom(32))


def es_cifrado(valor: Any) -> bool:
    return isinstance(valor, str) and valor.startswith(PREFIJO)


# --------------------------------------------------------------------------- #
# Cifrador
# --------------------------------------------------------------------------- #
class Cifrador:
    """Cifra y descifra valores de texto con una clave maestra."""

    def __init__(self, material: str) -> None:
        material = (material or "").strip()
        if not material:
            raise ErrorCifrado("La clave de cifrado está vacía.")
        secreto = material.encode("utf-8")
        self._clave_cifrado = _hkdf(secreto, b"cifrado")
        self._clave_mac = _hkdf(secreto, b"autenticacion")
        self._lock = threading.Lock()

    def cifrar(self, texto: Any, contexto: str = "") -> str:
        plano = "" if texto is None else str(texto)
        if not plano:
            return ""
        nonce = secrets.token_bytes(NONCE)
        cifrado = _aplicar(self._clave_cifrado, nonce, plano.encode("utf-8"))
        etiqueta = hmac.new(
            self._clave_mac,
            contexto.encode("utf-8") + nonce + cifrado,
            hashlib.sha256,
        ).digest()[:ETIQUETA]
        return PREFIJO + _b64(nonce + cifrado + etiqueta)

    def descifrar(self, valor: Any, contexto: str = "") -> str:
        if not es_cifrado(valor):
            return "" if valor is None else str(valor)
        crudo = _de_b64(str(valor)[len(PREFIJO) :])
        if len(crudo) < NONCE + ETIQUETA:
            raise ErrorCifrado("El dato cifrado está incompleto.")
        nonce = crudo[:NONCE]
        cifrado = crudo[NONCE:-ETIQUETA]
        etiqueta = crudo[-ETIQUETA:]
        esperada = hmac.new(
            self._clave_mac,
            contexto.encode("utf-8") + nonce + cifrado,
            hashlib.sha256,
        ).digest()[:ETIQUETA]
        if not hmac.compare_digest(etiqueta, esperada):
            raise ErrorCifrado(
                "No se pudo descifrar un dato: la clave no coincide o la fila fue editada a mano."
            )
        try:
            return _aplicar(self._clave_cifrado, nonce, cifrado).decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover
            raise ErrorCifrado("El dato descifrado no es texto válido.") from exc


# --------------------------------------------------------------------------- #
# Clave
# --------------------------------------------------------------------------- #
def resolver_clave(config) -> tuple[str, str]:
    """Devuelve (clave, origen). Origen `""` = hay que avisar que no hay cifrado."""
    if not getattr(config, "cifrado", True):
        return "", "desactivado"
    directa = (getattr(config, "clave_cifrado", "") or "").strip()
    if directa:
        return directa, "configuración"
    if getattr(config, "almacen", "") == "sheets":
        # Si los datos viven en la nube, la clave TIENE que venir de los
        # secretos: un archivo local se perdería al reiniciar el contenedor y
        # dejaría la planilla ilegible para siempre.
        return "", ""
    archivo = Path(getattr(config, "clave_archivo", "data/clave.key"))
    try:
        if archivo.exists():
            material = archivo.read_text(encoding="utf-8").strip()
            if material:
                return material, f"archivo {archivo}"
    except OSError:
        pass
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        material = generar_clave()
        archivo.write_text(material + "\n", encoding="utf-8")
        try:
            os.chmod(archivo, 0o600)
        except OSError:
            pass
        return material, f"generada en {archivo}"
    except OSError:
        return "", ""


# --------------------------------------------------------------------------- #
# Store con cifrado transparente
# --------------------------------------------------------------------------- #
class AlmacenCifrado(Store):
    """Envuelve cualquier `Store` cifrando todos los campos salvo `id`."""

    def __init__(self, interno: Store, cifrador: Cifrador) -> None:
        self._interno = interno
        self._cifrador = cifrador

    # --- conversión ------------------------------------------------------- #
    def _cifrar_fila(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
        datos = normalizar(tabla, fila)
        return {
            columna: (
                valor
                if columna == COLUMNA_EXENTA or not valor
                else self._cifrador.cifrar(valor, f"{tabla}.{columna}")
            )
            for columna, valor in datos.items()
        }

    def _cifrar_campos(self, tabla: str, campos: Mapping[str, Any]) -> dict[str, str]:
        """Cifra sólo las columnas indicadas (para updates parciales).

        Importante: no normalizamos acá, porque escribir "" en el resto de las
        columnas borraría los datos de la fila (y el `id`).
        """
        columnas = set(TABLAS[tabla])
        salida: dict[str, str] = {}
        for clave, valor in campos.items():
            if clave not in columnas:
                continue
            texto = "" if valor is None else str(valor)
            if clave == COLUMNA_EXENTA or not texto:
                salida[clave] = texto
            else:
                salida[clave] = self._cifrador.cifrar(texto, f"{tabla}.{clave}")
        return salida

    def _descifrar_fila(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
        datos = normalizar(tabla, fila)
        salida: dict[str, str] = {}
        for columna, valor in datos.items():
            if columna == COLUMNA_EXENTA or not es_cifrado(valor):
                salida[columna] = valor
            else:
                salida[columna] = self._cifrador.descifrar(valor, f"{tabla}.{columna}")
        return salida

    # --- interfaz --------------------------------------------------------- #
    def all(self, tabla: str) -> list[dict[str, str]]:
        return [self._descifrar_fila(tabla, fila) for fila in self._interno.all(tabla)]

    def insert(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
        guardada = self._interno.insert(tabla, self._cifrar_fila(tabla, fila))
        return self._descifrar_fila(tabla, guardada)

    def update(self, tabla: str, id_fila: str, campos: Mapping[str, Any]) -> None:
        self._interno.update(tabla, id_fila, self._cifrar_campos(tabla, campos))

    def delete(self, tabla: str, id_fila: str) -> None:
        self._interno.delete(tabla, id_fila)

    def ping(self) -> str:
        return f"{self._interno.ping()} · cifrado ChaCha20"

    def leer_pestana(self, titulo: str) -> list[dict[str, str]]:
        """Pestañas ajenas al esquema (v1): se leen tal cual, en texto plano."""
        leer = getattr(self._interno, "leer_pestana", None)
        return leer(titulo) if callable(leer) else []

    def leer_pestana_externa(self, titulo: str, url: str) -> list[dict[str, str]]:
        leer = getattr(self._interno, "leer_pestana_externa", None)
        return leer(titulo, url) if callable(leer) else []

    def buscar_pestana_por_columnas(self, columnas):
        buscar = getattr(self._interno, "buscar_pestana_por_columnas", None)
        return buscar(columnas) if callable(buscar) else None

    def pestanas(self) -> list[str]:
        listar = getattr(self._interno, "pestanas", None)
        return listar() if callable(listar) else []

    def cerrar(self) -> None:
        cerrar = getattr(self._interno, "cerrar", None)
        if callable(cerrar):
            cerrar()

    @property
    def crudo(self) -> Store:
        """El store sin cifrar (sólo para scripts de mantenimiento)."""
        return self._interno


def envolver(store: Store, config) -> tuple[Store, str]:
    """Aplica cifrado si hay clave disponible. Devuelve (store, origen de clave)."""
    clave, origen = resolver_clave(config)
    if not clave:
        return store, origen
    return AlmacenCifrado(store, Cifrador(clave)), origen
