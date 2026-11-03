"""Controlador de planes: estado de la suscripción y pedido de upgrade."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..modelos import planes
from .base import Controlador, Resultado


class ControladorPlanes(Controlador):
    def estado(self) -> Resultado:
        try:
            hogar = self.repo.obtener_hogar(self.usuario_id, self.hogar_id)
            plan = planes.normalizar_plan(hogar.get("plan"))
            limites = planes.limites(plan)
            propios = [
                h for h in self.repo.hogares_de(self.usuario_id) if h["rol"] == "propietario"
            ]
            uso = {
                "hogares": len(propios),
                "miembros": len(self.repo.miembros(self.hogar_id)),
                "gastos_mes": self._gastos_del_mes(),
            }
            return Resultado.exito(
                "",
                {
                    "hogar": hogar,
                    "plan": plan,
                    "etiqueta": planes.etiqueta(plan),
                    "limites": limites,
                    "uso": uso,
                    "comparativa": planes.comparativa(self.config),
                    "precio_mensual": planes.precio(planes.PRO, "mensual", self.config),
                    "precio_anual": planes.precio(planes.PRO, "anual", self.config),
                    "ahorro": self.config.ahorro_anual_pct,
                    "historial_meses": planes.meses_visibles(plan, self.config),
                    "es_pro": plan == planes.PRO,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def _gastos_del_mes(self) -> int:
        from ..modelos.dinero import clave_mes, periodo

        desde, hasta = periodo(clave_mes())
        try:
            return len(self.repo.gastos(self.hogar_id, self.usuario_id, desde, hasta))
        except Exception:  # noqa: BLE001
            return 0

    def pedido(self, ciclo: str = "mensual") -> dict[str, Any]:
        """Datos para armar el pedido de upgrade (mailto / WhatsApp)."""
        estado = self.estado().datos or {}
        precio = estado.get("precio_anual" if ciclo == "anual" else "precio_mensual", 0)
        hogar = estado.get("hogar", {})
        asunto = f"Quiero pasar mi hogar «{hogar.get('nombre', '')}» a Plan Pro"
        cuerpo = (
            "Hola, quiero contratar el Plan Pro de Cuentas Claras.\n\n"
            f"Hogar: {hogar.get('nombre', '')}\n"
            f"Identificador: {hogar.get('id', '')}\n"
            f"Plan pedido: Pro {ciclo}\n"
            f"Importe: {self.config.simbolo}{precio}\n\n"
            "Gracias."
        )
        return {
            "asunto": asunto,
            "cuerpo": cuerpo,
            "mailto": f"mailto:{self.config.soporte_email}?subject={quote(asunto)}&body={quote(cuerpo)}",
            "ciclo": ciclo,
            "precio": precio,
        }
