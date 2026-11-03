"""Controlador del panel de plataforma (administración del servicio)."""

from __future__ import annotations

from typing import Any

from ..modelos import planes
from .base import Controlador, Resultado


class ControladorAdmin(Controlador):
    def puede(self) -> bool:
        return bool((self.usuario or {}).get("es_admin_plataforma")) or self.config.es_admin(
            (self.usuario or {}).get("email", "")
        )

    def _guardia(self) -> Resultado | None:
        if not self.puede():
            return Resultado.error("Esta sección es sólo para administración de la plataforma.")
        return None

    def datos(self) -> Resultado:
        bloqueo = self._guardia()
        if bloqueo:
            return bloqueo
        try:
            resumen = self.repo.plataforma_resumen()
            return Resultado.exito(
                "",
                {
                    "resumen": resumen,
                    "usuarios": self.repo.plataforma_usuarios(),
                    "hogares": self.repo.plataforma_hogares(),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def cambiar_plan(self, hogar_id: str, plan: str) -> Resultado:
        bloqueo = self._guardia()
        if bloqueo:
            return bloqueo
        try:
            self.repo.cambiar_plan(hogar_id, plan)
            return Resultado.exito(f"Hogar pasado a plan {planes.etiqueta(plan)}.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def alternar_usuario(self, usuario_id: str, activo: bool) -> Resultado:
        bloqueo = self._guardia()
        if bloqueo:
            return bloqueo
        try:
            self.repo.alternar_usuario(usuario_id, activo)
            return Resultado.exito(
                "Cuenta habilitada." if activo else "Cuenta deshabilitada y sesiones cerradas."
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def almacen(self) -> dict[str, Any]:
        try:
            return {
                "descripcion": self.repo.store.ping(),
                "almacen": self.config.almacen,
                "medios": self.config.medios,
            }
        except Exception:  # noqa: BLE001
            return {"descripcion": "desconocido", "almacen": self.config.almacen, "medios": self.config.medios}
