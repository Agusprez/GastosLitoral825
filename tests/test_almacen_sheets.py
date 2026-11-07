"""Tests de `SheetsStore` contra un libro falso.

El caso que motivó estos tests: la app creaba pestañas con el nombre de la tabla
(`gastos`) en vez de usar el prefijo (`cc_gastos`) y Google rechazaba la creación
porque la v1 ya tenía una pestaña `Gastos` (los nombres son únicos sin distinguir
mayúsculas).
"""

from __future__ import annotations

import unittest
from unittest import mock

from cuentasclaras.modelos import almacen
from cuentasclaras.modelos.almacen import TABLAS, ErrorAlmacen, SheetsStore
from tests.hoja_falsa import LibroFalso


def crear_store(libro: LibroFalso, prefijo: str = "cc_") -> SheetsStore:
    return SheetsStore("https://planilla.falsa", {}, prefijo=prefijo, libro=libro)


class TestPrefijo(unittest.TestCase):
    def test_crea_pestanas_con_prefijo(self):
        libro = LibroFalso()
        store = crear_store(libro)
        store.insert("usuarios", {"email": "a@x.com", "nombre": "Ana"})
        store.insert("gastos", {"concepto": "Luz", "monto": "1000"})
        self.assertEqual(libro.titulos(), ["cc_usuarios", "cc_gastos"])
        self.assertEqual(libro.hoja("cc_usuarios").filas[0], TABLAS["usuarios"])

    def test_no_pisa_la_pestana_v1_de_gastos(self):
        libro = LibroFalso()
        v1 = libro.agregar_hoja(
            "Gastos",
            [
                ["Fecha", "Quien", "Concepto", "Monto", "Categoria", "Comprobante"],
                ["01/10/2026", "Agustin", "Compra Coto", "48500", "Supermercado", ""],
            ],
        )
        antes = [list(f) for f in v1.filas]

        store = crear_store(libro)
        store.insert("gastos", {"concepto": "Internet", "monto": "21500"})

        self.assertIn("cc_gastos", libro.titulos())
        self.assertEqual(libro.hoja("Gastos").filas, antes)  # intacta
        # Y se puede leer/escribir normalmente en la pestaña nueva.
        store.insert("gastos", {"concepto": "Gas", "monto": "8000"})
        self.assertEqual(len(store.all("gastos")), 2)

    def test_lista_completa_con_pestana_v1_presente(self):
        """El escenario real: planilla vieja + todas las tablas nuevas."""
        libro = LibroFalso()
        libro.agregar_hoja("Gastos", [["Fecha", "Quien"], ["01/10/2026", "Agustin"]])
        libro.agregar_hoja("Lista_Compras", [["Elemento", "Quién Anotó"]])
        store = crear_store(libro)
        for tabla in TABLAS:
            self.assertEqual(store.all(tabla), [])
        self.assertNotIn("Gastos", [t for t in libro.titulos() if t.startswith("cc_")])
        self.assertEqual(len(libro.titulos()), 2 + len(TABLAS))


class TestAdopcion(unittest.TestCase):
    def test_renombra_pestana_sin_prefijo_con_nuestro_esquema(self):
        libro = LibroFalso()
        libro.agregar_hoja(
            "usuarios",
            [
                TABLAS["usuarios"],
                ["u1", "a@x.com", "Ana", "hash", "usuario", "Si", "", "", "0", "", "", ""],
            ],
        )
        store = crear_store(libro)
        filas = store.all("usuarios")
        self.assertEqual([f["email"] for f in filas], ["a@x.com"])
        self.assertIn("cc_usuarios", libro.titulos())
        self.assertNotIn("usuarios", libro.titulos())

    def test_no_adopta_una_pestana_con_otro_formato(self):
        libro = LibroFalso()
        libro.agregar_hoja("usuarios", [["legacy_col", "otra"], ["x", "y"]])
        store = crear_store(libro)
        self.assertEqual(store.all("usuarios"), [])
        self.assertIn("cc_usuarios", libro.titulos())
        # La vieja sigue como estaba.
        self.assertEqual(libro.hoja("usuarios").filas[0], ["legacy_col", "otra"])


class TestEncabezados(unittest.TestCase):
    def test_completa_columnas_nuevas(self):
        libro = LibroFalso()
        libro.agregar_hoja(
            "cc_usuarios",
            [["id", "email"], ["u1", "a@x.com"]],
        )
        store = crear_store(libro)
        store.insert("usuarios", {"email": "b@x.com", "nombre": "Bruno"})
        self.assertEqual(libro.hoja("cc_usuarios").filas[0], TABLAS["usuarios"])
        filas = store.all("usuarios")
        self.assertEqual(len(filas), 2)
        self.assertEqual({f["email"] for f in filas}, {"a@x.com", "b@x.com"})

    def test_encabezado_ajeno_falla_claro(self):
        libro = LibroFalso()
        libro.agregar_hoja("cc_usuarios", [["algo", "distinto"]])
        store = crear_store(libro)
        with self.assertRaises(ErrorAlmacen) as contexto:
            store.all("usuarios")
        self.assertIn("encabezado", str(contexto.exception))

    def test_prefijo_vacio_choca_con_la_v1(self):
        libro = LibroFalso()
        libro.agregar_hoja(
            "Gastos", [["Fecha", "Quien", "Concepto", "Monto", "Categoria", "Comprobante"]]
        )
        store = crear_store(libro, prefijo="")
        with self.assertRaises(ErrorAlmacen) as contexto:
            store.insert("gastos", {"concepto": "Luz", "monto": "1"})
        mensaje = str(contexto.exception)
        self.assertIn("otro formato", mensaje)
        self.assertIn("prefijo_hojas", mensaje)


class TestCrud(unittest.TestCase):
    def setUp(self) -> None:
        self.libro = LibroFalso()
        self.store = crear_store(self.libro)

    def test_alta_lectura_edicion_baja(self):
        fila = self.store.insert("compras", {"texto": "Leche", "hogar_id": "h1"})
        self.assertEqual(len(self.store.all("compras")), 1)

        self.store.update("compras", fila["id"], {"estado": "comprado"})
        actualizada = self.store.uno("compras", fila["id"])
        self.assertEqual(actualizada["estado"], "comprado")
        self.assertEqual(actualizada["texto"], "Leche")

        self.store.delete("compras", fila["id"])
        self.assertEqual(self.store.all("compras"), [])

    def test_cache_se_invalida_al_escribir(self):
        self.assertEqual(self.store.all("eventos"), [])
        self.store.insert("eventos", {"accion": "prueba"})
        self.assertEqual(len(self.store.all("eventos")), 1)

    def test_numero_de_fila_con_prefijo(self):
        fila = self.store.insert("hogares", {"nombre": "Casa"})
        self.store.insert("hogares", {"nombre": "Depto"})
        self.store.update("hogares", fila["id"], {"nombre": "Casa Grande"})
        self.assertEqual(
            [h["nombre"] for h in self.store.all("hogares")],
            ["Casa Grande", "Depto"],
        )


class TestCuota(unittest.TestCase):
    """El límite de lecturas de Google no debe romper la app."""

    def test_reintenta_cuando_google_limita(self):
        estado = {"intentos": 0}

        def accion():
            estado["intentos"] += 1
            if estado["intentos"] < 3:
                raise RuntimeError(
                    "APIError: [429]: Quota exceeded for quota metric 'Read requests'"
                )
            return "ok"

        with mock.patch("time.sleep"):
            self.assertEqual(almacen._con_reintentos(accion, espera=0), "ok")
        self.assertEqual(estado["intentos"], 3)

    def test_mensaje_claro_si_sigue_limitado(self):
        def accion():
            raise RuntimeError("APIError: [429]: Quota exceeded")

        with mock.patch("time.sleep"):
            with self.assertRaises(almacen.ErrorAlmacen) as contexto:
                almacen._con_reintentos(accion, intentos=2, espera=0)
        self.assertIn("limitando", str(contexto.exception))
        self.assertIn("no se perdió ningún dato", str(contexto.exception))

    def test_otros_errores_no_se_reintentan(self):
        estado = {"intentos": 0}

        def accion():
            estado["intentos"] += 1
            raise RuntimeError("WorksheetNotFound")

        with self.assertRaises(RuntimeError):
            almacen._con_reintentos(accion, espera=0)
        self.assertEqual(estado["intentos"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
