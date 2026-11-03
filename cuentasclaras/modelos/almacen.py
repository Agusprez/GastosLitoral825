"""Almacenamiento de bajo nivel.

Todo el sistema trabaja con "tablas" que son listas de diccionarios de texto
(`str -> str`). Hay tres implementaciones intercambiables:

* `MemoryStore`  — en RAM, para tests y demos.
* `SqliteStore`  — un archivo local (VPS, Docker, uso personal).
* `SheetsStore`  — una planilla de Google (sobrevive a reinicios en la nube).

Mantener las tres con la misma interfaz permite testear las reglas de negocio
una sola vez y cambiar de infraestructura sin tocar el resto de la app.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Mapping

# Esquema lógico. El orden de las columnas es el que se escribe en la planilla.
TABLAS: dict[str, list[str]] = {
    "usuarios": [
        "id", "email", "nombre", "hash_clave", "rol", "activo",
        "creado_en", "ultimo_login", "intentos_fallidos", "bloqueado_hasta",
        "codigo_recuperacion", "hogar_activo",
    ],
    "hogares": [
        "id", "nombre", "moneda", "plan", "division", "activo",
        "creado_en", "creado_por", "plan_hasta",
    ],
    "miembros": [
        "id", "hogar_id", "usuario_id", "rol", "estado", "unido_en",
    ],
    "gastos": [
        "id", "hogar_id", "fecha", "concepto", "monto", "categoria",
        "pagado_por", "division", "comprobante", "creado_por", "creado_en", "estado",
    ],
    "compras": [
        "id", "hogar_id", "texto", "estado", "anotado_por", "fecha",
        "comprado_por", "comprado_en",
    ],
    "pagos": [
        "id", "hogar_id", "de_usuario", "a_usuario", "monto", "fecha",
        "nota", "creado_por", "creado_en",
    ],
    "invitaciones": [
        "id", "hogar_id", "codigo", "rol", "creado_por", "creado_en",
        "expira_en", "usos", "usos_max", "activa",
    ],
    "sesiones": [
        "id", "usuario_id", "creado_en", "expira_en", "revocada",
        "hogar_activo", "huella",
    ],
    "eventos": [
        "id", "hogar_id", "usuario_id", "accion", "detalle", "creado_en",
    ],
}

# Columnas que nunca deben salir de la capa de datos hacia la interfaz.
SECRETAS = {"hash_clave", "codigo_recuperacion"}


class ErrorAlmacen(RuntimeError):
    """Falla de infraestructura (credenciales, cuota, disco)."""


def nuevo_id() -> str:
    return uuid.uuid4().hex


def normalizar(tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
    """Devuelve una fila con exactamente las columnas del esquema."""
    columnas = TABLAS[tabla]
    return {c: ("" if fila.get(c) is None else str(fila.get(c))) for c in columnas}


class Store(ABC):
    """Interfaz mínima que necesita la capa de negocio."""

    @abstractmethod
    def all(self, tabla: str) -> list[dict[str, str]]: ...

    @abstractmethod
    def insert(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]: ...

    @abstractmethod
    def update(self, tabla: str, id_fila: str, campos: Mapping[str, Any]) -> None: ...

    @abstractmethod
    def delete(self, tabla: str, id_fila: str) -> None: ...

    # --- utilidades compartidas -------------------------------------------------

    def filtrar(self, tabla: str, **campos: Any) -> list[dict[str, str]]:
        objetivos = {k: str(v) for k, v in campos.items()}
        return [
            fila
            for fila in self.all(tabla)
            if all(fila.get(k) == v for k, v in objetivos.items())
        ]

    def uno(self, tabla: str, id_fila: str) -> dict[str, str] | None:
        for fila in self.all(tabla):
            if fila.get("id") == id_fila:
                return fila
        return None

    def borrar_donde(self, tabla: str, **campos: Any) -> int:
        filas = self.filtrar(tabla, **campos)
        for fila in filas:
            self.delete(tabla, fila["id"])
        return len(filas)

    def ping(self) -> str:
        return "ok"


class MemoryStore(Store):
    """Store en memoria: rápido, descartable. Base de los tests."""

    def __init__(self) -> None:
        self._datos: dict[str, list[dict[str, str]]] = {t: [] for t in TABLAS}

    def all(self, tabla: str) -> list[dict[str, str]]:
        return [dict(f) for f in self._datos[tabla]]

    def insert(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
        datos = normalizar(tabla, fila)
        if not datos["id"]:
            datos["id"] = nuevo_id()
        self._datos[tabla].append(datos)
        return dict(datos)

    def update(self, tabla: str, id_fila: str, campos: Mapping[str, Any]) -> None:
        for fila in self._datos[tabla]:
            if fila["id"] == id_fila:
                for clave, valor in campos.items():
                    if clave in fila:
                        fila[clave] = "" if valor is None else str(valor)
                return
        raise ErrorAlmacen(f"No existe {tabla}/{id_fila}")

    def delete(self, tabla: str, id_fila: str) -> None:
        antes = len(self._datos[tabla])
        self._datos[tabla] = [f for f in self._datos[tabla] if f["id"] != id_fila]
        if len(self._datos[tabla]) == antes:
            raise ErrorAlmacen(f"No existe {tabla}/{id_fila}")

    def limpiar(self) -> None:
        for tabla in self._datos:
            self._datos[tabla] = []


class SqliteStore(Store):
    """Un archivo SQLite por instalación.

    Cada tabla es `(id TEXT PRIMARY KEY, datos TEXT)` con la fila en JSON. Se
    prioriza la portabilidad y la simplicidad de migraciones por sobre consultas
    SQL: el volumen esperado es de miles de filas, no de millones.
    """

    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)
        if self.ruta.parent and str(self.ruta.parent) not in ("", "."):
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.ruta), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        for tabla in TABLAS:
            self._conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{tabla}" (id TEXT PRIMARY KEY, datos TEXT NOT NULL)'
            )
        self._conn.commit()

    def _leer(self, tabla: str) -> list[dict[str, str]]:
        with self._lock:
            cur = self._conn.execute(f'SELECT datos FROM "{tabla}"')
            filas = []
            for (crudo,) in cur.fetchall():
                try:
                    filas.append(normalizar(tabla, json.loads(crudo)))
                except (ValueError, TypeError):
                    continue
            return filas

    def all(self, tabla: str) -> list[dict[str, str]]:
        return self._leer(tabla)

    def insert(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
        datos = normalizar(tabla, fila)
        if not datos["id"]:
            datos["id"] = nuevo_id()
        with self._lock:
            self._conn.execute(
                f'INSERT INTO "{tabla}" (id, datos) VALUES (?, ?)',
                (datos["id"], json.dumps(datos, ensure_ascii=False)),
            )
            self._conn.commit()
        return dict(datos)

    def update(self, tabla: str, id_fila: str, campos: Mapping[str, Any]) -> None:
        with self._lock:
            cur = self._conn.execute(f'SELECT datos FROM "{tabla}" WHERE id = ?', (id_fila,))
            resultado = cur.fetchone()
            if not resultado:
                raise ErrorAlmacen(f"No existe {tabla}/{id_fila}")
            datos = normalizar(tabla, json.loads(resultado[0]))
            for clave, valor in campos.items():
                if clave in datos:
                    datos[clave] = "" if valor is None else str(valor)
            self._conn.execute(
                f'UPDATE "{tabla}" SET datos = ? WHERE id = ?',
                (json.dumps(datos, ensure_ascii=False), id_fila),
            )
            self._conn.commit()

    def delete(self, tabla: str, id_fila: str) -> None:
        with self._lock:
            cur = self._conn.execute(f'DELETE FROM "{tabla}" WHERE id = ?', (id_fila,))
            self._conn.commit()
            if cur.rowcount == 0:
                raise ErrorAlmacen(f"No existe {tabla}/{id_fila}")

    def ping(self) -> str:
        return f"sqlite {sqlite3.sqlite_version} · {self.ruta}"

    def cerrar(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:  # pragma: no cover - cierre defensivo
                pass


class SheetsStore(Store):
    """Google Sheets como base de datos.

    Una pestaña por tabla. Se lee con `get_all_values()` (no `get_all_records()`)
    para evitar coerciones numéricas de gspread y conservar los textos tal cual
    se escribieron. Las lecturas se cachean unos segundos porque cada rerun de
    Streamlit vuelve a pedir todo.
    """

    TTL = 5.0

    def __init__(self, url: str, credenciales: Mapping[str, Any]) -> None:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:  # pragma: no cover - depende del despliegue
            raise ErrorAlmacen(
                "Faltan dependencias de Google (gspread / google-auth). "
                "Instalá requirements.txt o usá almacen=sqlite."
            ) from exc

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        try:
            creds = Credentials.from_service_account_info(dict(credenciales), scopes=scopes)
            cliente = gspread.authorize(creds)
            self._libro = cliente.open_by_url(url)
        except Exception as exc:  # credenciales inválidas, planilla sin permiso, etc.
            raise ErrorAlmacen(f"No se pudo abrir la planilla: {exc}") from exc

        self._cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._lock = threading.RLock()

    # --- infraestructura --------------------------------------------------------

    def _hoja(self, tabla: str):
        import gspread

        titulo = tabla
        try:
            hoja = self._libro.worksheet(titulo)
        except gspread.WorksheetNotFound:
            hoja = self._libro.add_worksheet(
                title=titulo, rows=100, cols=len(TABLAS[tabla]) + 2
            )
        self._asegurar_encabezados(tabla, hoja)
        return hoja

    def _asegurar_encabezados(self, tabla: str, hoja) -> None:
        columnas = TABLAS[tabla]
        try:
            actuales = hoja.row_values(1)
        except Exception:
            actuales = []
        actuales = [c.strip() for c in actuales]
        if actuales[: len(columnas)] != columnas:
            hoja.update(range_name="A1", values=[columnas])

    def _invalidar(self, tabla: str | None = None) -> None:
        with self._lock:
            if tabla is None:
                self._cache.clear()
            else:
                self._cache.pop(tabla, None)

    def _valores(self, tabla: str) -> list[dict[str, str]]:
        hoja = self._hoja(tabla)
        valores = hoja.get_all_values()
        if not valores:
            return []
        encabezados = [c.strip() for c in valores[0]]
        indice = {nombre: i for i, nombre in enumerate(encabezados) if nombre}
        filas: list[dict[str, str]] = []
        for cruda in valores[1:]:
            if not any(str(c).strip() for c in cruda):
                continue
            fila = {
                col: (cruda[indice[col]] if col in indice and indice[col] < len(cruda) else "")
                for col in TABLAS[tabla]
            }
            if fila.get("id"):
                filas.append(normalizar(tabla, fila))
        return filas

    def _numero_fila(self, tabla: str, id_fila: str) -> int:
        """Fila real en la planilla (1 = encabezado)."""
        hoja = self._hoja(tabla)
        ids = hoja.col_values(1)
        try:
            return ids.index(id_fila) + 1
        except ValueError as exc:
            raise ErrorAlmacen(f"No existe {tabla}/{id_fila}") from exc

    # --- interfaz ---------------------------------------------------------------

    def all(self, tabla: str) -> list[dict[str, str]]:
        with self._lock:
            cacheado = self._cache.get(tabla)
            if cacheado and (time.monotonic() - cacheado[0]) < self.TTL:
                return [dict(f) for f in cacheado[1]]
        filas = self._valores(tabla)
        with self._lock:
            self._cache[tabla] = (time.monotonic(), filas)
        return [dict(f) for f in filas]

    def insert(self, tabla: str, fila: Mapping[str, Any]) -> dict[str, str]:
        datos = normalizar(tabla, fila)
        if not datos["id"]:
            datos["id"] = nuevo_id()
        hoja = self._hoja(tabla)
        hoja.append_row([datos[c] for c in TABLAS[tabla]], value_input_option="RAW")
        self._invalidar(tabla)
        return dict(datos)

    def update(self, tabla: str, id_fila: str, campos: Mapping[str, Any]) -> None:
        fila = self.uno(tabla, id_fila)
        if fila is None:
            raise ErrorAlmacen(f"No existe {tabla}/{id_fila}")
        fila.update({k: "" if v is None else str(v) for k, v in campos.items() if k in fila})
        numero = self._numero_fila(tabla, id_fila)
        self._hoja(tabla).update(
            range_name=f"A{numero}", values=[[fila[c] for c in TABLAS[tabla]]]
        )
        self._invalidar(tabla)

    def delete(self, tabla: str, id_fila: str) -> None:
        numero = self._numero_fila(tabla, id_fila)
        self._hoja(tabla).delete_rows(numero)
        self._invalidar(tabla)

    def ping(self) -> str:
        return f"google sheets · {self._libro.title}"


def abrir(config, memoria: Store | None = None) -> Store:
    """Fábrica según configuración (usada por la app y por los scripts)."""
    if memoria is not None:
        return memoria
    if config.almacen == "memoria":
        return MemoryStore()
    if config.almacen == "sheets":
        if not (config.hoja_url and config.gcp_credenciales):
            raise ErrorAlmacen(
                "Almacenamiento 'sheets' requiere hoja_url y gcp_service_account."
            )
        return SheetsStore(config.hoja_url, config.gcp_credenciales)
    return SqliteStore(config.sqlite_ruta)


def importar_tablas(store: Store, tablas: Iterable[str] | None = None) -> int:
    """Escribe las hojas que falten (útil al provisionar una planilla nueva)."""
    total = 0
    for tabla in tablas or TABLAS:
        total += len(store.all(tabla))
    return total
