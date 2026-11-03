"""Controlador del tablero de inicio (resumen del período)."""

from __future__ import annotations

from typing import Any

from ..modelos import planes
from ..modelos.dinero import clave_mes, nombre_mes
from .base import Controlador, Resultado


class ControladorResumen(Controlador):
    def meses(self) -> list[str]:
        try:
            return self.repo.meses_con_datos(self.hogar_id, self.usuario_id)
        except Exception:  # noqa: BLE001
            return [clave_mes()]

    def etiqueta_periodo(self, mes: str, historico: bool) -> str:
        if historico or not mes:
            return "Histórico completo"
        return nombre_mes(mes)

    def panel(self, mes: str = "", historico: bool = False) -> Resultado:
        try:
            resumen = self.repo.resumen(
                self.hogar_id,
                self.usuario_id,
                mes=mes or None,
                historico=historico,
            )
            plan = resumen["hogar"].get("plan")
            resumen["limites"] = {
                "plan": plan,
                "etiqueta": planes.etiqueta(plan),
                "miembros": planes.limites(plan)["miembros"],
                "gastos_mes": planes.limites(plan)["gastos_mes"],
                "historial_meses": planes.meses_visibles(plan, self.config),
            }
            resumen["es_gratis"] = planes.normalizar_plan(plan) == planes.GRATIS
            resumen["mi_neto"] = resumen["saldos"].get(self.usuario_id, {}).get("neto", 0)
            return Resultado.exito("", resumen)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def compras_pendientes(self) -> int:
        try:
            return len(self.repo.compras(self.hogar_id, self.usuario_id))
        except Exception:  # noqa: BLE001
            return 0

    def datos(self, mes: str = "", historico: bool = False) -> dict[str, Any]:
        return self.panel(mes, historico).datos or {}
