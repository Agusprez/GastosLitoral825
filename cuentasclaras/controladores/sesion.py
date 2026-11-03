"""Controlador de sesión: login, registro, invitaciones y sesiones."""

from __future__ import annotations

from typing import Any

from ..modelos import autenticacion as auth
from ..modelos import planes
from ..modelos.configuracion import Config
from ..modelos.repositorio import ErrorNegocio, Repositorio
from .base import Controlador, Resultado


class ControladorSesion(Controlador):
    def iniciar(self, email: str, clave: str, recordar: bool = True) -> Resultado:
        if not email or not clave:
            return Resultado.error("Completá email y contraseña.")
        resultado = auth.autenticar(self.repo.store, email, clave)
        if not resultado.ok or not resultado.usuario:
            return Resultado.error(resultado.mensaje)
        usuario = resultado.usuario
        token = auth.crear_sesion(
            self.repo.store, usuario["id"], dias=auth.DIAS_SESION if recordar else 1
        )
        hogares = self.repo.hogares_de(usuario["id"])
        if hogares:
            auth.recordar_hogar(self.repo.store, token, hogares[0]["id"])
        return Resultado.exito(
            f"¡Hola de nuevo, {usuario.get('nombre', '')}!",
            {"usuario": usuario, "token": token, "hogares": hogares},
        )

    def registrar(
        self,
        nombre: str,
        email: str,
        clave: str,
        clave2: str,
        acepto: bool = True,
        codigo: str = "",
    ) -> Resultado:
        if clave != clave2:
            return Resultado.error("Las contraseñas no coinciden.")
        if not acepto:
            return Resultado.error("Tenés que aceptar los términos para crear la cuenta.")
        try:
            usuario = self.repo.crear_usuario(email, nombre, clave)
        except ErrorNegocio as exc:
            return Resultado.error(str(exc))

        aviso = ""
        if (codigo or "").strip():
            unido = self.unirse(usuario["id"], codigo)
            if not unido.ok:
                aviso = (
                    " La cuenta se creó, pero el código no se pudo usar: "
                    f"{unido.mensaje}"
                )
        token = auth.crear_sesion(self.repo.store, usuario["id"])
        hogares = self.repo.hogares_de(usuario["id"])
        if hogares:
            auth.recordar_hogar(self.repo.store, token, hogares[0]["id"])
        mensaje = f"¡Bienvenido/a, {usuario.get('nombre', '')}!{aviso}"
        return Resultado.exito(
            mensaje, {"usuario": usuario, "token": token, "hogares": hogares}
        )

    def unirse(self, usuario_id: str, codigo: str) -> Resultado:
        return self.correr(
            lambda: self.repo.unirse_por_codigo(usuario_id, codigo),
            "¡Te sumaste al hogar!",
        )

    def restaurar(self, token: str) -> Resultado:
        if not token:
            return Resultado.error("Sin sesión.")
        fila = auth.sesion_por_token(self.repo.store, token)
        if not fila:
            return Resultado.error("La sesión venció. Entrá de nuevo.")
        usuario = self.repo.usuario(fila["usuario_id"])
        if not usuario or not usuario.get("activo_booleano"):
            auth.revocar(self.repo.store, token)
            return Resultado.error("La cuenta está deshabilitada.")
        return Resultado.exito(
            "",
            {
                "usuario": usuario,
                "token": token,
                "hogar_activo": fila.get("hogar_activo", ""),
                "hogares": self.repo.hogares_de(usuario["id"]),
            },
        )

    def cerrar(self, token: str) -> None:
        auth.revocar(self.repo.store, token)

    def hogares(self, usuario_id: str) -> list[dict[str, Any]]:
        return self.repo.hogares_de(usuario_id)

    def elegir_hogar(self, token: str, hogar_id: str) -> None:
        auth.recordar_hogar(self.repo.store, token, hogar_id)

    def plan_de_la_cuenta(self, usuario_id: str) -> str:
        return self.repo.plan_efectivo(usuario_id)

    def limites(self, usuario_id: str) -> dict[str, Any]:
        return planes.limites(self.plan_de_la_cuenta(usuario_id))
