"""Base de la capa de controladores.

Un controlador recibe las acciones de la vista, valida, delega en el modelo y
devuelve un `Resultado` listo para mostrar. La vista no decide nada de negocio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..modelos import archivos as medios_mod
from ..modelos.configuracion import Config
from ..modelos.repositorio import ErrorNegocio, NoAutorizado, Repositorio
from ..modelos.almacen import ErrorAlmacen


@dataclass
class Resultado:
    """Respuesta uniforme de cualquier acción del sistema."""

    ok: bool = True
    mensaje: str = ""
    tipo: str = "info"  # "exito" | "error" | "aviso" | "info"
    datos: Any = None

    @classmethod
    def exito(cls, mensaje: str = "Listo", datos: Any = None) -> "Resultado":
        return cls(True, mensaje, "exito", datos)

    @classmethod
    def aviso(cls, mensaje: str, datos: Any = None) -> "Resultado":
        return cls(True, mensaje, "aviso", datos)

    @classmethod
    def error(cls, mensaje: str) -> "Resultado":
        return cls(False, mensaje, "error", None)


class Controlador:
    """Controlador con el contexto de sesión (usuario y hogar activos)."""

    def __init__(
        self,
        repo: Repositorio,
        config: Config,
        medios: medios_mod.Medios | None = None,
        usuario: dict[str, Any] | None = None,
        hogar: dict[str, Any] | None = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self.medios = medios
        self.usuario = usuario or {}
        self.hogar = hogar or {}

    # --- contexto --------------------------------------------------------- #
    @property
    def usuario_id(self) -> str:
        return str(self.usuario.get("id") or "")

    @property
    def hogar_id(self) -> str:
        if not self.hogar.get("id"):
            raise ErrorNegocio("Elegí un hogar para continuar.")
        return str(self.hogar["id"])

    @property
    def rol(self) -> str:
        return str(self.hogar.get("rol") or "miembro")

    def es_admin_hogar(self) -> bool:
        return self.rol in ("propietario", "admin")

    # --- ejecución -------------------------------------------------------- #
    def correr(self, accion: Callable[[], Any], mensaje_ok: str = "Listo") -> Resultado:
        """Ejecuta una acción del modelo traduciendo errores a mensajes."""
        try:
            datos = accion()
        except NoAutorizado as exc:
            return Resultado.error(f"No tenés permiso: {exc}")
        except ErrorNegocio as exc:
            return Resultado.error(str(exc))
        except ErrorAlmacen as exc:
            return Resultado.error(
                "No pudimos guardar en el almacenamiento. "
                f"Detalle técnico: {exc}"
            )
        except Exception as exc:  # noqa: BLE001 - la vista nunca debe crashear
            return Resultado.error(
                "Ocurrió un error inesperado. Probá de nuevo en unos segundos. "
                f"(detalle: {exc})"
            )
        return Resultado.exito(mensaje_ok, datos)
