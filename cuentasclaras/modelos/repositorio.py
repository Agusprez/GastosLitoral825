"""Reglas de negocio: usuarios, hogares, gastos, compras y pagos.

Esta es la única capa que puede tocar el `Store`. Toda operación recibe el
usuario que la ejecuta y verifica su membresía en el hogar: así el aislamiento
entre hogares queda garantizado por un solo punto y no depende de que la
interfaz recuerde filtrar.
"""

from __future__ import annotations

import csv
import io
import json
import secrets
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Mapping

from . import autenticacion as auth, planes as plans, saldos as balances
from .configuracion import Config
from .dinero import (
    ahora,
    clave_mes,
    desde_iso,
    fecha_iso,
    formatear,
    hoy,
    iso,
    monto_texto,
    parsear_fecha,
    periodo,
    redondear,
)
from .almacen import Store, nuevo_id

CATEGORIAS = (
    "Supermercado", "Servicios", "Internet", "Auto", "Salidas",
    "Casa", "Salud", "Mascotas", "Otros",
)

ROLES = {"propietario": 3, "admin": 2, "miembro": 1}
ROLES_ETIQUETA = {
    "propietario": "Propietario/a",
    "admin": "Administrador/a",
    "miembro": "Miembro",
}

ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin I, O, 0, 1
MAX_NOMBRE_HOGAR = 60
MAX_CONCEPTO = 120
MAX_NOTA = 200
MAX_TEXTO_COMPRA = 140
MAX_MONTO = Decimal("99999999.99")


class ErrorNegocio(Exception):
    """Error esperable, con mensaje pensado para mostrarse al usuario."""


class NoAutorizado(ErrorNegocio):
    pass


class LimiteAlcanzado(ErrorNegocio):
    def __init__(self, mensaje: str, plan: str = plans.GRATIS) -> None:
        super().__init__(mensaje)
        self.plan = plan


class NoEncontrado(ErrorNegocio):
    pass


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _limpiar(texto: Any, maximo: int) -> str:
    limpio = " ".join(str(texto or "").split())
    return limpio[:maximo]


def _slug(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def _codigo_invitacion() -> str:
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(6))


def _si(valor: Any) -> bool:
    return str(valor or "").strip().lower() in {"si", "sí", "s", "1", "true", "yes"}


def _nivel(rol: str | None) -> int:
    return ROLES.get((rol or "").strip().lower(), 0)


def _validar_monto(monto: Any) -> Decimal:
    valor = redondear(monto)
    if valor <= 0:
        raise ErrorNegocio("El monto tiene que ser mayor a cero.")
    if valor > MAX_MONTO:
        raise ErrorNegocio(f"El monto máximo por movimiento es {formatear(MAX_MONTO)}.")
    return valor


class Repositorio:
    def __init__(self, store: Store, config: Config | None = None) -> None:
        self.store = store
        self.config = config or Config()

    # ------------------------------------------------------------------ #
    # Usuarios
    # ------------------------------------------------------------------ #
    def crear_usuario(
        self,
        email: str,
        nombre: str,
        clave: str,
        rol: str = "usuario",
        activo: bool = True,
    ) -> dict[str, Any]:
        if not self.config.registro_abierto and rol != "admin":
            raise ErrorNegocio(
                "El registro está cerrado por ahora. Escribinos si querés una invitación."
            )
        email = auth.normalizar_email(email)
        nombre = _limpiar(nombre, 60)
        if not auth.email_valido(email):
            raise ErrorNegocio("Ingresá un email válido.")
        if not nombre:
            raise ErrorNegocio("Ingresá tu nombre.")
        if self.store.filtrar("usuarios", email=email):
            raise ErrorNegocio("Ya existe una cuenta con ese email. Probá iniciar sesión.")
        problemas = auth.revisar_clave(clave, email, nombre)
        if problemas:
            raise ErrorNegocio(" ".join(problemas))

        usuario = self.store.insert(
            "usuarios",
            {
                "id": nuevo_id(),
                "email": email,
                "nombre": nombre,
                "hash_clave": auth.hash_clave(clave),
                "rol": "admin" if self.config.es_admin(email) else rol,
                "activo": "Si" if activo else "No",
                "creado_en": iso(),
                "ultimo_login": "",
                "intentos_fallidos": "0",
                "bloqueado_hasta": "",
                "hogar_activo": "",
            },
        )
        return self.usuario(usuario["id"]) or usuario

    def usuario(self, usuario_id: str) -> dict[str, Any] | None:
        fila = self.store.uno("usuarios", usuario_id)
        return self._usuario_norm(fila) if fila else None

    def usuario_por_email(self, email: str) -> dict[str, Any] | None:
        encontrados = self.store.filtrar("usuarios", email=auth.normalizar_email(email))
        return self._usuario_norm(encontrados[0]) if encontrados else None

    def _usuario_norm(self, fila: dict[str, str]) -> dict[str, Any]:
        datos = dict(fila)
        for campo in ("hash_clave", "codigo_recuperacion"):
            datos.pop(campo, None)
        datos["activo_booleano"] = _si(datos.get("activo", "Si"))
        datos["es_admin_plataforma"] = (
            self.config.es_admin(datos.get("email", ""))
            or (datos.get("rol") or "").lower() == "admin"
        )
        return datos

    def actualizar_perfil(
        self, usuario_id: str, nombre: str | None = None, email: str | None = None
    ) -> dict[str, Any]:
        campos: dict[str, str] = {}
        if nombre is not None:
            limpio = _limpiar(nombre, 60)
            if not limpio:
                raise ErrorNegocio("El nombre no puede quedar vacío.")
            campos["nombre"] = limpio
        if email is not None:
            nuevo = auth.normalizar_email(email)
            if not auth.email_valido(nuevo):
                raise ErrorNegocio("Ingresá un email válido.")
            if nuevo != self.store.uno("usuarios", usuario_id)["email"]:
                if self.store.filtrar("usuarios", email=nuevo):
                    raise ErrorNegocio("Ese email ya está en uso.")
                campos["email"] = nuevo
                campos["rol"] = "admin" if self.config.es_admin(nuevo) else "usuario"
        if campos:
            self.store.update("usuarios", usuario_id, campos)
        return self.usuario(usuario_id) or {}

    def cambiar_clave(
        self, usuario_id: str, clave_actual: str, clave_nueva: str, token_actual: str = ""
    ) -> None:
        fila = self.store.uno("usuarios", usuario_id)
        if not fila:
            raise NoEncontrado("Usuario inexistente.")
        if not auth.verificar_clave(clave_actual, fila.get("hash_clave", "")):
            raise ErrorNegocio("La contraseña actual no es correcta.")
        problemas = auth.revisar_clave(
            clave_nueva, fila.get("email", ""), fila.get("nombre", "")
        )
        if problemas:
            raise ErrorNegocio(" ".join(problemas))
        self.store.update("usuarios", usuario_id, {"hash_clave": auth.hash_clave(clave_nueva)})
        # Cerramos el resto de las sesiones abiertas.
        auth.revocar_todas(self.store, usuario_id, excepto=token_actual)

    def eliminar_cuenta(self, usuario_id: str, clave: str) -> None:
        fila = self.store.uno("usuarios", usuario_id)
        if not fila:
            raise NoEncontrado("Usuario inexistente.")
        if not auth.verificar_clave(clave, fila.get("hash_clave", "")):
            raise ErrorNegocio("La contraseña no es correcta.")
        hogares = self.hogares_de(usuario_id)
        if any(h["rol"] == "propietario" and h["miembros"] > 1 for h in hogares):
            raise ErrorNegocio(
                "Antes de borrar tu cuenta transferí la propiedad de tus hogares "
                "o quitá a las demás personas."
            )
        for hogar in hogares:
            self._quitar_membresia(hogar["id"], usuario_id)
        for gasto in self.store.filtrar("gastos", creado_por=usuario_id):
            self.store.delete("gastos", gasto["id"])
        auth.revocar_todas(self.store, usuario_id)
        self.store.delete("usuarios", usuario_id)

    # ------------------------------------------------------------------ #
    # Hogares y membresías
    # ------------------------------------------------------------------ #
    def plan_efectivo(self, usuario_id: str) -> str:
        """El mejor plan entre los hogares de la persona (define sus límites)."""
        mejor = plans.GRATIS
        for fila in self.store.filtrar("miembros", usuario_id=usuario_id):
            hogar = self.store.uno("hogares", fila["hogar_id"])
            if hogar and plans.normalizar_plan(hogar.get("plan")) == plans.PRO:
                return plans.PRO
        return mejor

    def crear_hogar(self, usuario_id: str, nombre: str, moneda: str | None = None) -> dict[str, Any]:
        nombre = _limpiar(nombre, MAX_NOMBRE_HOGAR)
        if len(nombre) < 2:
            raise ErrorNegocio("Poné un nombre de al menos 2 caracteres.")
        propios = [h for h in self.hogares_de(usuario_id) if h["rol"] == "propietario"]
        plan = self.plan_efectivo(usuario_id)
        if not plans.permite(plan, "hogares", len(propios)):
            raise LimiteAlcanzado(
                f"Tu plan {plans.etiqueta(plan)} permite {plans.texto_limite(plan, 'hogares')} "
                "hogar(es). Pasate a Pro para administrar más de uno.",
                plan=plan,
            )
        hogar = self.store.insert(
            "hogares",
            {
                "id": nuevo_id(),
                "nombre": nombre,
                "moneda": (moneda or self.config.moneda).upper()[:8],
                "plan": plans.GRATIS,
                "division": "iguales",
                "activo": "Si",
                "creado_en": iso(),
                "creado_por": usuario_id,
                "plan_hasta": "",
            },
        )
        self._agregar_membresia(hogar["id"], usuario_id, "propietario")
        self._auditar(hogar["id"], usuario_id, "hogar_creado", nombre)
        return self.obtener_hogar(usuario_id, hogar["id"])

    def hogares_de(self, usuario_id: str) -> list[dict[str, Any]]:
        salida: list[dict[str, Any]] = []
        for fila in self.store.filtrar("miembros", usuario_id=usuario_id):
            if (fila.get("estado") or "activo").lower() != "activo":
                continue
            hogar = self.store.uno("hogares", fila["hogar_id"])
            if not hogar or not _si(hogar.get("activo", "Si")):
                continue
            datos = dict(hogar)
            datos["rol"] = fila.get("rol", "miembro")
            datos["unido_en"] = fila.get("unido_en", "")
            datos["miembros"] = len(self._miembros_activos(hogar["id"]))
            datos["plan"] = plans.normalizar_plan(hogar.get("plan"))
            salida.append(datos)
        salida.sort(key=lambda h: h.get("creado_en", ""))
        return salida

    def obtener_hogar(self, usuario_id: str, hogar_id: str) -> dict[str, Any]:
        hogar = self.store.uno("hogares", hogar_id)
        if not hogar or not _si(hogar.get("activo", "Si")):
            raise NoEncontrado("Ese hogar no existe.")
        rol = self.rol_en(hogar_id, usuario_id)
        if not rol:
            raise NoAutorizado("No tenés acceso a este hogar.")
        datos = dict(hogar)
        datos["rol"] = rol
        datos["plan"] = plans.normalizar_plan(hogar.get("plan"))
        datos["miembros"] = len(self._miembros_activos(hogar_id))
        return datos

    def rol_en(self, hogar_id: str, usuario_id: str) -> str | None:
        for fila in self.store.filtrar("miembros", hogar_id=hogar_id, usuario_id=usuario_id):
            if (fila.get("estado") or "activo").lower() == "activo":
                return (fila.get("rol") or "miembro").lower()
        return None

    def exigir(self, hogar_id: str, usuario_id: str, minimo: str = "miembro") -> str:
        rol = self.rol_en(hogar_id, usuario_id)
        if not rol:
            raise NoAutorizado("No tenés acceso a este hogar.")
        if _nivel(rol) < _nivel(minimo):
            raise NoAutorizado(
                f"Necesitás rol de {ROLES_ETIQUETA.get(minimo, minimo).lower()} para esto."
            )
        return rol

    def _miembros_activos(self, hogar_id: str) -> list[dict[str, str]]:
        return [
            fila
            for fila in self.store.filtrar("miembros", hogar_id=hogar_id)
            if (fila.get("estado") or "activo").lower() == "activo"
        ]

    def _agregar_membresia(self, hogar_id: str, usuario_id: str, rol: str) -> dict[str, str]:
        existente = self.store.filtrar("miembros", hogar_id=hogar_id, usuario_id=usuario_id)
        if existente:
            self.store.update(
                "miembros", existente[0]["id"], {"rol": rol, "estado": "activo"}
            )
            return existente[0]
        return self.store.insert(
            "miembros",
            {
                "id": nuevo_id(),
                "hogar_id": hogar_id,
                "usuario_id": usuario_id,
                "rol": rol,
                "estado": "activo",
                "unido_en": iso(),
            },
        )

    def _quitar_membresia(self, hogar_id: str, usuario_id: str) -> None:
        for fila in self.store.filtrar("miembros", hogar_id=hogar_id, usuario_id=usuario_id):
            self.store.update("miembros", fila["id"], {"estado": "baja"})

    def miembros(self, hogar_id: str) -> list[dict[str, Any]]:
        salida = []
        for fila in self._miembros_activos(hogar_id):
            usuario = self.store.uno("usuarios", fila["usuario_id"])
            if not usuario:
                continue
            salida.append(
                {
                    "usuario_id": fila["usuario_id"],
                    "nombre": usuario.get("nombre", ""),
                    "email": usuario.get("email", ""),
                    "rol": (fila.get("rol") or "miembro").lower(),
                    "unido_en": fila.get("unido_en", ""),
                    "activo": usuario.get("activo", "Si"),
                }
            )
        salida.sort(key=lambda m: (-_nivel(m["rol"]), _slug(m["nombre"])))
        return salida

    def nombres(self, hogar_id: str) -> dict[str, str]:
        """id -> nombre, incluyendo ex miembros (los gastos viejos los referencian)."""
        nombres: dict[str, str] = {}
        for fila in self.store.filtrar("miembros", hogar_id=hogar_id):
            usuario = self.store.uno("usuarios", fila["usuario_id"])
            if usuario:
                nombres.setdefault(fila["usuario_id"], usuario.get("nombre", ""))
        return nombres

    def renombrar_hogar(self, hogar_id: str, usuario_id: str, nombre: str) -> None:
        self.exigir(hogar_id, usuario_id, "admin")
        limpio = _limpiar(nombre, MAX_NOMBRE_HOGAR)
        if len(limpio) < 2:
            raise ErrorNegocio("El nombre es demasiado corto.")
        self.store.update("hogares", hogar_id, {"nombre": limpio})
        self._auditar(hogar_id, usuario_id, "hogar_renombrado", limpio)

    def cambiar_plan(self, hogar_id: str, plan: str) -> dict[str, Any]:
        """Sólo desde el panel de plataforma (cobro manual o pasarela a futuro)."""
        destino = plans.normalizar_plan(plan)
        self.store.update(
            "hogares",
            hogar_id,
            {
                "plan": destino,
                "plan_hasta": (
                    iso(ahora() + timedelta(days=365)) if destino == plans.PRO else ""
                ),
            },
        )
        self._auditar(hogar_id, "", "plan_cambiado", destino)
        return dict(self.store.uno("hogares", hogar_id))

    # --- invitaciones --------------------------------------------------- #
    def invitar(
        self,
        hogar_id: str,
        usuario_id: str,
        rol: str = "miembro",
        dias: int = 14,
        usos_max: int = 10,
    ) -> dict[str, Any]:
        self.exigir(hogar_id, usuario_id, "admin")
        rol = rol if rol in ("admin", "miembro") else "miembro"
        hogar = self.store.uno("hogares", hogar_id)
        plan = plans.normalizar_plan(hogar.get("plan"))
        cantidad = len(self._miembros_activos(hogar_id))
        if not plans.permite(plan, "miembros", cantidad):
            raise LimiteAlcanzado(
                f"El plan {plans.etiqueta(plan)} permite {plans.texto_limite(plan, 'miembros')} "
                "personas por hogar.",
                plan=plan,
            )
        codigo = _codigo_invitacion()
        while any(i.get("codigo") == codigo for i in self.store.all("invitaciones")):
            codigo = _codigo_invitacion()
        invitacion = self.store.insert(
            "invitaciones",
            {
                "id": nuevo_id(),
                "hogar_id": hogar_id,
                "codigo": codigo,
                "rol": rol,
                "creado_por": usuario_id,
                "creado_en": iso(),
                "expira_en": iso(ahora() + timedelta(days=max(1, min(dias, 90)))),
                "usos": "0",
                "usos_max": str(max(1, usos_max)),
                "activa": "Si",
            },
        )
        self._auditar(hogar_id, usuario_id, "invitacion_creada", codigo)
        return dict(invitacion)

    def invitaciones(self, hogar_id: str, usuario_id: str) -> list[dict[str, Any]]:
        self.exigir(hogar_id, usuario_id, "admin")
        salida = []
        for fila in self.store.filtrar("invitaciones", hogar_id=hogar_id):
            datos = dict(fila)
            datos["vigente"] = self._invitacion_vigente(datos)
            salida.append(datos)
        salida.sort(key=lambda i: i.get("creado_en", ""), reverse=True)
        return salida

    def _invitacion_vigente(self, fila: Mapping[str, Any]) -> bool:
        from .dinero import desde_iso

        if not _si(fila.get("activa", "Si")):
            return False
        if desde_iso(fila.get("expira_en", "")) <= ahora():
            return False
        return int(fila.get("usos") or 0) < int(fila.get("usos_max") or 1)

    def revocar_invitacion(self, hogar_id: str, usuario_id: str, invitacion_id: str) -> None:
        self.exigir(hogar_id, usuario_id, "admin")
        fila = self.store.uno("invitaciones", invitacion_id)
        if not fila or fila.get("hogar_id") != hogar_id:
            raise NoEncontrado("Invitación inexistente.")
        self.store.update("invitaciones", invitacion_id, {"activa": "No"})

    def unirse_por_codigo(self, usuario_id: str, codigo: str) -> dict[str, Any]:
        codigo = (codigo or "").strip().upper().replace(" ", "")
        if not codigo:
            raise ErrorNegocio("Ingresá el código de invitación.")
        candidatas = self.store.filtrar("invitaciones", codigo=codigo)
        vigentes = [i for i in candidatas if self._invitacion_vigente(i)]
        if not vigentes:
            raise ErrorNegocio("El código no es válido o ya venció.")
        invitacion = vigentes[0]
        hogar_id = invitacion["hogar_id"]
        hogar = self.store.uno("hogares", hogar_id)
        if not hogar or not _si(hogar.get("activo", "Si")):
            raise NoEncontrado("Ese hogar ya no está disponible.")
        if self.rol_en(hogar_id, usuario_id):
            raise ErrorNegocio(f"Ya formás parte de «{hogar['nombre']}».")

        plan = plans.normalizar_plan(hogar.get("plan"))
        if not plans.permite(plan, "miembros", len(self._miembros_activos(hogar_id))):
            raise LimiteAlcanzado(
                "Ese hogar llegó al máximo de personas de su plan. "
                "Pedile a quien lo administra que pase a Pro.",
                plan=plan,
            )
        self._agregar_membresia(hogar_id, usuario_id, invitacion.get("rol") or "miembro")
        self.store.update(
            "invitaciones", invitacion["id"], {"usos": str(int(invitacion.get("usos") or 0) + 1)}
        )
        self.store.update("usuarios", usuario_id, {"hogar_activo": hogar_id})
        self._auditar(hogar_id, usuario_id, "miembro_unido", "")
        return self.obtener_hogar(usuario_id, hogar_id)

    def cambiar_rol(self, hogar_id: str, actor_id: str, usuario_id: str, rol: str) -> None:
        rol_actor = self.exigir(hogar_id, actor_id, "admin")
        if rol not in ("admin", "miembro"):
            raise ErrorNegocio("Rol inválido.")
        if usuario_id == actor_id and rol_actor == "propietario":
            raise ErrorNegocio("No podés cambiarte el rol a vos mismo.")
        actual = self.rol_en(hogar_id, usuario_id)
        if not actual:
            raise NoEncontrado("Esa persona no pertenece al hogar.")
        if actual == "propietario":
            raise ErrorNegocio("El rol de propietario no se puede modificar desde acá.")
        for fila in self.store.filtrar("miembros", hogar_id=hogar_id, usuario_id=usuario_id):
            self.store.update("miembros", fila["id"], {"rol": rol})
        self._auditar(hogar_id, actor_id, "rol_cambiado", f"{usuario_id}:{rol}")

    def quitar_miembro(self, hogar_id: str, actor_id: str, usuario_id: str) -> None:
        self.exigir(hogar_id, actor_id, "admin")
        actual = self.rol_en(hogar_id, usuario_id)
        if not actual:
            raise NoEncontrado("Esa persona no pertenece al hogar.")
        if actual == "propietario":
            raise ErrorNegocio("No se puede quitar a quien es propietario del hogar.")
        self._quitar_membresia(hogar_id, usuario_id)
        self._auditar(hogar_id, actor_id, "miembro_quitado", usuario_id)

    def salir_del_hogar(self, hogar_id: str, usuario_id: str) -> None:
        rol = self.exigir(hogar_id, usuario_id, "miembro")
        if rol == "propietario":
            if len(self._miembros_activos(hogar_id)) > 1:
                raise ErrorNegocio(
                    "Sos propietario/a: transferí la propiedad a otra persona antes de salir."
                )
            raise ErrorNegocio("Sos la única persona del hogar; podés eliminarlo desde Ajustes.")
        self._quitar_membresia(hogar_id, usuario_id)
        self._auditar(hogar_id, usuario_id, "miembro_salio", "")

    def transferir_propiedad(self, hogar_id: str, actor_id: str, usuario_id: str) -> None:
        self.exigir(hogar_id, actor_id, "propietario")
        if not self.rol_en(hogar_id, usuario_id):
            raise NoEncontrado("Esa persona no pertenece al hogar.")
        for fila in self.store.filtrar("miembros", hogar_id=hogar_id):
            if (fila.get("estado") or "activo").lower() != "activo":
                continue
            nuevo = "propietario" if fila["usuario_id"] == usuario_id else (
                "admin" if fila["usuario_id"] == actor_id else (fila.get("rol") or "miembro")
            )
            self.store.update("miembros", fila["id"], {"rol": nuevo})
        self._auditar(hogar_id, actor_id, "propiedad_transferida", usuario_id)

    def eliminar_hogar(self, hogar_id: str, usuario_id: str, confirmacion: str) -> None:
        self.exigir(hogar_id, usuario_id, "propietario")
        hogar = self.store.uno("hogares", hogar_id)
        esperado = (hogar or {}).get("nombre", "")
        if (confirmacion or "").strip() != esperado:
            raise ErrorNegocio("Escribí el nombre exacto del hogar para confirmar.")
        for tabla in ("gastos", "compras", "pagos", "invitaciones", "miembros", "eventos"):
            self.store.borrar_donde(tabla, hogar_id=hogar_id)
        self.store.delete("hogares", hogar_id)

    # ------------------------------------------------------------------ #
    # Gastos
    # ------------------------------------------------------------------ #
    def agregar_gasto(
        self,
        hogar_id: str,
        usuario_id: str,
        concepto: str,
        monto: Any,
        categoria: str,
        pagado_por: str,
        participantes: Iterable[str] | None = None,
        fecha: Any = None,
        comprobante: str = "",
    ) -> dict[str, Any]:
        self.exigir(hogar_id, usuario_id, "miembro")
        hogar = self.store.uno("hogares", hogar_id)
        plan = plans.normalizar_plan(hogar.get("plan"))

        concepto = _limpiar(concepto, MAX_CONCEPTO)
        if len(concepto) < 2:
            raise ErrorNegocio("Describí el gasto con al menos 2 caracteres.")
        valor = _validar_monto(monto)
        categoria = categoria if categoria in CATEGORIAS else "Otros"

        miembros_ids = {m["usuario_id"] for m in self.miembros(hogar_id)}
        if pagado_por not in miembros_ids:
            raise ErrorNegocio("Quien pagó tiene que ser miembro del hogar.")
        elegidos = [p for p in (participantes or miembros_ids) if p in miembros_ids]
        if not elegidos:
            raise ErrorNegocio("Elegí al menos una persona entre la que se divide el gasto.")

        mes = clave_mes(parsear_fecha(fecha) if fecha else hoy())
        if not plans.permite(plan, "gastos_mes", self._gastos_del_mes(hogar_id, mes)):
            raise LimiteAlcanzado(
                f"El plan {plans.etiqueta(plan)} permite {plans.texto_limite(plan, 'gastos_mes')} "
                "gastos por mes. Pasate a Pro para seguir cargando.",
                plan=plan,
            )

        division = balances.repartir(valor, elegidos)
        fila = self.store.insert(
            "gastos",
            {
                "id": nuevo_id(),
                "hogar_id": hogar_id,
                "fecha": fecha_iso(fecha) or hoy().isoformat(),
                "concepto": concepto,
                "monto": monto_texto(valor),
                "categoria": categoria,
                "pagado_por": pagado_por,
                "division": balances.division_json(division),
                "comprobante": comprobante or "",
                "creado_por": usuario_id,
                "creado_en": iso(),
                "estado": "activo",
            },
        )
        self._auditar(hogar_id, usuario_id, "gasto_agregado", f"{concepto}:{valor}")
        return self._gasto_norm(fila)

    def _gastos_del_mes(self, hogar_id: str, mes: str) -> int:
        desde, hasta = periodo(mes)
        total = 0
        for fila in self.store.filtrar("gastos", hogar_id=hogar_id):
            if (fila.get("estado") or "activo") == "anulado":
                continue
            try:
                fecha = parsear_fecha(fila.get("fecha", ""))
            except ValueError:
                continue
            if desde <= fecha <= hasta:
                total += 1
        return total

    def _gasto_norm(self, fila: Mapping[str, Any]) -> dict[str, Any]:
        datos = dict(fila)
        datos["monto"] = redondear(datos.get("monto", 0))
        try:
            datos["fecha_dt"] = parsear_fecha(datos.get("fecha", ""))
        except ValueError:
            datos["fecha_dt"] = hoy()
        datos["division_detalle"] = balances.normalizar_division(datos.get("division"))
        datos["participantes"] = list(datos["division_detalle"].keys())
        datos["anulado"] = (datos.get("estado") or "activo").lower() == "anulado"
        return datos

    def gastos(
        self,
        hogar_id: str,
        usuario_id: str,
        desde: Any = None,
        hasta: Any = None,
        categoria: str | None = None,
        pagado_por: str | None = None,
        texto: str = "",
        incluir_anulados: bool = False,
    ) -> list[dict[str, Any]]:
        self.exigir(hogar_id, usuario_id, "miembro")
        desde_d = parsear_fecha(desde) if desde else None
        hasta_d = parsear_fecha(hasta) if hasta else None
        buscado = _slug(texto)
        nombres = self.nombres(hogar_id)
        salida: list[dict[str, Any]] = []
        for fila in self.store.filtrar("gastos", hogar_id=hogar_id):
            gasto = self._gasto_norm(fila)
            if gasto["anulado"] and not incluir_anulados:
                continue
            if desde_d and gasto["fecha_dt"] < desde_d:
                continue
            if hasta_d and gasto["fecha_dt"] > hasta_d:
                continue
            if categoria and gasto.get("categoria") != categoria:
                continue
            if pagado_por and gasto.get("pagado_por") != pagado_por:
                continue
            if buscado and buscado not in _slug(gasto.get("concepto", "")):
                continue
            gasto["pagado_por_nombre"] = nombres.get(gasto.get("pagado_por", ""), "—")
            gasto["participantes"] = list(gasto["division_detalle"].keys())
            gasto["comprobante_url"] = gasto.get("comprobante", "")
            salida.append(gasto)
        salida.sort(key=lambda g: (g["fecha_dt"], g.get("creado_en", "")), reverse=True)
        return salida

    def gasto(self, hogar_id: str, usuario_id: str, gasto_id: str) -> dict[str, Any]:
        self.exigir(hogar_id, usuario_id, "miembro")
        fila = self.store.uno("gastos", gasto_id)
        if not fila or fila.get("hogar_id") != hogar_id:
            raise NoEncontrado("Ese gasto no existe.")
        return self._gasto_norm(fila)

    def editar_gasto(
        self, hogar_id: str, usuario_id: str, gasto_id: str, **cambios: Any
    ) -> dict[str, Any]:
        rol = self.exigir(hogar_id, usuario_id, "miembro")
        gasto = self.gasto(hogar_id, usuario_id, gasto_id)
        if _nivel(rol) < _nivel("admin") and gasto.get("creado_por") != usuario_id:
            raise NoAutorizado("Sólo quien lo cargó, un admin o el propietario pueden editarlo.")

        campos: dict[str, str] = {}
        if "concepto" in cambios:
            concepto = _limpiar(cambios["concepto"], MAX_CONCEPTO)
            if len(concepto) < 2:
                raise ErrorNegocio("El detalle es demasiado corto.")
            campos["concepto"] = concepto
        if "monto" in cambios:
            valor = _validar_monto(cambios["monto"])
            participantes = cambios.get("participantes") or gasto["participantes"]
            campos["monto"] = monto_texto(valor)
            campos["division"] = balances.division_json(balances.repartir(valor, participantes))
        if "categoria" in cambios:
            campos["categoria"] = (
                cambios["categoria"] if cambios["categoria"] in CATEGORIAS else gasto["categoria"]
            )
        if "pagado_por" in cambios:
            if cambios["pagado_por"] not in {m["usuario_id"] for m in self.miembros(hogar_id)}:
                raise ErrorNegocio("Quien pagó tiene que ser miembro del hogar.")
            campos["pagado_por"] = cambios["pagado_por"]
        if "fecha" in cambios and cambios["fecha"]:
            campos["fecha"] = fecha_iso(cambios["fecha"]) or gasto["fecha"]
        if "participantes" in cambios and cambios["participantes"]:
            elegidos = [
                p for p in cambios["participantes"]
                if p in {m["usuario_id"] for m in self.miembros(hogar_id)}
            ]
            if not elegidos:
                raise ErrorNegocio("Tiene que participar al menos una persona.")
            if "monto" not in campos:
                campos["division"] = balances.division_json(
                    balances.repartir(gasto["monto"], elegidos)
                )
        if cambios.get("comprobante") is not None and "comprobante" in cambios:
            campos["comprobante"] = str(cambios["comprobante"])

        if not campos:
            return gasto
        self.store.update("gastos", gasto_id, campos)
        self._auditar(hogar_id, usuario_id, "gasto_editado", gasto_id)
        return self.gasto(hogar_id, usuario_id, gasto_id)

    def anular_gasto(self, hogar_id: str, usuario_id: str, gasto_id: str) -> None:
        rol = self.exigir(hogar_id, usuario_id, "miembro")
        gasto = self.gasto(hogar_id, usuario_id, gasto_id)
        if _nivel(rol) < _nivel("admin") and gasto.get("creado_por") != usuario_id:
            raise NoAutorizado("Sólo quien lo cargó, un admin o el propietario pueden eliminarlo.")
        self.store.update("gastos", gasto_id, {"estado": "anulado"})
        self._auditar(hogar_id, usuario_id, "gasto_anulado", gasto_id)

    # ------------------------------------------------------------------ #
    # Compras
    # ------------------------------------------------------------------ #
    def agregar_compra(self, hogar_id: str, usuario_id: str, texto: str) -> dict[str, Any]:
        self.exigir(hogar_id, usuario_id, "miembro")
        limpio = _limpiar(texto, MAX_TEXTO_COMPRA)
        if len(limpio) < 2:
            raise ErrorNegocio("Escribí qué hace falta comprar.")
        fila = self.store.insert(
            "compras",
            {
                "id": nuevo_id(),
                "hogar_id": hogar_id,
                "texto": limpio,
                "estado": "pendiente",
                "anotado_por": usuario_id,
                "fecha": hoy().isoformat(),
                "comprado_por": "",
                "comprado_en": "",
            },
        )
        return dict(fila)

    def compras(
        self, hogar_id: str, usuario_id: str, incluir_compradas: bool = False
    ) -> list[dict[str, Any]]:
        self.exigir(hogar_id, usuario_id, "miembro")
        nombres = self.nombres(hogar_id)
        salida = []
        for fila in self.store.filtrar("compras", hogar_id=hogar_id):
            comprada = (fila.get("estado") or "").lower() == "comprado"
            if comprada and not incluir_compradas:
                continue
            datos = dict(fila)
            datos["comprada"] = comprada
            datos["anotado_por_nombre"] = nombres.get(fila.get("anotado_por", ""), "—")
            datos["comprado_por_nombre"] = nombres.get(fila.get("comprado_por", ""), "")
            salida.append(datos)
        salida.sort(key=lambda c: (c.get("comprada", False), c.get("fecha", ""), c.get("texto", "")))
        return salida

    def cambiar_estado_compra(
        self, hogar_id: str, usuario_id: str, compra_id: str, comprada: bool
    ) -> None:
        self.exigir(hogar_id, usuario_id, "miembro")
        fila = self.store.uno("compras", compra_id)
        if not fila or fila.get("hogar_id") != hogar_id:
            raise NoEncontrado("Ese ítem no existe.")
        self.store.update(
            "compras",
            compra_id,
            {
                "estado": "comprado" if comprada else "pendiente",
                "comprado_por": usuario_id if comprada else "",
                "comprado_en": iso() if comprada else "",
            },
        )

    def borrar_compra(self, hogar_id: str, usuario_id: str, compra_id: str) -> None:
        self.exigir(hogar_id, usuario_id, "miembro")
        fila = self.store.uno("compras", compra_id)
        if not fila or fila.get("hogar_id") != hogar_id:
            raise NoEncontrado("Ese ítem no existe.")
        self.store.delete("compras", compra_id)

    def limpiar_compradas(self, hogar_id: str, usuario_id: str) -> int:
        self.exigir(hogar_id, usuario_id, "miembro")
        return self.store.borrar_donde("compras", hogar_id=hogar_id, estado="comprado")

    # ------------------------------------------------------------------ #
    # Pagos (transferencias entre miembros)
    # ------------------------------------------------------------------ #
    def registrar_pago(
        self,
        hogar_id: str,
        usuario_id: str,
        de_usuario: str,
        a_usuario: str,
        monto: Any,
        fecha: Any = None,
        nota: str = "",
    ) -> dict[str, Any]:
        self.exigir(hogar_id, usuario_id, "miembro")
        miembros = {m["usuario_id"] for m in self.miembros(hogar_id)}
        if de_usuario not in miembros or a_usuario not in miembros:
            raise ErrorNegocio("Ambas personas tienen que ser miembros del hogar.")
        if de_usuario == a_usuario:
            raise ErrorNegocio("Una persona no puede pagarse a sí misma.")
        valor = _validar_monto(monto)
        fila = self.store.insert(
            "pagos",
            {
                "id": nuevo_id(),
                "hogar_id": hogar_id,
                "de_usuario": de_usuario,
                "a_usuario": a_usuario,
                "monto": monto_texto(valor),
                "fecha": fecha_iso(fecha) or hoy().isoformat(),
                "nota": _limpiar(nota, MAX_NOTA),
                "creado_por": usuario_id,
                "creado_en": iso(),
            },
        )
        self._auditar(hogar_id, usuario_id, "pago_registrado", f"{de_usuario}>{a_usuario}:{valor}")
        return dict(fila)

    def pagos(self, hogar_id: str, usuario_id: str, desde: Any = None, hasta: Any = None) -> list[dict[str, Any]]:
        self.exigir(hogar_id, usuario_id, "miembro")
        desde_d = parsear_fecha(desde) if desde else None
        hasta_d = parsear_fecha(hasta) if hasta else None
        nombres = self.nombres(hogar_id)
        salida = []
        for fila in self.store.filtrar("pagos", hogar_id=hogar_id):
            try:
                fecha_d = parsear_fecha(fila.get("fecha", ""))
            except ValueError:
                continue
            if desde_d and fecha_d < desde_d:
                continue
            if hasta_d and fecha_d > hasta_d:
                continue
            datos = dict(fila)
            datos["monto"] = redondear(datos.get("monto", 0))
            datos["fecha_dt"] = fecha_d
            datos["de_nombre"] = nombres.get(fila.get("de_usuario", ""), "—")
            datos["a_nombre"] = nombres.get(fila.get("a_usuario", ""), "—")
            salida.append(datos)
        salida.sort(key=lambda p: (p["fecha_dt"], p.get("creado_en", "")), reverse=True)
        return salida

    def borrar_pago(self, hogar_id: str, usuario_id: str, pago_id: str) -> None:
        rol = self.exigir(hogar_id, usuario_id, "miembro")
        fila = self.store.uno("pagos", pago_id)
        if not fila or fila.get("hogar_id") != hogar_id:
            raise NoEncontrado("Ese pago no existe.")
        if _nivel(rol) < _nivel("admin") and fila.get("creado_por") != usuario_id:
            raise NoAutorizado("Sólo quien lo registró o un admin pueden borrarlo.")
        self.store.delete("pagos", pago_id)
        self._auditar(hogar_id, usuario_id, "pago_borrado", pago_id)

    # ------------------------------------------------------------------ #
    # Resumen
    # ------------------------------------------------------------------ #
    def resumen(
        self,
        hogar_id: str,
        usuario_id: str,
        mes: str | None = None,
        desde: Any = None,
        hasta: Any = None,
        historico: bool = False,
    ) -> dict[str, Any]:
        """Números del período: totales, categorías, saldos y transferencias."""
        hogar = self.obtener_hogar(usuario_id, hogar_id)
        plan = hogar["plan"]

        if historico:
            desde_d, hasta_d = date(2000, 1, 1), hoy()
        elif desde or hasta:
            desde_d = parsear_fecha(desde) if desde else date(2000, 1, 1)
            hasta_d = parsear_fecha(hasta) if hasta else hoy()
        else:
            clave = mes or clave_mes()
            desde_d, hasta_d = periodo(clave)

        recortado = False
        original = desde_d
        tope_meses = plans.meses_visibles(plan, self.config)
        if tope_meses is not None and not historico:
            limite = date(hoy().year, hoy().month, 1)
            for _ in range(max(tope_meses - 1, 0)):
                limite = (limite - timedelta(days=1)).replace(day=1)
            if desde_d < limite:
                desde_d, recortado = limite, True

        gastos = self.gastos(hogar_id, usuario_id, desde_d, hasta_d)
        pagos = self.pagos(hogar_id, usuario_id, desde_d, hasta_d)
        miembros = self.miembros(hogar_id)
        ids = [m["usuario_id"] for m in miembros]
        nombres = {m["usuario_id"]: m["nombre"] for m in miembros}

        saldos = balances.saldos(gastos, pagos, ids)
        por_categoria: dict[str, Decimal] = {}
        for gasto in gastos:
            categoria = gasto.get("categoria") or "Otros"
            por_categoria[categoria] = por_categoria.get(categoria, Decimal("0")) + gasto["monto"]
        por_categoria = dict(
            sorted(por_categoria.items(), key=lambda kv: kv[1], reverse=True)
        )

        movimientos = len(gastos) + len(pagos)
        return {
            "hogar": hogar,
            "desde": desde_d,
            "hasta": hasta_d,
            "desde_original": original,
            "recortado": recortado,
            "mes": clave_mes(desde_d) if not historico else "",
            "gastos": gastos,
            "pagos": pagos,
            "cantidad": len(gastos),
            "total": redondear(sum((g["monto"] for g in gastos), Decimal("0"))),
            "por_categoria": por_categoria,
            "por_persona": {
                uid: redondear(saldos.get(uid, {}).get("pagado", Decimal("0"))) for uid in ids
            },
            "saldos": saldos,
            "nombres": nombres,
            "transferencias": balances.sugerir_transferencias(
                {uid: datos["neto"] for uid, datos in saldos.items()}, nombres
            ),
            "totales": balances.totales(saldos),
            "movimientos": movimientos,
            "comprobantes": sum(1 for g in gastos if g.get("comprobante")),
            "compras_pendientes": len(self.compras(hogar_id, usuario_id)),
            "miembros": miembros,
        }

    def meses_con_datos(self, hogar_id: str, usuario_id: str) -> list[str]:
        self.exigir(hogar_id, usuario_id, "miembro")
        claves = set()
        for fila in self.store.filtrar("gastos", hogar_id=hogar_id):
            try:
                claves.add(clave_mes(parsear_fecha(fila.get("fecha", ""))))
            except ValueError:
                continue
        claves.add(clave_mes())
        return sorted(claves, reverse=True)

    # ------------------------------------------------------------------ #
    # Exportación y respaldo
    # ------------------------------------------------------------------ #
    def exportar_csv(
        self, hogar_id: str, usuario_id: str, desde: Any = None, hasta: Any = None
    ) -> str:
        hogar = self.obtener_hogar(usuario_id, hogar_id)
        gastos = self.gastos(hogar_id, usuario_id, desde, hasta, incluir_anulados=True)
        buffer = io.StringIO()
        escritor = csv.writer(buffer, lineterminator="\n")
        escritor.writerow(
            [
                "fecha", "quien", "concepto", "monto", "categoria",
                "comprobante", "participantes", "estado",
            ]
        )
        for gasto in sorted(gastos, key=lambda g: g["fecha_dt"]):
            escritor.writerow(
                [
                    gasto["fecha_dt"].strftime("%d/%m/%Y"),
                    gasto.get("pagado_por_nombre", ""),
                    gasto.get("concepto", ""),
                    f"{gasto['monto']:.2f}",
                    gasto.get("categoria", ""),
                    "si" if gasto.get("comprobante") else "no",
                    ";".join(
                        self.nombres(hogar_id).get(p, p) for p in gasto["participantes"]
                    ),
                    gasto.get("estado", "activo"),
                ]
            )
        return buffer.getvalue()

    def exportar_json(self, hogar_id: str, usuario_id: str) -> str:
        """Respaldo completo del hogar (portabilidad de datos)."""
        self.obtener_hogar(usuario_id, hogar_id)
        datos = {
            "version": 2,
            "generado_en": iso(),
            "hogar": self.store.uno("hogares", hogar_id),
            "miembros": self.miembros(hogar_id),
            "gastos": [
                {k: v for k, v in g.items() if k != "fecha_dt"}
                for g in self.gastos(hogar_id, usuario_id, incluir_anulados=True)
            ],
            "compras": self.compras(hogar_id, usuario_id, incluir_compradas=True),
            "pagos": self.pagos(hogar_id, usuario_id),
        }
        return json.dumps(datos, ensure_ascii=False, indent=2, default=str)

    # ------------------------------------------------------------------ #
    # Administración de plataforma
    # ------------------------------------------------------------------ #
    def plataforma_resumen(self) -> dict[str, Any]:
        usuarios = [self._usuario_norm(u) for u in self.store.all("usuarios")]
        hogares = self.store.all("hogares")
        gastos = self.store.all("gastos")
        ahora_dt = ahora()
        hace_30 = ahora_dt - timedelta(days=30)
        activos_30 = 0
        for usuario in usuarios:
            login = usuario.get("ultimo_login", "")
            if login and desde_iso(login) >= hace_30:
                activos_30 += 1
        pro = sum(1 for h in hogares if plans.normalizar_plan(h.get("plan")) == plans.PRO)
        mrr = self.config.precio_mensual_num * pro
        return {
            "usuarios": len(usuarios),            "usuarios_activos_30": activos_30,
            "hogares": len(hogares),
            "hogares_pro": pro,
            "hogares_gratis": len(hogares) - pro,
            "gastos": len(gastos),
            "mrr": redondear(mrr),
            "arr": redondear(mrr * 12),
            "lista_usuarios": usuarios,
            "lista_hogares": hogares,
        }

    def plataforma_usuarios(self) -> list[dict[str, Any]]:
        usuarios = [self._usuario_norm(u) for u in self.store.all("usuarios")]
        por_usuario: dict[str, list[str]] = {}
        for fila in self.store.all("miembros"):
            if (fila.get("estado") or "activo").lower() != "activo":
                continue
            hogar = self.store.uno("hogares", fila["hogar_id"])
            if hogar:
                por_usuario.setdefault(fila["usuario_id"], []).append(hogar.get("nombre", ""))
        for usuario in usuarios:
            usuario["hogares"] = ", ".join(por_usuario.get(usuario["id"], []))
        usuarios.sort(key=lambda u: u.get("creado_en", ""), reverse=True)
        return usuarios

    def plataforma_hogares(self) -> list[dict[str, Any]]:
        salida = []
        for hogar in self.store.all("hogares"):
            datos = dict(hogar)
            datos["plan"] = plans.normalizar_plan(hogar.get("plan"))
            datos["miembros"] = len(self._miembros_activos(hogar["id"]))
            datos["gastos"] = sum(
                1
                for g in self.store.filtrar("gastos", hogar_id=hogar["id"])
                if (g.get("estado") or "activo") != "anulado"
            )
            datos["propietario"] = next(
                (
                    (self.store.uno("usuarios", m["usuario_id"]) or {}).get("email", "")
                    for m in self._miembros_activos(hogar["id"])
                    if (m.get("rol") or "") == "propietario"
                ),
                "",
            )
            salida.append(datos)
        salida.sort(key=lambda h: h.get("creado_en", ""), reverse=True)
        return salida

    def alternar_usuario(self, usuario_id: str, activo: bool) -> None:
        self.store.update("usuarios", usuario_id, {"activo": "Si" if activo else "No"})
        if not activo:
            auth.revocar_todas(self.store, usuario_id)

    # ------------------------------------------------------------------ #
    # Auditoría
    # ------------------------------------------------------------------ #
    def _auditar(self, hogar_id: str, usuario_id: str, accion: str, detalle: str) -> None:
        self.store.insert(
            "eventos",
            {
                "id": nuevo_id(),
                "hogar_id": hogar_id,
                "usuario_id": usuario_id,
                "accion": accion,
                "detalle": detalle,
                "creado_en": iso(),
            },
        )

    def eventos(self, hogar_id: str, usuario_id: str, limite: int = 40) -> list[dict[str, Any]]:
        self.exigir(hogar_id, usuario_id, "admin")
        filas = self.store.filtrar("eventos", hogar_id=hogar_id)
        filas.sort(key=lambda e: e.get("creado_en", ""), reverse=True)
        return [dict(f) for f in filas[:limite]]
