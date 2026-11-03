"""Controlador de la lista de compras."""

from __future__ import annotations

from typing import Any

from .base import Controlador, Resultado


class ControladorCompras(Controlador):
    def listar(self, incluir_compradas: bool = False) -> Resultado:
        try:
            return Resultado.exito(
                "",
                {
                    "items": self.repo.compras(
                        self.hogar_id, self.usuario_id, incluir_compradas
                    ),
                    "compras_pendientes": len(
                        self.repo.compras(self.hogar_id, self.usuario_id)
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def agregar(self, texto: str) -> Resultado:
        if not (texto or "").strip():
            return Resultado.error("Escribí qué hace falta comprar.")
        try:
            item = self.repo.agregar_compra(self.hogar_id, self.usuario_id, texto)
            return Resultado.exito(f"«{item['texto']}» anotado.", item)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def marcar(self, item_id: str, comprada: bool = True) -> Resultado:
        try:
            self.repo.cambiar_estado_compra(
                self.hogar_id, self.usuario_id, item_id, comprada
            )
            return Resultado.exito(
                "Marcado como comprado." if comprada else "Vuelve a pendientes."
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def borrar(self, item_id: str) -> Resultado:
        try:
            self.repo.borrar_compra(self.hogar_id, self.usuario_id, item_id)
            return Resultado.exito("Ítem eliminado.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def limpiar_compradas(self) -> Resultado:
        try:
            borrados = self.repo.limpiar_compradas(self.hogar_id, self.usuario_id)
            return Resultado.exito(f"{borrados} ítem(s) quitados de la lista.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def datos(self, incluir_compradas: bool = False) -> dict[str, Any]:
        return self.listar(incluir_compradas).datos or {}
