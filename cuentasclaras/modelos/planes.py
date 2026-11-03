"""Planes comerciales y límites.

Los límites se aplican en la capa de negocio (`repositorio`), no en la UI, para
que no se puedan saltear desde la interfaz.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .configuracion import Config

GRATIS = "gratis"
PRO = "pro"

# `None` = sin límite.
LIMITES: dict[str, dict[str, Any]] = {
    GRATIS: {
        "hogares": 1,
        "miembros": 3,
        "gastos_mes": 200,
        "comprobantes_mes": 20,
        "historial_meses": 12,
    },
    PRO: {
        "hogares": 5,
        "miembros": 15,
        "gastos_mes": None,
        "comprobantes_mes": None,
        "historial_meses": None,
    },
}

ETIQUETAS = {GRATIS: "Gratis", PRO: "Pro"}

DESCRIPCION = {
    GRATIS: "Para probar el sistema con tu casa, sin tarjeta.",
    PRO: "Para hogares activos y para quien administra varias casas.",
}

ALIAS = {"free": GRATIS, "gratuito": GRATIS, "basico": GRATIS, "básico": GRATIS,
         "pro": PRO, "pago": PRO, "premium": PRO}


def normalizar_plan(plan: str | None) -> str:
    return ALIAS.get((plan or "").strip().lower(), GRATIS)


def limites(plan: str | None) -> dict[str, Any]:
    return LIMITES[normalizar_plan(plan)]


def plan_de(hogar: dict[str, Any] | None) -> str:
    return normalizar_plan((hogar or {}).get("plan"))


def etiqueta(plan: str | None) -> str:
    return ETIQUETAS[normalizar_plan(plan)]


def precio(plan: str | None, ciclo: str = "mensual", config: Config | None = None) -> Decimal:
    """Precio del plan. El gratuito siempre es 0."""
    if normalizar_plan(plan) == GRATIS:
        return Decimal("0")
    config = config or Config()
    return config.precio_anual_num if ciclo == "anual" else config.precio_mensual_num


def permite(plan: str | None, recurso: str, cantidad_actual: int) -> bool:
    """¿Se puede sumar uno más de `recurso`?"""
    tope = limites(plan).get(recurso)
    return tope is None or cantidad_actual < tope


def restantes(plan: str | None, recurso: str, cantidad_actual: int) -> int | None:
    tope = limites(plan).get(recurso)
    if tope is None:
        return None
    return max(tope - cantidad_actual, 0)


def meses_visibles(plan: str | None, config: Config) -> int | None:
    """Cuántos meses de historial puede consultar el plan (None = todo)."""
    if normalizar_plan(plan) == GRATIS:
        return config.historial_gratis_meses
    return limites(plan)["historial_meses"]


def texto_limite(plan: str | None, recurso: str) -> str:
    tope = limites(plan).get(recurso)
    if tope is None:
        return "sin límite"
    return str(tope)


def comparativa(config: Config) -> list[dict[str, Any]]:
    """Filas para la tabla de precios de la landing."""
    return [
        {
            "caracteristica": "Hogares por cuenta",
            "gratis": str(LIMITES[GRATIS]["hogares"]),
            "pro": str(LIMITES[PRO]["hogares"]),
        },
        {
            "caracteristica": "Personas por hogar",
            "gratis": str(LIMITES[GRATIS]["miembros"]),
            "pro": str(LIMITES[PRO]["miembros"]),
        },
        {
            "caracteristica": "Gastos por mes",
            "gratis": str(LIMITES[GRATIS]["gastos_mes"]),
            "pro": "Ilimitados",
        },
        {
            "caracteristica": "Historial consultable",
            "gratis": f"{config.historial_gratis_meses} meses",
            "pro": "Completo",
        },
        {
            "caracteristica": "Comprobantes adjuntos",
            "gratis": str(LIMITES[GRATIS]["comprobantes_mes"]) + " / mes",
            "pro": "Ilimitados",
        },
        {"caracteristica": "Exportar a CSV", "gratis": "Sí", "pro": "Sí"},
        {"caracteristica": "Soporte por email", "gratis": "Comunidad", "pro": "Prioritario"},
    ]
