"""Tests de la importación de la planilla vieja (v1) desde la app."""

from __future__ import annotations

import unittest
from decimal import Decimal

from cuentasclaras.controladores.hogar import ControladorHogar
from cuentasclaras.modelos import migracion
from cuentasclaras.modelos.almacen import MemoryStore
from cuentasclaras.modelos.configuracion import armar
from cuentasclaras.modelos.repositorio import Repositorio

CLAVE = "ClaveSegura2026"

GASTOS_V1 = [
    {"Fecha": "05/10/2026", "Quien": "Agustin", "Concepto": "Compra Coto", "Monto": "48500", "Categoria": "Supermercado", "Comprobante": ""},
    {"Fecha": "12/10/2026", "Quien": "Jorge", "Concepto": "Nafta", "Monto": "32000", "Categoria": "Auto", "Comprobante": "https://i.ibb.co/x.jpg"},
    {"Fecha": "20/10/2026", "Quien": "Agustín", "Concepto": "Internet", "Monto": "21500", "Categoria": "Internet", "Comprobante": ""},
    {"Fecha": "no-es-fecha", "Quien": "Agustin", "Concepto": "Rota", "Monto": "100", "Categoria": "Otros", "Comprobante": ""},
    {"Fecha": "21/10/2026", "Quien": "Marta", "Concepto": "Regalo", "Monto": "9000", "Categoria": "Otros", "Comprobante": ""},
]

COMPRAS_V1 = [
    {"Elemento": "Detergente", "Quién Anotó": "Agustin", "Comprado": "No"},
    {"Elemento": "Yerba", "Quién Anotó": "Jorge", "Comprado": "No"},
]


class StoreConPestanas(MemoryStore):
    """MemoryStore con pestañas ajenas al esquema (como Google Sheets)."""

    def __init__(
        self,
        pestanas: dict[str, list[dict[str, str]]],
        externa: dict[str, list[dict[str, str]]] | None = None,
    ) -> None:
        super().__init__()
        self._pestanas = pestanas
        self._externa = externa or {}

    def leer_pestana(self, titulo: str) -> list[dict[str, str]]:
        return [dict(f) for f in self._pestanas.get(titulo, [])]

    def leer_pestana_externa(self, titulo: str, url: str) -> list[dict[str, str]]:
        return [dict(f) for f in self._externa.get(titulo, [])]

    def buscar_pestana_por_columnas(self, columnas):
        buscadas = [str(c).strip().lower() for c in columnas]
        for titulo, filas in self._pestanas.items():
            if not filas:
                continue
            encabezados = [str(k).strip().lower() for k in filas[0]]
            if all(columna in encabezados for columna in buscadas):
                return titulo, [dict(f) for f in filas]
        return None

    def pestanas(self) -> list[str]:
        return sorted(self._pestanas)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.config = armar({"almacen": "memoria", "cifrado": False})
        self.store = StoreConPestanas(
            {migracion.PESTANA_GASTOS: GASTOS_V1, migracion.PESTANA_COMPRAS: COMPRAS_V1}
        )
        self.repo = Repositorio(self.store, self.config)
        self.agustin = self.repo.crear_usuario("agus@x.com", "Agustín Pérez", CLAVE)
        self.jorge = self.repo.crear_usuario("jorge@x.com", "Jorge", CLAVE)
        self.hogar = self.repo.crear_hogar(self.agustin["id"], "Litoral 825")
        self.repo.unirse_por_codigo(
            self.jorge["id"], self.repo.invitar(self.hogar["id"], self.agustin["id"])["codigo"]
        )
        self.hogar_obj = self.repo.obtener_hogar(self.agustin["id"], self.hogar["id"])

    def ctl(self, usuario=None):
        usuario = usuario or self.agustin
        return ControladorHogar(
            self.repo,
            self.config,
            None,
            usuario,
            self.repo.obtener_hogar(usuario["id"], self.hogar["id"]),
        )


class TestAnalisis(Base):
    def test_normaliza_encabezados_y_cuenta(self):
        informe = migracion.analizar(GASTOS_V1)
        self.assertEqual(informe.omitidos, 1)  # la fecha inválida
        self.assertEqual(informe.importados, 0)  # analizar no importa
        self.assertEqual(informe.total, Decimal("111000.00"))
        self.assertEqual(informe.personas["Agustin"], 1)
        self.assertEqual(informe.personas["Agustín"], 1)
        self.assertEqual(informe.personas["Marta"], 1)
        self.assertEqual(informe.desde.isoformat(), "2026-10-05")
        self.assertEqual(informe.hasta.isoformat(), "2026-10-21")

    def test_propuesta_de_personas(self):
        miembros = self.repo.miembros(self.hogar["id"])
        propuesta = migracion.proponer_mapeo(["Agustin", "Jorge", "Marta"], miembros)
        self.assertEqual(propuesta["Agustin"], self.agustin["id"])  # por email agus@
        self.assertEqual(propuesta["Jorge"], self.jorge["id"])
        self.assertNotIn("Marta", propuesta)


class TestControladorImportacion(Base):
    def test_analisis_propietario(self):
        resultado = self.ctl().analizar_importacion()
        self.assertTrue(resultado.ok, resultado.mensaje)
        info = resultado.datos
        self.assertEqual(info["filas"], len(GASTOS_V1))
        self.assertEqual(info["compras"], len(COMPRAS_V1))
        self.assertIn("Marta", info["sin_asignar"])
        self.assertEqual(info["ya_importado"], "")

    def test_solo_propietario_puede_importar(self):
        resultado = self.ctl(self.jorge).analizar_importacion()
        self.assertFalse(resultado.ok)
        self.assertIn("propietario", resultado.mensaje.lower())

    def test_importacion_completa(self):
        ctl = self.ctl()
        analisis = ctl.analizar_importacion().datos
        mapeo = {n: uid for n, uid in analisis["mapeo"].items()}
        mapeo["Marta"] = self.jorge["id"]

        resultado = ctl.importar_v1(mapeo)
        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(resultado.datos.importados, 4)  # la fila rota se omite
        self.assertEqual(resultado.datos.omitidos, 1)
        self.assertEqual(resultado.datos.compras, 2)

        resumen = self.repo.resumen(self.hogar["id"], self.agustin["id"], historico=True)
        self.assertEqual(resumen["cantidad"], 4)
        self.assertEqual(resumen["total"], Decimal("111000.00"))
        self.assertEqual(len(self.repo.compras(self.hogar["id"], self.agustin["id"])), 2)
        # El total de Marta se cargó a Jorge.
        self.assertEqual(
            resumen["saldos"][self.jorge["id"]]["pagado"], Decimal("41000.00")
        )

    def test_segunda_importacion_queda_marcada(self):
        ctl = self.ctl()
        ctl.importar_v1(ctl.analizar_importacion().datos["mapeo"])
        info = ctl.analizar_importacion().datos
        self.assertTrue(info["ya_importado"])

    def test_por_defecto_para_nombres_desconocidos(self):
        ctl = self.ctl()
        mapeo = {"Agustin": self.agustin["id"], "Jorge": self.jorge["id"]}
        resultado = ctl.importar_v1(mapeo, por_defecto=self.agustin["id"])
        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(resultado.datos.importados, 4)  # Marta cae en el por defecto
        self.assertEqual(resultado.datos.sin_persona, {})

    def test_sin_pestanas_avisa(self):
        self.store._pestanas = {}
        resultado = self.ctl().analizar_importacion()
        self.assertTrue(resultado.ok)
        self.assertIn("no encontramos", resultado.mensaje.lower())
        self.assertEqual(resultado.datos["pestanas"], [])


class TestPestanaConOtroNombre(Base):
    """El nombre de la pestaña puede ser otro: se reconoce por las columnas."""

    def test_encuentra_por_encabezados(self):
        self.store._pestanas = {
            "cc_gastos": [{"id": "x", "fecha": "2026-10-01", "monto": "1"}],
            "Gastos 2025": GASTOS_V1,
            "Compras de la casa": COMPRAS_V1,
        }
        resultado = self.ctl().analizar_importacion()
        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(resultado.datos["origen"], "por_columnas")
        self.assertEqual(resultado.datos["filas"], len(GASTOS_V1))

    def test_no_confunde_las_pestanas_propias(self):
        """`cc_gastos` no debe tomarse como planilla vieja."""
        self.store._pestanas = {
            "cc_gastos": [
                {"fecha": "2026-10-01", "concepto": "Algo", "monto": "100"}
            ]
        }
        resultado = self.ctl().analizar_importacion()
        self.assertEqual(resultado.datos["filas"], 0)


class TestPlanillaExterna(Base):
    """Los datos viejos pueden estar en otra planilla (copia de la original)."""

    def setUp(self) -> None:
        super().setUp()
        self.store._pestanas = {}  # la planilla de la app no las tiene
        self.store._externa = {
            migracion.PESTANA_GASTOS: GASTOS_V1,
            migracion.PESTANA_COMPRAS: COMPRAS_V1,
        }
        self.config_externa = armar(
            {
                "almacen": "memoria",
                "cifrado": False,
                "hoja_url_legacy": "https://docs.google.com/spreadsheets/d/vieja/edit",
            }
        )

    def _ctl(self):
        return ControladorHogar(
            self.repo,
            self.config_externa,
            None,
            self.agustin,
            self.repo.obtener_hogar(self.agustin["id"], self.hogar["id"]),
        )

    def test_lee_de_la_planilla_configurada(self):
        resultado = self._ctl().analizar_importacion()
        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(resultado.datos["origen"], "externa")
        self.assertEqual(resultado.datos["filas"], len(GASTOS_V1))

    def test_importa_desde_la_externa(self):
        ctl = self._ctl()
        mapeo = ctl.analizar_importacion().datos["mapeo"]
        resultado = ctl.importar_v1(mapeo, por_defecto=self.agustin["id"])
        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(resultado.datos.importados, 4)

    def test_sin_configurar_la_externa_no_hay_nada(self):
        resultado = self.ctl().analizar_importacion()
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.datos["filas"], 0)
        self.assertEqual(resultado.datos["origen"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
