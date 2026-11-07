"""Controlador del hogar: miembros, invitaciones, ajustes y pagos."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..modelos import migracion, planes
from ..modelos.repositorio import ROLES_ETIQUETA
from .base import Controlador, Resultado

ACCION_IMPORTACION = "importacion_v1"


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

    # --- importación de la planilla vieja (v1) ---------------------------- #
    def _pestanas_v1(self) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
        """Devuelve (gastos, compras, origen) leyendo la planilla de la v1.

        Primero busca las pestañas por nombre; si no las encuentra, las busca por
        los encabezados (`Fecha, Quien, Concepto, Monto`), así funciona aunque la
        pestaña se llame distinto. Si tampoco están y hay `hoja_url_legacy`
        configurada, las busca en esa otra planilla.
        """
        store = self.repo.store
        leer = getattr(store, "leer_pestana", None)
        if not callable(leer):
            return [], [], ""
        gastos = leer(migracion.PESTANA_GASTOS)
        compras = leer(migracion.PESTANA_COMPRAS)
        if gastos or compras:
            return gastos, compras, "actual"

        buscar = getattr(store, "buscar_pestana_por_columnas", None)
        if callable(buscar):
            try:
                encontrada = buscar(migracion.COLUMNAS_GASTOS)
                if encontrada:
                    _titulo, gastos = encontrada
                encontrada = buscar(migracion.COLUMNAS_COMPRAS)
                if encontrada:
                    _titulo, compras = encontrada
            except Exception:  # noqa: BLE001
                gastos, compras = [], []
            if gastos or compras:
                return gastos, compras, "por_columnas"

        legacy = (getattr(self.config, "hoja_url_legacy", "") or "").strip()
        leer_externa = getattr(store, "leer_pestana_externa", None)
        if legacy and callable(leer_externa):
            try:
                gastos = leer_externa(migracion.PESTANA_GASTOS, legacy)
                compras = leer_externa(migracion.PESTANA_COMPRAS, legacy)
            except Exception:  # noqa: BLE001 - planilla sin permiso, URL mala
                return [], [], "externa_error"
            if gastos or compras:
                return gastos, compras, "externa"
        return [], [], ""

    def _pestanas_visibles(self) -> list[str]:
        listar = getattr(self.repo.store, "pestanas", None)
        if not callable(listar):
            return []
        try:
            return sorted(listar())
        except Exception:  # noqa: BLE001
            return []

    def _datos_analisis(
        self,
        filas: list[dict[str, str]],
        compras: list[dict[str, str]],
        origen: str,
    ) -> dict[str, Any]:
        """Arma el resumen + mapeo propuesto para una fuente de datos cualquiera."""
        informe = migracion.analizar(filas)
        miembros = self.repo.miembros(self.hogar_id)
        mapeo = migracion.proponer_mapeo(informe.personas, miembros)
        ya = self.repo.buscar_evento(self.hogar_id, ACCION_IMPORTACION)
        return {
            "filas": len(filas),
            "compras": len(compras),
            "origen": origen,
            "informe": informe,
            "miembros": miembros,
            "mapeo": mapeo,
            "ya_importado": (ya or {}).get("creado_en", ""),
            "sin_asignar": [n for n in informe.personas if n not in mapeo],
        }

    def analizar_importacion(self) -> Resultado:
        """Lee las pestañas de la v1 y propone a quién corresponde cada nombre."""
        try:
            if self.rol != "propietario":
                return Resultado.error(
                    "Sólo quien es propietario/a del hogar puede importar los datos."
                )
            filas, compras, origen = self._pestanas_v1()
            if not filas and not compras:
                return Resultado.aviso(
                    "No encontramos las pestañas «Gastos» ni «Lista_Compras» en la "
                    "planilla.",
                    {
                        "filas": 0,
                        "compras": 0,
                        "origen": origen,
                        "pestanas": self._pestanas_visibles(),
                        "hoja_legacy": (
                            getattr(self.config, "hoja_url_legacy", "") or ""
                        ).strip(),
                    },
                )
            datos = self._datos_analisis(filas, compras, origen)
            datos["pestanas"] = self._pestanas_visibles()
            return Resultado.exito("", datos)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def analizar_filas(
        self,
        filas: list[dict[str, str]],
        compras: list[dict[str, str]] | None = None,
    ) -> Resultado:
        """Igual que `analizar_importacion`, pero con filas ya cargadas (archivo)."""
        try:
            if self.rol != "propietario":
                return Resultado.error(
                    "Sólo quien es propietario/a del hogar puede importar los datos."
                )
            if not filas:  # puede venir sólo la lista de compras
                return Resultado.aviso(
                    "El archivo no tiene filas de gastos.", {"filas": 0, "compras": 0}
                )
            return Resultado.exito(
                "", self._datos_analisis(filas, compras or [], "archivo")
            )
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def _importar(
        self,
        filas: list[dict[str, str]],
        compras: list[dict[str, str]],
        mapeo: dict[str, str],
        por_defecto: str,
    ) -> Resultado:
        informe = migracion.importar(
            self.repo,
            self.hogar_id,
            filas,
            mapeo,
            aplicar=True,
            compras=compras,
            por_defecto=por_defecto,
        )
        self.repo.registrar_evento(
            self.hogar_id,
            self.usuario_id,
            ACCION_IMPORTACION,
            f"{informe.importados} gastos, {informe.compras} compras",
        )
        mensaje = (
            f"Importamos {informe.importados} gasto(s)"
            + (f" y {informe.compras} compra(s)" if informe.compras else "")
            + "."
        )
        if informe.omitidos:
            mensaje += f" Quedaron {informe.omitidos} fila(s) sin importar."
        return Resultado.exito(mensaje, informe)

    def importar_v1(
        self, mapeo: dict[str, str], por_defecto: str = ""
    ) -> Resultado:
        """Importa los gastos y compras de la planilla vieja al hogar activo."""
        try:
            if self.rol != "propietario":
                return Resultado.error(
                    "Sólo quien es propietario/a del hogar puede importar los datos."
                )
            filas, compras, _origen = self._pestanas_v1()
            if not filas and not compras:
                return Resultado.error("No hay datos de la planilla vieja para importar.")
            return self._importar(filas, compras, mapeo, por_defecto)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

    def importar_filas(
        self,
        filas: list[dict[str, str]],
        mapeo: dict[str, str],
        por_defecto: str = "",
        compras: list[dict[str, str]] | None = None,
    ) -> Resultado:
        """Importa gastos desde un archivo (CSV/Excel) subido a la app."""
        try:
            if self.rol != "propietario":
                return Resultado.error(
                    "Sólo quien es propietario/a del hogar puede importar los datos."
                )
            if not filas:
                return Resultado.error("No hay filas para importar.")
            return self._importar(filas, compras or [], mapeo, por_defecto)
        except Exception as exc:  # noqa: BLE001
            return Resultado.error(str(exc))

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
