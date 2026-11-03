"""Controlador del hogar: miembros, invitaciones, ajustes y pagos."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..modelos import planes
from ..modelos.repositorio import ROLES_ETIQUETA
from .base import Controlador, Resultado


class ControladorHogar(Controlador):
    # --- alta ------------------------------------------------------------- #
    def crear(self, nombre: str) -> Resultado:
        """Crea un hogar nuevo para la persona logueada (onboarding)."""
        try:
            hogar = self.repo.crear_hogar(self.usuario_id, nombre)
            return Resultado.exito(f"¡Listo! Creamos «{hogar.get('nombre')}».", hogar)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    # --- lectura ---------------------------------------------------------- #
    def datos(self) -> Resultado:
        try:
            hogar = self.repo.obtener_hogar(self.usuario_id, self.hogar_id)
            miembros = self.repo.miembros(self.hogar_id)
            invitaciones = (
                self.repo.invitaciones(self.hogar_id, self.usuario_id)
                if self.es_admin_hogar()
                else []
            )
            eventos = (
                self.repo.eventos(self.hogar_id, self.usuario_id)
                if self.es_admin_hogar()
                else []
            )
            return Resultado.exito(
                "",
                {
                    "hogar": hogar,
                    "miembros": miembros,
                    "invitaciones": invitaciones,
                    "eventos": eventos,
                    "puedo_administrar": self.es_admin_hogar(),
                    "es_propietario": self.rol == "propietario",
                    "plan": hogar.get("plan"),
                    "etiqueta_plan": planes.etiqueta(hogar.get("plan")),
                    "limite_miembros": planes.limites(hogar.get("plan"))["miembros"],
                    "roles": ROLES_ETIQUETA,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def miembros(self) -> list[dict[str, Any]]:
        try:
            return self.repo.miembros(self.hogar_id)
        except Exception:  # noqa: BLE001
            return []

    # --- invitaciones ----------------------------------------------------- #
    def invitar(self, rol: str = "miembro", dias: int = 14, usos_max: int = 10) -> Resultado:
        try:
            invitacion = self.repo.invitar(
                self.hogar_id, self.usuario_id, rol=rol, dias=dias, usos_max=usos_max
            )
            return Resultado.exito(
                f"Código creado: {invitacion['codigo']} (pasáselo a quien quieras sumar)",
                invitacion,
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def revocar(self, invitacion_id: str) -> Resultado:
        try:
            self.repo.revocar_invitacion(self.hogar_id, self.usuario_id, invitacion_id)
            return Resultado.exito("Invitación revocada.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def mensaje_invitacion(self, codigo: str, expira_en: str = "") -> Resultado:
        """Arma el texto listo para pegar en WhatsApp y el link `wa.me`."""
        try:
            codigo = (codigo or "").strip().upper()
            if not codigo:
                return Resultado.error("Falta el código de invitación.")
            hogar = self.repo.obtener_hogar(self.usuario_id, self.hogar_id)
            nombre_hogar = hogar.get("nombre") or "mi hogar"
            nombre = (self.usuario or {}).get("nombre") or ""
            url = (self.config.url_publica or "").strip().rstrip("/")

            if url:
                pasos = (
                    f"1) Entrá a {url}\n"
                    "2) Creá tu cuenta (si ya tenés, iniciá sesión)\n"
                    f"3) Código de invitación: {codigo}"
                )
            else:
                pasos = (
                    "1) Entrá a la app de Cuentas Claras\n"
                    "2) Creá tu cuenta (si ya tenés, iniciá sesión)\n"
                    f"3) Código de invitación: {codigo}"
                )

            vence = ""
            if expira_en:
                try:
                    from ..modelos.dinero import formatear_fecha

                    vence = f"\n\nEl código vence el {formatear_fecha(expira_en)}."
                except ValueError:
                    vence = ""

            mensaje = (
                f"¡Hola! Te invito a «{nombre_hogar}» en Cuentas Claras "
                "para llevar juntos los gastos de la casa.\n\n"
                f"{pasos}{vence}\n\n"
                "Es gratis y se usa desde el celular, sin instalar nada. "
                "Cualquier cosa, avisame."
                + (f"\n— {nombre}" if nombre else "")
            )
            enlace = "https://wa.me/?text=" + quote(mensaje)
            return Resultado.exito(
                "",
                {
                    "mensaje": mensaje,
                    "enlace": enlace,
                    "codigo": codigo,
                    "hogar": nombre_hogar,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    # --- personas --------------------------------------------------------- #
    def cambiar_rol(self, usuario_id: str, rol: str) -> Resultado:
        try:
            self.repo.cambiar_rol(self.hogar_id, self.usuario_id, usuario_id, rol)
            return Resultado.exito("Rol actualizado.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def quitar(self, usuario_id: str) -> Resultado:
        try:
            self.repo.quitar_miembro(self.hogar_id, self.usuario_id, usuario_id)
            return Resultado.exito("La persona salió del hogar.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def transferir(self, usuario_id: str) -> Resultado:
        try:
            self.repo.transferir_propiedad(self.hogar_id, self.usuario_id, usuario_id)
            return Resultado.exito("Listo: ahora esa persona es propietaria del hogar.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def salir(self) -> Resultado:
        try:
            self.repo.salir_del_hogar(self.hogar_id, self.usuario_id)
            return Resultado.exito("Saliste del hogar.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    # --- ajustes ---------------------------------------------------------- #
    def renombrar(self, nombre: str) -> Resultado:
        try:
            self.repo.renombrar_hogar(self.hogar_id, self.usuario_id, nombre)
            return Resultado.exito("Nombre actualizado.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def eliminar(self, confirmacion: str) -> Resultado:
        try:
            self.repo.eliminar_hogar(self.hogar_id, self.usuario_id, confirmacion)
            return Resultado.exito("El hogar y sus datos fueron eliminados.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    # --- pagos entre personas --------------------------------------------- #
    def registrar_pago(
        self,
        de_usuario: str,
        a_usuario: str,
        monto: Any,
        fecha: Any = None,
        nota: str = "",
    ) -> Resultado:
        try:
            pago = self.repo.registrar_pago(
                self.hogar_id,
                self.usuario_id,
                de_usuario,
                a_usuario,
                monto,
                fecha=fecha,
                nota=nota,
            )
            return Resultado.exito("Pago registrado.", pago)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def borrar_pago(self, pago_id: str) -> Resultado:
        try:
            self.repo.borrar_pago(self.hogar_id, self.usuario_id, pago_id)
            return Resultado.exito("Pago eliminado.")
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))
