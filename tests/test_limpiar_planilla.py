"""Tests del limpiador de la planilla v1 (`tools/limpiar_planilla.py`)."""

from __future__ import annotations

import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cuentasclaras.modelos.migracion import leer_archivo
from tools import limpiar_planilla

FILAS = [
    {"fecha": "09/05/2026", "quien": "Agustin", "concepto": "Pizzas  ", "monto": "20000", "categoria": "Salidas", "comprobante": "Sin comprobante"},
    {"fecha": "10/05/2026", "quien": "Jorge", "concepto": "", "monto": "15300", "categoria": "Supermercado", "comprobante": ""},
    {"fecha": "11/05/2026", "quien": "Jorge", "concepto": "Cosa rara", "monto": "0", "categoria": "Supermercado", "comprobante": ""},
    {"fecha": "no-es-fecha", "quien": "Jorge", "concepto": "Rota", "monto": "100", "categoria": "Auto", "comprobante": ""},
    {"fecha": "12/05/2026", "quien": "Agustin", "concepto": "Algo", "monto": "1000", "categoria": "Cripto", "comprobante": "https://i.ibb.co/x.jpg"},
]


class TestLimpiar(unittest.TestCase):
    def test_recorta_y_completa(self):
        limpias, avisos = limpiar_planilla.limpiar(FILAS)
        self.assertEqual(len(limpias), 3)  # se omiten la de monto 0 y la fecha rota
        self.assertEqual(limpias[0]["Concepto"], "Pizzas")
        self.assertEqual(limpias[0]["Comprobante"], "")  # "Sin comprobante" se limpia
        self.assertEqual(limpias[1]["Concepto"], "Sin detalle")  # no tenía detalle
        self.assertEqual(limpias[2]["Categoria"], "Otros")  # categoría fuera de lista
        self.assertEqual(limpias[2]["Comprobante"], "https://i.ibb.co/x.jpg")
        self.assertEqual(len(avisos), 4)

    def test_totales(self):
        limpias, _ = limpiar_planilla.limpiar(FILAS)
        total = sum((Decimal(f["Monto"]) for f in limpias), Decimal("0"))
        self.assertEqual(total, Decimal("36300.00"))

    def test_archivo_ida_y_vuelta(self):
        limpias, _ = limpiar_planilla.limpiar(FILAS)
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "limpio.csv"
            limpiar_planilla.escribir(limpias, destino)
            with destino.open(encoding="utf-8", newline="") as archivo:
                filas = list(csv.DictReader(archivo))
            gastos, _ = leer_archivo("limpio.csv", destino.read_bytes())
        self.assertEqual(len(filas), 3)
        self.assertEqual(len(gastos), 3)
        self.assertEqual(gastos[0]["concepto"], "Pizzas")


if __name__ == "__main__":
    unittest.main(verbosity=2)
