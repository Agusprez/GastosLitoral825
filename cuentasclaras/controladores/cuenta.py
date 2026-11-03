"""Controlador de la cuenta de la persona usuaria."""

from __future__ import annotations

from ..modelos import autenticacion as auth
from .base import Controlador, Resultado


class ControladorCuenta(Controlador):
    def perfil(self) -> Resultado:
        if not self.usuario_id:
            return Resultado.error("No hay sesión activa.")
        usuario = self.repo.usuario(self.usuario_id)
        if not usuario:
            return Resultado.error("La cuenta no existe.")
        return Resultado.exito("", usuario)

    def actualizar(self, nombre: str, email: str) -> Resultado:
        try:
            actualizado = self.repo.actualizar_perfil(
                self.usuario_id, nombre=nombre, email=email
            )
            return Resultado.exito("Datos actualizados.", actualizado)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def cambiar_clave(
        self, actual: str, nueva: str, repetir: str, token: str = ""
    ) -> Resultado:
        if nueva != repetir:
            return Resultado.error("La contraseña nueva no coincide con la repetición.")
        try:
            self.repo.cambiar_clave(self.usuario_id, actual, nueva, token_actual=token)
            return Resultado.exito(
                "Contraseña cambiada. Cerramos las sesiones abiertas en otros dispositivos."
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def cerrar_otras_sesiones(self, token: str) -> Resultado:
        try:
            cuantas = auth.revocar_todas(self.repo.store, self.usuario_id, excepto=token)
            return Resultado.exito(
                f"Cerramos {cuantas} sesión(es) en otros dispositivos."
                if cuantas
                else "No había otras sesiones abiertas."
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def sesiones_activas(self) -> int:
        try:
            from ..modelos.dinero import ahora, desde_iso

            total = 0
            for fila in self.repo.store.filtrar("sesiones", usuario_id=self.usuario_id):
                if (fila.get("revocada") or "No") in ("Si", "sí", "true", "1"):
                    continue
                if desde_iso(fila.get("expira_en", "")) > ahora():
                    total += 1
            return total
        except Exception:  # noqa: BLE001
            return 1

    def eliminar(self, clave: str, token: str = "") -> Resultado:
        try:
            self.repo.eliminar_cuenta(self.usuario_id, clave)
            return Resultado.exito(
                "Tu cuenta fue eliminada. Gracias por haber usado Cuentas Claras."
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))
