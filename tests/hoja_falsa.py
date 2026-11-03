"""Doble de prueba de Google Sheets (lo mínimo que usa `SheetsStore`).

Reproduce lo importante del comportamiento real:

* los nombres de pestaña son únicos **sin distinguir mayúsculas** (por eso la v1
  con `Gastos` chocaba con una pestaña `gastos`),
* `append_row` agrega al final y `delete_rows` usa índices de 1,
* `update(range_name="A1", values=[...])` reemplaza la fila indicada.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


class APIError(Exception):
    """Equivale a `gspread.exceptions.APIError`."""


class HojaFalsa:
    def __init__(self, libro: "LibroFalso", titulo: str, filas: list[list[str]] | None = None) -> None:
        self.libro = libro
        self.title = titulo
        self.filas: list[list[str]] = [list(f) for f in (filas or [])]

    # --- lectura ---------------------------------------------------------- #
    def row_values(self, numero: int) -> list[str]:
        if 0 < numero <= len(self.filas):
            return list(self.filas[numero - 1])
        return []

    def get_all_values(self) -> list[list[str]]:
        return [list(f) for f in self.filas]

    def col_values(self, numero: int) -> list[str]:
        salida = []
        for fila in self.filas:
            if len(fila) >= numero:
                salida.append(str(fila[numero - 1]))
        return salida

    # --- escritura -------------------------------------------------------- #
    def append_row(self, fila: Iterable[Any], value_input_option: str | None = None) -> None:
        self.filas.append([str(c) for c in fila])

    def update(self, range_name: str, values: list[list[Any]], **kwargs: Any) -> None:
        numero = int(re.sub(r"\D", "", range_name) or "1")
        while len(self.filas) < numero:
            self.filas.append([])
        self.filas[numero - 1] = [str(c) for c in values[0]]

    def delete_rows(self, numero: int) -> None:
        if 0 < numero <= len(self.filas):
            del self.filas[numero - 1]

    def update_title(self, titulo: str) -> None:
        self.libro.renombrar(self, titulo)


class LibroFalso:
    def __init__(self, title: str = "Planilla de prueba") -> None:
        self.title = title
        self._hojas: list[HojaFalsa] = []

    # --- API que usa SheetsStore ------------------------------------------ #
    def worksheets(self) -> list[HojaFalsa]:
        return list(self._hojas)

    def add_worksheet(self, title: str, rows: int = 100, cols: int = 26) -> HojaFalsa:
        if any(hoja.title.lower() == title.lower() for hoja in self._hojas):
            # Mensaje calcado del que devuelve Google (fue el error en producción).
            raise APIError(
                f'Invalid requests[0].addSheet: A sheet with the name "{title}" '
                "already exists. Please enter another name."
            )
        hoja = HojaFalsa(self, title)
        self._hojas.append(hoja)
        return hoja

    def worksheet(self, titulo: str) -> HojaFalsa:
        for hoja in self._hojas:
            if hoja.title == titulo:
                return hoja
        raise APIError(f"WorksheetNotFound: {titulo}")

    def renombrar(self, hoja: HojaFalsa, titulo: str) -> None:
        if any(otra is not hoja and otra.title.lower() == titulo.lower() for otra in self._hojas):
            raise APIError(f'A sheet with the name "{titulo}" already exists.')
        hoja.title = titulo

    # --- utilidades para los tests ---------------------------------------- #
    def agregar_hoja(self, titulo: str, filas: list[list[str]] | None = None) -> HojaFalsa:
        hoja = HojaFalsa(self, titulo, filas)
        self._hojas.append(hoja)
        return hoja

    def titulos(self) -> list[str]:
        return [hoja.title for hoja in self._hojas]

    def hoja(self, titulo: str) -> HojaFalsa:
        for hoja in self._hojas:
            if hoja.title.lower() == titulo.lower():
                return hoja
        raise KeyError(titulo)
