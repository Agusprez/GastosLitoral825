"""Fábrica de persistencia: arma el almacén y le aplica el cifrado.

Se usa desde la capa de vista (y desde los scripts) para no repetir el armado:

    store, origen_clave = abrir_almacen(config)
"""

from __future__ import annotations

from . import cifrado as _cifrado
from .almacen import Store, abrir
from .configuracion import Config


def abrir_almacen(config: Config) -> tuple[Store, str]:
    """Devuelve el store listo para usar y de dónde salió la clave de cifrado.

    `origen` vacío significa que se está guardando SIN cifrar (modo planilla sin
    clave configurada), y la interfaz debe avisarlo.
    """
    base = abrir(config)
    return _cifrado.envolver(base, config)
