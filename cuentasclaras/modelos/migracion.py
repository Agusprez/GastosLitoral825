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
    participantes = miembros

    def resolver(nombre: str) -> str:
        buscado = _clave(nombre)
        for clave, usuario_id in mapa_usuarios.items():
            if clave.startswith("__"):
                continue
            if _clave(clave) == buscado:
                return usuario_id
        return por_defecto

    fechas = []
    total = 0
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
        categoria = fila.get("categoria") or "Otros"
        if categoria not in CATEGORIAS:
            categoria = "Otros"
        monto = _a_decimal(fila.get("monto"))
        if not aplicar:
            informe.importados += 1
            fechas.append(fecha)
            total += monto
            informe.personas[nombre] = informe.personas.get(nombre, 0) + 1
            continue
        try:
            repo.agregar_gasto(
                hogar_id,
                quien,
                concepto,
                monto,
                categoria,
                quien,
                participantes,
                fecha=fecha,
                comprobante=fila.get("comprobante", ""),
            )
            informe.importados += 1
            fechas.append(fecha)
            total += monto
            informe.personas[nombre] = informe.personas.get(nombre, 0) + 1
        except ErrorNegocio as exc:
            informe.omitidos += 1
            informe.errores.append(f"fila {numero}: {exc}")

    if aplicar:
        for compra in normalizar_filas(compras):
            texto = (compra.get("concepto") or "").strip()
            if not texto or not miembros:
                continue
            try:
                repo.agregar_compra(hogar_id, miembros[0], texto)
                informe.compras += 1
            except ErrorNegocio as exc:
                informe.errores.append(f"compra: {exc}")

    informe.total = total
    informe.desde = min(fechas) if fechas else None
    informe.hasta = max(fechas) if fechas else None
    return informe


def _clave(texto: str) -> str:
    import unicodedata

    normalizado = unicodedata.normalize("NFKD", str(texto or ""))
    limpio = "".join(c for c in normalizado if not unicodedata.combining(c))
    return " ".join(limpio.lower().split())


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
