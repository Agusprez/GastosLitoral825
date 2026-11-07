"""Importación de los datos de la versión 1 (planilla vieja) al modelo actual.

La lógica vive acá —y no en el script de `tools/`— para poder usarla desde la app
(panel de plataforma) y desde la línea de comandos, y para testearla sin red.

Columnas que entiende (la v1 usaba las tres primeras de gastos):

* gastos: `Fecha`, `Quien`, `Concepto`, `Monto`, `Categoria`, `Comprobante`
* compras: `Elemento`, `Quién Anotó`, `Comprado`, `Fecha Anotado`

Los encabezados se normalizan (mayúsculas, acentos y variantes), así que también
funciona con un CSV exportado a mano.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .dinero import parsear_fecha
from .repositorio import CATEGORIAS, ErrorNegocio, Repositorio

ALIAS = {
    "fecha": ("fecha", "date", "dia", "día"),
    "quien": ("quien", "quién", "pagado_por", "quien pago", "quién pagó", "who", "usuario"),
    "concepto": ("concepto", "detalle", "descripcion", "descripción", "elemento", "concept"),
    "monto": ("monto", "importe", "valor", "total", "amount"),
    "categoria": ("categoria", "categoría", "category", "rubro"),
    "comprobante": ("comprobante", "ticket", "foto", "imagen", "receipt"),
}

# Nombres de las pestañas de la v1.
PESTANA_GASTOS = "Gastos"
PESTANA_COMPRAS = "Lista_Compras"

# Columnas que identifican cada pestaña, para encontrarlas aunque el nombre cambie.
COLUMNAS_GASTOS = ("fecha", "quien", "concepto", "monto")
COLUMNAS_COMPRAS = ("elemento",)


@dataclass
class Informe:
    importados: int = 0
    omitidos: int = 0
    compras: int = 0
    errores: list[str] = field(default_factory=list)
    total: Any = 0
    desde: Any = None
    hasta: Any = None
    personas: dict[str, int] = field(default_factory=dict)
    sin_persona: dict[str, int] = field(default_factory=dict)

    def resumen(self) -> str:
        lineas = [
            f"Gastos importados : {self.importados}",
            f"Gastos omitidos   : {self.omitidos}",
            f"Compras anotadas  : {self.compras}",
        ]
        if self.errores:
            lineas.append(f"\nAvisos ({len(self.errores)}):")
            lineas.extend(f"  - {e}" for e in self.errores[:20])
            if len(self.errores) > 20:
                lineas.append(f"  … y {len(self.errores) - 20} más")
        return "\n".join(lineas)


def normalizar_fila(fila: Mapping[str, Any]) -> dict[str, str]:
    """Mapea encabezados desconocidos a los campos del modelo."""
    claves = {str(k).strip().lower(): (v if v is not None else "") for k, v in fila.items()}
    salida: dict[str, str] = {}
    for campo, alias in ALIAS.items():
        for nombre in alias:
            if nombre in claves and str(claves[nombre]).strip() != "":
                salida[campo] = str(claves[nombre]).strip()
                break
    return salida


def normalizar_filas(filas: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [normalizar_fila(fila) for fila in filas]


def analizar(filas: Iterable[Mapping[str, Any]]) -> Informe:
    """Resumen de lo que hay en las filas, sin escribir nada."""
    informe = Informe()
    fechas = []
    total = 0
    for fila in normalizar_filas(filas):
        try:
            fecha = parsear_fecha(fila.get("fecha", ""))
        except ValueError:
            informe.omitidos += 1
            continue
        if not (fila.get("concepto") or "").strip():
            informe.omitidos += 1
            continue
        fechas.append(fecha)
        total += _a_decimal(fila.get("monto"))
        nombre = (fila.get("quien") or "").strip() or "(sin nombre)"
        informe.personas[nombre] = informe.personas.get(nombre, 0) + 1
    informe.total = total
    informe.desde = min(fechas) if fechas else None
    informe.hasta = max(fechas) if fechas else None
    return informe


def _a_decimal(valor: Any):
    from .dinero import redondear

    return redondear(valor or 0)


def importar(
    repo: Repositorio,
    hogar_id: str,
    filas: Iterable[Mapping[str, Any]],
    mapa_usuarios: Mapping[str, str],
    aplicar: bool = True,
    compras: Iterable[Mapping[str, Any]] = (),
    por_defecto: str = "",
) -> Informe:
    """Importa gastos y compras.

    `mapa_usuarios` relaciona el nombre que figura en la planilla con el id de la
    persona en el hogar. `por_defecto` es a quién se le asignan las filas cuyo
    nombre no está en el mapa (si está vacío, esas filas se omiten y se informan).
    """
    informe = Informe()
    miembros = [m["usuario_id"] for m in repo.miembros(hogar_id)]
    if not miembros:
        informe.errores.append("El hogar no tiene integrantes.")
        return informe

    def resolver(nombre: str) -> str:
        buscado = _clave(nombre)
        for clave, usuario_id in mapa_usuarios.items():
            if _clave(clave) == buscado:
                return usuario_id
        return por_defecto

    # El alta masiva la ejecuta quien administra el hogar (el propietario).
    equipo = repo.miembros(hogar_id)
    actor = next(
        (m["usuario_id"] for m in equipo if (m.get("rol") or "") == "propietario"),
        miembros[0],
    )

    preparadas: list[dict[str, Any]] = []
    fechas: list[Any] = []
    for numero, fila in enumerate(normalizar_filas(filas), start=2):
        concepto = (fila.get("concepto") or "").strip()
        try:
            fecha = parsear_fecha(fila.get("fecha", ""))
        except ValueError:
            informe.omitidos += 1
            informe.errores.append(f"fila {numero}: fecha inválida {fila.get('fecha')!r}")
            continue
        if not concepto:
            informe.omitidos += 1
            informe.errores.append(f"fila {numero}: sin detalle")
            continue
        nombre = (fila.get("quien") or "").strip() or "(sin nombre)"
        quien = resolver(nombre)
        if not quien:
            informe.omitidos += 1
            informe.sin_persona[nombre] = informe.sin_persona.get(nombre, 0) + 1
            informe.errores.append(
                f"fila {numero}: «{nombre}» no está asignado a nadie del hogar"
            )
            continue
        preparadas.append(
            {
                "concepto": concepto,
                "fecha": fecha,
                "monto": fila.get("monto"),
                "categoria": fila.get("categoria") or "Otros",
                "pagado_por": quien,
                "participantes": miembros,
                "comprobante": fila.get("comprobante", ""),
            }
        )
        informe.personas[nombre] = informe.personas.get(nombre, 0) + 1
        fechas.append(fecha)

    if not aplicar:
        informe.importados = len(preparadas)

    if aplicar and preparadas:
        importados, errores = repo.importar_gastos(hogar_id, actor, preparadas)
        informe.importados = importados
        informe.errores.extend(errores)
        informe.omitidos += len(preparadas) - importados

    if aplicar:
        textos = [
            (compra.get("concepto") or "").strip()
            for compra in normalizar_filas(compras)
            if (compra.get("concepto") or "").strip()
        ]
        if textos:
            informe.compras = repo.importar_compras(hogar_id, actor, textos)

    informe.total = sum((_a_decimal(f.get("monto")) for f in preparadas), 0)
    informe.desde = min(fechas) if fechas else None
    informe.hasta = max(fechas) if fechas else None
    return informe


def _clave(texto: str) -> str:
    import unicodedata

    normalizado = unicodedata.normalize("NFKD", str(texto or ""))
    limpio = "".join(c for c in normalizado if not unicodedata.combining(c))
    return " ".join(limpio.lower().split())


def leer_archivo(nombre: str, datos: bytes) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Lee un CSV o Excel exportado de la planilla vieja.

    Devuelve `(filas_de_gastos, filas_de_compras)` ya normalizadas. Para Excel usa
    pandas/openpyxl si están disponibles; si no, pide exportar a CSV.
    """
    nombre = (nombre or "").lower()
    if nombre.endswith((".xlsx", ".xls", ".xlsm")):
        return _leer_excel(datos)
    return _leer_csv(datos)


def _leer_csv(datos: bytes) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    import csv
    import io

    texto = None
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = datos.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("No pude leer el archivo: probá exportarlo como CSV UTF-8.")

    # Excel en español exporta con `;` y a veces con tabulaciones.
    muestra = texto[:2000]
    separador = max((",", ";", "\t"), key=lambda c: muestra.count(c))
    lector = csv.DictReader(io.StringIO(texto), delimiter=separador)
    filas = [dict(fila) for fila in lector]
    if not filas:
        raise ValueError("El archivo no tiene filas de datos.")

    gastos = _separar(filas, COLUMNAS_GASTOS)
    compras = _separar(filas, COLUMNAS_COMPRAS)
    if not gastos and compras:
        return [], compras
    if not gastos:
        raise ValueError(
            "El archivo no tiene las columnas de gastos (Fecha, Quien, Concepto, Monto)."
        )
    return gastos, compras


def _leer_excel(datos: bytes) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    try:
        import io

        import pandas as pd
    except ImportError as exc:  # pragma: no cover - depende del despliegue
        raise ValueError(
            "Para leer Excel falta `pandas` y `openpyxl`. Exportá la planilla como "
            "CSV y subila así."
        ) from exc

    try:
        hojas = pd.read_excel(io.BytesIO(datos), sheet_name=None, dtype=str)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"No pude leer el Excel: {exc}") from exc

    gastos: list[dict[str, str]] = []
    compras: list[dict[str, str]] = []
    for nombre_hoja, tabla in hojas.items():
        filas = [
            {str(k): ("" if v is None else str(v)) for k, v in fila.items()}
            for fila in tabla.to_dict(orient="records")
        ]
        if not filas:
            continue
        encontrados = _separar(filas, COLUMNAS_GASTOS)
        if encontrados and not gastos:
            gastos = encontrados
            continue
        encontrados = _separar(filas, COLUMNAS_COMPRAS)
        if encontrados and not compras:
            compras = encontrados
    if not gastos:
        raise ValueError(
            "No encontré una hoja con las columnas de gastos "
            "(Fecha, Quien, Concepto, Monto)."
        )
    return gastos, compras


def _separar(filas: list[dict[str, Any]], columnas: tuple[str, ...]) -> list[dict[str, str]]:
    """Devuelve las filas normalizadas si tienen todas esas columnas."""
    if not filas:
        return []
    encabezados = [_clave(k) for k in filas[0]]
    if not all(_clave(c) in encabezados for c in columnas):
        return []
    return normalizar_filas(filas)


def proponer_mapeo(
    nombres: Iterable[str], miembros: Iterable[Mapping[str, Any]]
) -> dict[str, str]:
    """Sugiere qué persona del hogar corresponde a cada nombre de la planilla.

    Compara por nombre completo, primer nombre y el email. Devuelve sólo las
    coincidencias; lo que queda afuera lo resuelve la persona en la pantalla.
    """
    personas = [dict(m) for m in miembros]
    propuesta: dict[str, str] = {}
    for nombre in nombres:
        buscado = _clave(nombre)
        if not buscado:
            continue
        primero = buscado.split(" ")[0]
        elegido = ""
        for persona in personas:
            candidato = _clave(persona.get("nombre", ""))
            correo = _clave(str(persona.get("email", "")).split("@")[0])
            if candidato == buscado or correo == buscado:
                elegido = str(persona["usuario_id"])
                break
        if not elegido and len(primero) >= 3:
            for persona in personas:
                if _clave(persona.get("nombre", "")).split(" ")[0] == primero:
                    elegido = str(persona["usuario_id"])
                    break
        if elegido:
            propuesta[nombre] = elegido
    return propuesta
