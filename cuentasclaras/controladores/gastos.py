"""Controlador de gastos: alta, edición, anulación y comprobantes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from ..modelos import archivos as medios_mod
from ..modelos.dinero import clave_mes, formatear, hoy, nombre_mes
from .base import Controlador, Resultado


class ControladorGastos(Controlador):
    # --- lectura ---------------------------------------------------------- #
    def listar(
        self,
        mes: str = "",
        historico: bool = False,
        categoria: str | None = None,
        persona: str | None = None,
        texto: str = "",
    ) -> Resultado:
        try:
            desde, hasta = (None, None)
            if not historico and mes:
                from ..modelos.dinero import periodo

                desde, hasta = periodo(mes)
            gastos = self.repo.gastos(
                self.hogar_id, self.usuario_id, desde, hasta, categoria, persona, texto
            )
            total = sum((g["monto"] for g in gastos), Decimal("0"))
            return Resultado.exito(
                "",
                {
                    "gastos": gastos,
                    "total": total,
                    "cantidad": len(gastos),
                    "nombres": self.repo.nombres(self.hogar_id),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    def meses(self) -> list[str]:
        try:
            return self.repo.meses_con_datos(self.hogar_id, self.usuario_id)
        except Exception:  # noqa: BLE001
            return [clave_mes()]

    def detalle(self, gasto_id: str) -> Resultado:
        return self.correr(lambda: self.repo.gasto(self.hogar_id, self.usuario_id, gasto_id))

    def comprobante(self, gasto_id: str) -> Resultado:
        """Devuelve los bytes del comprobante (o None si no hay o no se puede leer)."""
        try:
            gasto = self.repo.gasto(self.hogar_id, self.usuario_id, gasto_id)
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        referencia = gasto.get("comprobante", "")
        if not referencia:
            return Resultado.aviso("Este gasto no tiene comprobante.", {"ref": ""})
        if self.medios is None:
            return Resultado.aviso("Los comprobantes no están configurados.", {"ref": referencia})
        datos = self.medios.leer(referencia)
        return Resultado.exito(
            "",
            {
                "ref": referencia,
                "bytes": datos,
                "mime": medios_mod.mime_de(referencia, datos),
                "nombre": medios_mod.nombre_descarga(gasto.get("concepto", ""), referencia),
            },
        )

    # --- escritura -------------------------------------------------------- #
    def agregar(
        self,
        concepto: str,
        monto: Any,
        categoria: str,
        pagado_por: str,
        participantes: Iterable[str],
        fecha: Any = None,
        archivo: tuple[str, bytes] | None = None,
    ) -> Resultado:
        try:
            referencia = ""
            if archivo is not None and self.medios is not None:
                nombre, contenido = archivo
                referencia = self.medios.guardar(self.hogar_id, contenido, nombre)
            gasto = self.repo.agregar_gasto(
                self.hogar_id,
                self.usuario_id,
                concepto,
                monto,
                categoria,
                pagado_por,
                list(participantes),
                fecha=fecha,
                comprobante=referencia,
            )
            return Resultado.exito(
                f"Gasto guardado: {gasto.get('concepto', '')} "
                f"({formatear(gasto.get('monto', 0), self.config.simbolo)})",
                gasto,
            )
        except medios_mod.ErrorArchivo as exc:
            return Resultado.error(f"No pudimos guardar el comprobante: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    def editar(
        self,
        gasto_id: str,
        concepto: str | None = None,
        monto: Any = None,
        categoria: str | None = None,
        pagado_por: str | None = None,
        participantes: Iterable[str] | None = None,
        fecha: Any = None,
        archivo: tuple[str, bytes] | None = None,
    ) -> Resultado:
        try:
            cambios: dict[str, Any] = {}
            if concepto is not None:
                cambios["concepto"] = concepto
            if monto is not None:
                cambios["monto"] = monto
            if categoria is not None:
                cambios["categoria"] = categoria
            if pagado_por:
                cambios["pagado_por"] = pagado_por
            if participantes:
                cambios["participantes"] = list(participantes)
            if fecha:
                cambios["fecha"] = fecha
            if archivo is not None and self.medios is not None:
                nombre, contenido = archivo
                anterior = self.repo.gasto(self.hogar_id, self.usuario_id, gasto_id).get(
                    "comprobante", ""
                )
                nuevo = self.medios.guardar(self.hogar_id, contenido, nombre)
                cambios["comprobante"] = nuevo
                if anterior:
                    self.medios.borrar(anterior)
            gasto = self.repo.editar_gasto(self.hogar_id, self.usuario_id, gasto_id, **cambios)
            return Resultado.exito("Cambios guardados.", gasto)
        except medios_mod.ErrorArchivo as exc:
            return Resultado.error(f"No pudimos guardar el comprobante: {exc}")
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    def anular(self, gasto_id: str) -> Resultado:
        try:
            self.repo.anular_gasto(self.hogar_id, self.usuario_id, gasto_id)
            return Resultado.exito("Gasto eliminado.")
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    # --- exportación ------------------------------------------------------ #
    def exportar_csv(self, mes: str = "", historico: bool = False) -> Resultado:
        try:
            desde, hasta = None, None
            if not historico and mes:
                from ..modelos.dinero import periodo

                desde, hasta = periodo(mes)
            contenido = self.repo.exportar_csv(
                self.hogar_id, self.usuario_id, desde, hasta
            )
            etiqueta = "historico" if historico or not mes else mes
            return Resultado.exito(
                "", {"csv": contenido, "nombre": f"gastos_{etiqueta}.csv"}
            )
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    def exportar_json(self) -> Resultado:
        try:
            contenido = self.repo.exportar_json(self.hogar_id, self.usuario_id)
            return Resultado.exito(
                "", {"json": contenido, "nombre": "respaldo_hogar.json"}
            )
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    # --- utilidades ------------------------------------------------------- #
    def miembros(self) -> list[dict[str, Any]]:
        try:
            return self.repo.miembros(self.hogar_id)
        except Exception:  # noqa: BLE001
            return []

    def etiqueta_mes(self, mes: str) -> str:
        return nombre_mes(mes) if mes else "Histórico completo"

    @staticmethod
    def es_hoy(fecha) -> bool:
        return fecha == hoy()

    @staticmethod
    def _error(exc: Exception) -> Resultado:
        mensaje = str(exc) or "Ocurrió un error."
        return Resultado.error(mensaje)
