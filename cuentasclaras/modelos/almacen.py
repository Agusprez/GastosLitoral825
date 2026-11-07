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

    def leer_pestana(self, titulo: str) -> list[dict[str, str]]:
        """Filas de una pestaña ajena al esquema (migraciones). Sin pestañas acá."""
        return []


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


def _abrir_libro(url: str, credenciales: Mapping[str, Any]):
    """Abre la planilla con la cuenta de servicio.

    Aislado en una función para poder testear `SheetsStore` con un libro falso,
    sin credenciales ni red.
    """
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
        return gspread.authorize(creds).open_by_url(url)
    except Exception as exc:  # credenciales inválidas, planilla sin permiso, etc.
        raise ErrorAlmacen(f"No se pudo abrir la planilla: {exc}") from exc


class SheetsStore(Store):
    """Google Sheets como base de datos.

    Una pestaña por tabla, con prefijo (`cc_usuarios`, `cc_gastos`, …) para no
    chocar con las pestañas de la versión 1 (`Gastos`, `Lista_Compras`).

    Se lee con `get_all_values()` (no con `get_all_records()`) para evitar
    coerciones numéricas de gspread y conservar los textos tal cual se
    escribieron. Las lecturas se cachean unos segundos porque cada rerun de
    Streamlit vuelve a pedir todo.

    Compatibilidad: si encuentra una pestaña sin prefijo con **nuestro** esquema
    (por ejemplo, las que creó una versión anterior con el prefijo sin aplicar),
    la renombra en vez de duplicarla. Si la pestaña tiene otro formato, nunca la
    toca: falla con un mensaje claro.
    """

    TTL = 5.0

    def __init__(
        self,
        url: str,
        credenciales: Mapping[str, Any],
        prefijo: str = "cc_",
        libro: Any | None = None,
    ) -> None:
        self.prefijo = (prefijo or "").strip()
        self._libro = libro if libro is not None else _abrir_libro(url, credenciales)
        self._cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
        self._hojas: list[Any] | None = None
        self._lock = threading.RLock()

    # --- infraestructura --------------------------------------------------------

    def _titulo(self, tabla: str) -> str:
        return f"{self.prefijo}{tabla}"

    def _listar_hojas(self) -> list[Any]:
        with self._lock:
            if self._hojas is None:
                try:
                    self._hojas = list(self._libro.worksheets())
                except Exception as exc:  # noqa: BLE001 - red, permisos, cuota
                    raise ErrorAlmacen(
                        f"No se pudieron listar las pestañas de la planilla: {exc}"
                    ) from exc
            return self._hojas

    def _olvidar_hojas(self) -> None:
        with self._lock:
            self._hojas = None

    def _buscar(self, titulo: str):
        """Busca una pestaña por nombre, sin distinguir mayúsculas/minúsculas."""
        buscado = titulo.strip().lower()
        for hoja in self._listar_hojas():
            if str(getattr(hoja, "title", "")).strip().lower() == buscado:
                return hoja
        return None

    def _error_formato(self, tabla: str, titulo: str) -> ErrorAlmacen:
        return ErrorAlmacen(
            f"La planilla ya tiene una pestaña «{titulo}» con otro formato. "
            f"Para no pisarla, la app necesita usar «{self._titulo(tabla)}» con su "
            f"propio encabezado. Renombrá la pestaña existente (por ejemplo "
            f"«{titulo}_viejo») o cambiá `prefijo_hojas` en los secretos."
        )

    def _crear(self, tabla: str):
        titulo = self._titulo(tabla)
        existente = self._buscar(titulo)
        if existente is not None and not self._esquema_propio(tabla, existente):
            raise self._error_formato(tabla, getattr(existente, "title", titulo))
        try:
            hoja = self._libro.add_worksheet(
                title=titulo, rows=100, cols=len(TABLAS[tabla]) + 2
            )
        except Exception as exc:  # noqa: BLE001
            raise ErrorAlmacen(
                f"No se pudo crear la pestaña «{titulo}»: {exc}"
            ) from exc
        self._olvidar_hojas()
        return hoja

    def _adoptar(self, tabla: str):
        """Renombra una pestaña vieja sin prefijo si tiene nuestro esquema."""
        titulo = self._titulo(tabla)
        candidata = self._buscar(tabla)
        if candidata is not None and self._esquema_propio(tabla, candidata):
            try:
                candidata.update_title(titulo)
            except Exception:  # noqa: BLE001 - si no se puede, la creamos aparte
                return self._crear(tabla)
            self._olvidar_hojas()
            encontrada = self._buscar(titulo)
            if encontrada is not None:
                return encontrada
            return candidata
        return self._crear(tabla)

    def _esquema_propio(self, tabla: str, hoja) -> bool:
        """¿La pestaña tiene el encabezado de esta tabla (o un prefijo de él)?"""
        columnas = TABLAS[tabla]
        try:
            actuales = [str(c).strip().lower() for c in hoja.row_values(1)]
        except Exception:  # noqa: BLE001
            return False
        actuales = [c for c in actuales if c]
        if not actuales:
            return True  # pestaña vacía: es nuestra para inicializar
        if actuales[0] != columnas[0]:
            return False
        return actuales == columnas[: len(actuales)]

    def _hoja(self, tabla: str):
        titulo = self._titulo(tabla)
        hoja = self._buscar(titulo)
        if hoja is None:
            hoja = self._adoptar(tabla)
            self._olvidar_hojas()
        self._asegurar_encabezados(tabla, hoja)
        return hoja

    def _asegurar_encabezados(self, tabla: str, hoja) -> None:
        """Completa el encabezado si faltan columnas nuevas; nunca pisa otro formato."""
        columnas = TABLAS[tabla]
        try:
            crudo = hoja.row_values(1)
        except Exception:  # noqa: BLE001
            crudo = []
        actuales = [str(c).strip() for c in crudo]
        actuales = [c for c in actuales if c]
        if actuales == columnas:
            return
        if not actuales:
            hoja.update(range_name="A1", values=[columnas])
            return
        if actuales[0].lower() == columnas[0] and actuales == columnas[: len(actuales)]:
            hoja.update(range_name="A1", values=[columnas])
            return
        raise self._error_formato(tabla, self._titulo(tabla))

    def _invalidar(self, tabla: str | None = None) -> None:
        with self._lock:
            if tabla is None:
                self._cache.clear()
            else:
                self._cache.pop(tabla, None)

    # --- lectura de pestañas ajenas al esquema (migraciones) ---------------- #
    def leer_pestana(self, titulo: str) -> list[dict[str, str]]:
        """Devuelve las filas de una pestaña cualquiera, sin tocar su contenido.

        Se usa para importar datos de la versión 1 (`Gastos`, `Lista_Compras`).
        Devuelve `[]` si la pestaña no existe.
        """
        hoja = self._buscar(titulo)
        if hoja is None:
            return []
        try:
            valores = hoja.get_all_values()
        except Exception as exc:  # noqa: BLE001
            raise ErrorAlmacen(
                f"No se pudo leer la pestaña «{titulo}»: {exc}"
            ) from exc
        if len(valores) < 2:
            return []
        encabezados = [str(c).strip() for c in valores[0]]
        filas: list[dict[str, str]] = []
        for cruda in valores[1:]:
            if not any(str(c).strip() for c in cruda):
                continue
            fila = {
                encabezados[i]: (cruda[i] if i < len(cruda) else "")
                for i in range(len(encabezados))
                if encabezados[i]
            }
            if any(str(v).strip() for v in fila.values()):
                filas.append(fila)
        return filas

    def pestanas(self) -> list[str]:
        """Nombres de todas las pestañas de la planilla."""
        return [str(getattr(hoja, "title", "")) for hoja in self._listar_hojas()]

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
        return f"google sheets · {self._libro.title} · pestañas {self.prefijo}*"


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
        return SheetsStore(
            config.hoja_url,
            config.gcp_credenciales,
            prefijo=getattr(config, "prefijo_hojas", "cc_"),
        )
    return SqliteStore(config.sqlite_ruta)


def importar_tablas(store: Store, tablas: Iterable[str] | None = None) -> int:
    """Escribe las hojas que falten (útil al provisionar una planilla nueva)."""
    total = 0
    for tabla in tablas or TABLAS:
        total += len(store.all(tabla))
    return total
