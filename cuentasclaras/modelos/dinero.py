"""Fechas, zonas horarias y dinero (formato es-AR).

Argentina no aplica horario de verano desde 2009, así que un offset fijo
UTC-3 es exacto y evita depender del paquete `tzdata` (que no existe en
instalaciones peladas de Windows).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZONA_AR = timezone(timedelta(hours=-3), "America/Argentina/Buenos_Aires")

MESES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
CENT = Decimal("0.01")


# --------------------------------------------------------------------------- #
# Tiempo
# --------------------------------------------------------------------------- #
def ahora() -> datetime:
    return datetime.now(ZONA_AR).replace(microsecond=0)


def hoy() -> date:
    return ahora().date()


def iso(dt: datetime | date | None = None) -> str:
    valor = dt or ahora()
    if isinstance(valor, datetime):
        return valor.isoformat(timespec="seconds")
    return valor.isoformat()


def desde_iso(texto: str, defecto: datetime | None = None) -> datetime:
    """Acepta ISO con o sin offset; devuelve datetime con zona AR."""
    texto = (texto or "").strip()
    if not texto:
        return defecto or ahora()
    try:
        valor = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.combine(parsear_fecha(texto), datetime.min.time(), ZONA_AR)
        except ValueError:
            return defecto or ahora()
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=ZONA_AR)
    return valor.astimezone(ZONA_AR).replace(microsecond=0)


def parsear_fecha(texto: str | date | None) -> date:
    """Acepta `dd/mm/aaaa`, `aaaa-mm-dd`, `dd-mm-aaaa` y `dd/mm/aa`."""
    if isinstance(texto, date):
        return texto
    crudo = str(texto or "").strip()
    if not crudo:
        raise ValueError("fecha vacía")
    crudo = crudo.split("T")[0].split(" ")[0]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(crudo, formato).date()
        except ValueError:
            continue
    raise ValueError(f"fecha inválida: {texto!r}")


def fecha_iso(valor: str | date | None) -> str:
    if valor is None or str(valor).strip() == "":
        return ""
    try:
        return parsear_fecha(valor).isoformat()
    except ValueError:
        return ""


def formatear_fecha(valor: str | date | None) -> str:
    try:
        return parsear_fecha(valor).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor or "")


def periodo(mes: str) -> tuple[date, date]:
    """`"2026-11"` -> (2026-11-01, 2026-11-30)."""
    anio, num = (int(p) for p in mes.split("-")[:2])
    inicio = date(anio, num, 1)
    fin = date(anio + (num == 12), (num % 12) + 1, 1) - timedelta(days=1)
    return inicio, fin


def clave_mes(valor: date | str | None = None) -> str:
    if isinstance(valor, date):
        return f"{valor.year:04d}-{valor.month:02d}"
    return (valor or hoy().strftime("%Y-%m")).strip()[:7]


def nombre_mes(clave: str, incluir_anio: bool = True) -> str:
    try:
        anio, num = (int(p) for p in clave.split("-")[:2])
        base = MESES[num - 1]
        return f"{base} {anio}" if incluir_anio else base
    except (ValueError, IndexError):
        return clave


def meses_hacia_atras(cantidad: int, base: date | None = None) -> list[str]:
    """Lista de claves de mes, de la más nueva a la más vieja."""
    base = base or hoy()
    anio, mes = base.year, base.month
    salida = []
    for _ in range(max(cantidad, 1)):
        salida.append(f"{anio:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            anio -= 1
    return salida


# --------------------------------------------------------------------------- #
# Dinero
# --------------------------------------------------------------------------- #
def decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    crudo = str(valor or "").strip()
    if not crudo:
        return Decimal("0")
    crudo = re.sub(r"[^\d,.\-]", "", crudo)
    if "," in crudo and "." in crudo:
        # Formato es-AR: 12.345,67
        crudo = crudo.replace(".", "").replace(",", ".")
    elif "," in crudo:
        crudo = crudo.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", crudo):
        # "12.500" en Argentina son doce mil quinientos, no doce coma cinco.
        crudo = crudo.replace(".", "")
    try:
        return Decimal(crudo)
    except InvalidOperation:
        return Decimal("0")


def redondear(valor) -> Decimal:
    return decimal(valor).quantize(CENT, rounding=ROUND_HALF_UP)


def monto_texto(valor) -> str:
    """Formato estable para guardar: `12345.60` (sin separador de miles)."""
    return str(redondear(valor))


def negativo(valor) -> bool:
    return redondear(valor) < 0


def formatear(valor, simbolo: str = "$") -> str:
    """`12345.6` -> `"$12.345,60"`."""
    numero = redondear(valor)
    signo = "-" if numero < 0 else ""
    entero, _, decimales = f"{abs(numero):.2f}".partition(".")
    miles = ""
    while len(entero) > 3:
        miles = "." + entero[-3:] + miles
        entero = entero[:-3]
    cuerpo = f"{entero}{miles},{decimales}"
    return f"{signo}{simbolo}{cuerpo}" if simbolo else f"{signo}{cuerpo}"


def formatear_corto(valor, simbolo: str = "$") -> str:
    """Sin decimales cuando el monto es redondo: `$12.000` / `$12.345,60`."""
    numero = redondear(valor)
    if numero == numero.to_integral_value():
        return formatear(numero).replace(",00", "")
    return formatear(numero)
