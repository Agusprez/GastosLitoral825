"""Doble de prueba de pandas (sólo para los smoke tests de las vistas).

Streamlit recibe el `DataFrame` tal cual, así que para probar que la vista no se
rompe alcanza con una estructura mínima. La lógica de los datos se prueba en
`test_core.py` y `test_controladores.py` contra listas de diccionarios reales.
"""

from __future__ import annotations

import sys
import types
from typing import Any, Iterable


class DataFrame:
    def __init__(self, data: Any = None, columns: Iterable[str] | None = None, **kwargs: Any) -> None:
        if data is None:
            self.filas: list[Any] = []
        elif isinstance(data, (list, tuple)):
            self.filas = list(data)
        else:
            self.filas = list(data)
        self.columns = list(columns) if columns else []

    # API mínima usada por la app
    @property
    def empty(self) -> bool:
        return len(self.filas) == 0

    def __len__(self) -> int:
        return len(self.filas)

    def rename(self, columns: dict[str, str] | None = None, **kwargs: Any) -> "DataFrame":
        return self

    def head(self, n: int = 5) -> "DataFrame":
        return self

    def to_dict(self, orient: str = "records") -> list[Any]:
        return list(self.filas)


def instalar() -> types.ModuleType:
    modulo = sys.modules.get("pandas")
    if modulo is not None and getattr(modulo, "es_falso", False):
        return modulo
    modulo = types.ModuleType("pandas")
    modulo.es_falso = True
    modulo.DataFrame = DataFrame
    sys.modules["pandas"] = modulo
    return modulo
