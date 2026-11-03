"""División de gastos, saldos y sugerencia de transferencias.

Reglas contables (importante para que los números cierren al centavo):

* Cada gasto tiene UN pagador y una lista de participantes.
* El monto se reparte entre los participantes en partes iguales; el resto que
  no se puede dividir se asigna de a un centavo a los primeros participantes.
* Saldo de una persona = lo que pagó + lo que transfirió - lo que le tocó - lo
  que recibió. Positivo = le deben. Negativo = debe.
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .dinero import decimal, redondear

CERO = Decimal("0")

# Estados que no cuentan para los saldos.
ESTADOS_IGNORADOS = {"anulado"}


def redondear_reparto(total: Any, pesos: Mapping[str, Any]) -> dict[str, Decimal]:
    """Reparte `total` proporcionalmente a `pesos`, garantizando suma exacta."""
    monto = redondear(total)
    claves = [k for k, v in pesos.items() if decimal(v) > 0]
    if not claves:
        return {}
    suma_pesos = sum((decimal(pesos[k]) for k in claves), CERO)
    if suma_pesos <= 0:
        return {}
    bruto = {k: monto * decimal(pesos[k]) / suma_pesos for k in claves}
    repartido = {k: redondear(v) for k, v in bruto.items()}
    diferencia = monto - sum(repartido.values(), CERO)
    if diferencia != CERO:
        # Ajustamos sobre el participante con mayor peso (o el primero).
        objetivo = max(claves, key=lambda k: (decimal(pesos[k]), -claves.index(k)))
        repartido[objetivo] = redondear(repartido[objetivo] + diferencia)
    return repartido


def repartir(total: Any, participantes: Iterable[str]) -> dict[str, Decimal]:
    """Partes iguales entre los participantes (sin duplicados, sin vacíos)."""
    limpios = list(OrderedDict.fromkeys(p for p in participantes if p))
    if not limpios:
        return {}
    return redondear_reparto(total, {p: 1 for p in limpios})


def normalizar_division(division: Any) -> dict[str, Decimal]:
    """Convierte lo guardado en la fila (`{"usuario_id": "monto"}`) a Decimal."""
    if not division:
        return {}
    if isinstance(division, dict):
        crudo = division
    else:
        import json

        try:
            crudo = json.loads(division)
        except (ValueError, TypeError):
            return {}
    if isinstance(crudo, list):  # formato alternativo: [{"usuario_id","monto"}]
        crudo = {
            str(item.get("usuario_id")): item.get("monto", item.get("peso", 0))
            for item in crudo
            if isinstance(item, dict) and item.get("usuario_id")
        }
    if not isinstance(crudo, dict):
        return {}
    salida: dict[str, Decimal] = {}
    for clave, valor in crudo.items():
        monto = redondear(valor)
        if monto > 0:
            salida[str(clave)] = monto
    return salida


def division_json(division: Mapping[str, Any]) -> str:
    import json

    limpio = {str(k): str(redondear(v)) for k, v in division.items() if redondear(v) != 0}
    return json.dumps(limpio, ensure_ascii=False, sort_keys=True)


def dividir_entre(total: Any, participantes: Iterable[str]) -> str:
    """Atajo: reparte en partes iguales y devuelve el JSON listo para guardar."""
    return division_json(repartir(total, participantes))


def saldos(
    gastos: Iterable[Mapping[str, Any]],
    pagos: Iterable[Mapping[str, Any]] = (),
    miembros: Iterable[str] = (),
) -> dict[str, dict[str, Decimal]]:
    """Saldo por persona. Incluye a todos los miembros aunque no tengan movimientos."""
    resultado: dict[str, dict[str, Decimal]] = OrderedDict()
    for usuario_id in miembros:
        resultado[str(usuario_id)] = {
            "pagado": CERO,
            "parte": CERO,
            "enviado": CERO,
            "recibido": CERO,
            "neto": CERO,
        }

    def _fila(usuario_id: str) -> dict[str, Decimal]:
        return resultado.setdefault(
            str(usuario_id),
            {"pagado": CERO, "parte": CERO, "enviado": CERO, "recibido": CERO, "neto": CERO},
        )

    for gasto in gastos:
        if (gasto.get("estado") or "activo").lower() in ESTADOS_IGNORADOS:
            continue
        monto = redondear(gasto.get("monto", 0))
        pagador = str(gasto.get("pagado_por") or "")
        division = normalizar_division(gasto.get("division"))
        if not division:
            division = {pagador: monto} if pagador else {}
        if pagador:
            _fila(pagador)["pagado"] += monto
        for usuario_id, parte in division.items():
            _fila(usuario_id)["parte"] += parte

    for pago in pagos:
        monto = redondear(pago.get("monto", 0))
        de = str(pago.get("de_usuario") or "")
        a = str(pago.get("a_usuario") or "")
        if de:
            _fila(de)["enviado"] += monto
        if a:
            _fila(a)["recibido"] += monto

    for datos in resultado.values():
        datos["neto"] = redondear(
            datos["pagado"] - datos["parte"] + datos["enviado"] - datos["recibido"]
        )
    return resultado


def sugerir_transferencias(
    netos: Mapping[str, Any], nombres: Mapping[str, str] | None = None, minimo: Any = "0.01"
) -> list[dict[str, Any]]:
    """Lista mínima de transferencias que deja a todos en cero.

    Algoritmo voraz: el que más debe le paga al que más le deben. Genera como
    mucho `n - 1` transferencias.
    """
    nombres = nombres or {}
    umbral = decimal(minimo)
    deudas = {
        str(k): redondear(v)
        for k, v in netos.items()
        if redondear(v) < -umbral
    }
    creditos = {
        str(k): redondear(v)
        for k, v in netos.items()
        if redondear(v) > umbral
    }
    transferencias: list[dict[str, Any]] = []
    while deudas and creditos:
        deudor = min(deudas, key=lambda k: deudas[k])
        acreedor = max(creditos, key=lambda k: creditos[k])
        monto = min(-deudas[deudor], creditos[acreedor])
        if monto <= 0:
            break
        transferencias.append(
            {
                "de": deudor,
                "a": acreedor,
                "monto": redondear(monto),
                "de_nombre": nombres.get(deudor, deudor),
                "a_nombre": nombres.get(acreedor, acreedor),
            }
        )
        deudas[deudor] = redondear(deudas[deudor] + monto)
        creditos[acreedor] = redondear(creditos[acreedor] - monto)
        if deudas[deudor] >= -umbral:
            deudas.pop(deudor)
        if creditos[acreedor] <= umbral:
            creditos.pop(acreedor)
    return transferencias


def totales(saldos_por_persona: Mapping[str, Mapping[str, Any]]) -> dict[str, Decimal]:
    pagado = sum((decimal(d["pagado"]) for d in saldos_por_persona.values()), CERO)
    parte = sum((decimal(d["parte"]) for d in saldos_por_persona.values()), CERO)
    return {
        "pagado": redondear(pagado),
        "parte": redondear(parte),
        "a_favor": redondear(
            sum((decimal(d["neto"]) for d in saldos_por_persona.values() if decimal(d["neto"]) > 0), CERO)
        ),
        "en_contra": redondear(
            -sum((decimal(d["neto"]) for d in saldos_por_persona.values() if decimal(d["neto"]) < 0), CERO)
        ),
    }
