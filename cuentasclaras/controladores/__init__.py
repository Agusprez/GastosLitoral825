"""Capa de controladores (C de MVC).

Cada controlador expone casos de uso que devuelven un `Resultado` (ok/mensaje/
datos). Las vistas no contienen reglas de negocio: sólo dibujan widgets, llaman
al controlador correspondiente y muestran el resultado.
"""

from .admin import ControladorAdmin
from .base import Controlador, Resultado
from .compras import ControladorCompras
from .cuenta import ControladorCuenta
from .gastos import ControladorGastos
from .hogar import ControladorHogar
from .planes import ControladorPlanes
from .resumen import ControladorResumen
from .sesion import ControladorSesion

__all__ = [
    "Controlador",
    "Resultado",
    "ControladorAdmin",
    "ControladorCompras",
    "ControladorCuenta",
    "ControladorGastos",
    "ControladorHogar",
    "ControladorPlanes",
    "ControladorResumen",
    "ControladorSesion",
]
