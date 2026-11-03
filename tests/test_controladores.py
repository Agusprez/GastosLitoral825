"""Tests de la capa de controladores (C de MVC) y del importador."""

from __future__ import annotations

import base64
import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cuentasclaras.controladores import (
    ControladorAdmin,
    ControladorCompras,
    ControladorCuenta,
    ControladorGastos,
    ControladorHogar,
    ControladorPlanes,
    ControladorResumen,
    ControladorSesion,
    Resultado,
)
from cuentasclaras.modelos import datos_demo as seed
from cuentasclaras.modelos.almacen import MemoryStore
from cuentasclaras.modelos.archivos import MediosLocal
from cuentasclaras.modelos.configuracion import armar
from cuentasclaras.modelos.repositorio import Repositorio

CLAVE = "ClaveSegura2026"
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self._carpeta.cleanup)
        self.config = armar(
            {
                "almacen": "memoria",
                "cifrado": False,
                "registro_abierto": True,
                "admins": "jefa@cuentasclaras.app",
                "precio_mensual": "4.900",
                "precio_anual": "49.000",
            }
        )
        self.store = MemoryStore()
        self.repo = Repositorio(self.store, self.config)
        self.medios = MediosLocal(Path(self._carpeta.name) / "comprobantes")
        self.ana = self.repo.crear_usuario("ana@x.com", "Ana", CLAVE)
        self.bruno = self.repo.crear_usuario("bruno@x.com", "Bruno", CLAVE)
        self.hogar = self.repo.crear_hogar(self.ana["id"], "Casa")
        self.repo.unirse_por_codigo(
            self.bruno["id"],
            self.repo.invitar(self.hogar["id"], self.ana["id"])["codigo"],
        )
        self.hogar_ana = self.repo.obtener_hogar(self.ana["id"], self.hogar["id"])
        self.hogar_bruno = self.repo.obtener_hogar(self.bruno["id"], self.hogar["id"])

    def ctl(self, clase, usuario=None, hogar="ana"):
        usuario = usuario or self.ana
        hogar_obj = self.hogar_ana if hogar == "ana" else self.hogar_bruno
        return clase(self.repo, self.config, self.medios, usuario, hogar_obj)


class TestResultado(unittest.TestCase):
    def test_fabricas(self):
        self.assertTrue(Resultado.exito("ok").ok)
        self.assertFalse(Resultado.error("mal").ok)
        self.assertEqual(Resultado.aviso("ojo").tipo, "aviso")
        self.assertTrue(Resultado.aviso("ojo").ok)


class TestSesion(Base):
    def test_registro_e_inicio(self):
        ctl = ControladorSesion(self.repo, self.config, self.medios)
        resultado = ctl.registrar("Carla", "carla@x.com", CLAVE, CLAVE, True, "")
        self.assertTrue(resultado.ok, resultado.mensaje)
        token = resultado.datos["token"]
        self.assertTrue(ctl.restaurar(token).ok)

        malo = ctl.registrar("Carla", "carla@x.com", CLAVE, CLAVE, True, "")
        self.assertFalse(malo.ok)

        distinto = ctl.registrar("Dani", "dani@x.com", CLAVE, "otraClave1", True, "")
        self.assertFalse(distinto.ok)
        self.assertIn("no coinciden", distinto.mensaje)

    def test_registro_sin_aceptar(self):
        ctl = ControladorSesion(self.repo, self.config, self.medios)
        self.assertFalse(ctl.registrar("Eva", "eva@x.com", CLAVE, CLAVE, False, "").ok)

    def test_login_y_cierre(self):
        ctl = ControladorSesion(self.repo, self.config, self.medios)
        bueno = ctl.iniciar("ana@x.com", CLAVE)
        self.assertTrue(bueno.ok)
        token = bueno.datos["token"]
        self.assertFalse(ctl.iniciar("ana@x.com", "malisima").ok)
        ctl.cerrar(token)
        self.assertFalse(ctl.restaurar(token).ok)

    def test_registro_con_codigo_de_invitacion(self):
        ctl = ControladorSesion(self.repo, self.config, self.medios)
        codigo = self.repo.invitar(self.hogar["id"], self.ana["id"])["codigo"]
        resultado = ctl.registrar("Flor", "flor@x.com", CLAVE, CLAVE, True, codigo)
        self.assertTrue(resultado.ok, resultado.mensaje)
        usuario = self.repo.usuario_por_email("flor@x.com")
        self.assertEqual(len(self.repo.hogares_de(usuario["id"])), 1)


class TestGastos(Base):
    def test_alta_y_listado(self):
        ctl = self.ctl(ControladorGastos)
        resultado = ctl.agregar("Súper", "15000", "Supermercado", self.ana["id"], [self.ana["id"], self.bruno["id"]])
        self.assertTrue(resultado.ok, resultado.mensaje)
        listado = ctl.listar()
        self.assertTrue(listado.ok)
        self.assertEqual(listado.datos["cantidad"], 1)
        self.assertEqual(listado.datos["total"], Decimal("15000.00"))

    def test_error_de_validacion_no_explota(self):
        ctl = self.ctl(ControladorGastos)
        resultado = ctl.agregar("", "0", "Otros", self.ana["id"], [self.ana["id"]])
        self.assertFalse(resultado.ok)
        self.assertTrue(resultado.mensaje)

    def test_comprobante(self):
        ctl = self.ctl(ControladorGastos)
        alta = ctl.agregar(
            "Feria", "3000", "Supermercado", self.ana["id"], [self.ana["id"]],
            archivo=("ticket.jpg", JPEG),
        )
        self.assertTrue(alta.ok, alta.mensaje)
        gasto_id = alta.datos["id"]
        comprobante = ctl.comprobante(gasto_id)
        self.assertTrue(comprobante.ok)
        self.assertTrue(comprobante.datos["bytes"])  # se optimiza al guardar
        self.assertEqual(comprobante.datos["mime"], "image/jpeg")
        self.assertTrue(comprobante.datos["nombre"].endswith(".jpg"))

    def test_archivo_invalido(self):
        ctl = self.ctl(ControladorGastos)
        resultado = ctl.agregar(
            "Feria", "3000", "Otros", self.ana["id"], [self.ana["id"]],
            archivo=("virus.exe", b"MZ\x90\x00"),
        )
        self.assertFalse(resultado.ok)
        self.assertIn("comprobante", resultado.mensaje.lower())

    def test_editar_y_anular(self):
        ctl = self.ctl(ControladorGastos)
        alta = ctl.agregar("Luz", "1000", "Servicios", self.ana["id"], [self.ana["id"]])
        gasto_id = alta.datos["id"]
        self.assertTrue(ctl.editar(gasto_id, monto="2500").ok)
        self.assertEqual(ctl.detalle(gasto_id).datos["monto"], Decimal("2500.00"))
        self.assertTrue(ctl.anular(gasto_id).ok)
        self.assertEqual(ctl.listar().datos["cantidad"], 0)

    def test_miembro_no_edita_ajeno(self):
        ctl_ana = self.ctl(ControladorGastos)
        gasto_id = ctl_ana.agregar("Luz", "1000", "Servicios", self.ana["id"], [self.ana["id"]]).datos["id"]
        ctl_bruno = self.ctl(ControladorGastos, usuario=self.bruno, hogar="bruno")
        resultado = ctl_bruno.editar(gasto_id, monto="1")
        self.assertFalse(resultado.ok)
        self.assertIn("admin", resultado.mensaje.lower())

    def test_exportar(self):
        ctl = self.ctl(ControladorGastos)
        ctl.agregar("Feria", "3000", "Supermercado", self.ana["id"], [self.ana["id"]])
        csv_texto = ctl.exportar_csv().datos["csv"]
        self.assertIn("Feria", csv_texto)
        self.assertIn("fecha,quien,concepto", csv_texto)
        self.assertIn("Feria", ctl.exportar_json().datos["json"])


class TestCompras(Base):
    def test_flujo(self):
        ctl = self.ctl(ControladorCompras)
        self.assertTrue(ctl.agregar("Detergente").ok)
        self.assertFalse(ctl.agregar("  ").ok)
        items = ctl.listar().datos["items"]
        self.assertEqual(len(items), 1)
        self.assertTrue(ctl.marcar(items[0]["id"], True).ok)
        self.assertEqual(ctl.listar().datos["items"], [])
        self.assertEqual(len(ctl.listar(True).datos["items"]), 1)
        self.assertTrue(ctl.limpiar_compradas().ok)
        self.assertEqual(ctl.listar(True).datos["items"], [])


class TestHogar(Base):
    def test_datos(self):
        datos = self.ctl(ControladorHogar).datos().datos
        self.assertEqual(len(datos["miembros"]), 2)
        self.assertTrue(datos["puedo_administrar"])
        self.assertFalse(datos["es_propietario"] is None)

    def test_invitar_y_revocar(self):
        ctl = self.ctl(ControladorHogar)
        antes = len([i for i in ctl.datos().datos["invitaciones"] if i["vigente"]])
        invitacion = ctl.invitar("miembro", 7, 3)
        self.assertTrue(invitacion.ok, invitacion.mensaje)
        codigo = invitacion.datos["codigo"]
        self.assertEqual(len(codigo), 6)
        vigentes = [i for i in ctl.datos().datos["invitaciones"] if i["vigente"]]
        self.assertEqual(len(vigentes), antes + 1)
        self.assertTrue(ctl.revocar(vigentes[0]["id"]).ok)
        self.assertFalse(
            next(i for i in ctl.datos().datos["invitaciones"] if i["id"] == vigentes[0]["id"])["vigente"]
        )

    def test_renombrar_y_pago(self):
        ctl = self.ctl(ControladorHogar)
        self.assertTrue(ctl.renombrar("Casa Nueva").ok)
        self.assertEqual(ctl.datos().datos["hogar"]["nombre"], "Casa Nueva")
        self.assertTrue(ctl.registrar_pago(self.bruno["id"], self.ana["id"], "100").ok)
        self.assertFalse(ctl.registrar_pago(self.ana["id"], self.ana["id"], "100").ok)

    def test_eliminar_pide_confirmacion(self):
        ctl = self.ctl(ControladorHogar)
        self.assertFalse(ctl.eliminar("otro nombre").ok)
        self.assertTrue(ctl.eliminar("Casa").ok)
        self.assertEqual(self.repo.hogares_de(self.ana["id"]), [])

    def test_miembro_no_administra(self):
        ctl = self.ctl(ControladorHogar, usuario=self.bruno, hogar="bruno")
        self.assertFalse(ctl.invitar().ok)
        self.assertFalse(ctl.renombrar("x").ok)


class TestCuenta(Base):
    def test_perfil_y_clave(self):
        ctl = self.ctl(ControladorCuenta)
        self.assertTrue(ctl.actualizar("Ana María", "ana@x.com").ok)
        malo = ctl.cambiar_clave(CLAVE, "nueva", "otra")
        self.assertFalse(malo.ok)
        self.assertTrue(ctl.cambiar_clave(CLAVE, "NuevaClave2026", "NuevaClave2026").ok)
        self.assertFalse(self.repo_usuario_valido(CLAVE))

    def repo_usuario_valido(self, clave: str) -> bool:
        from cuentasclaras.modelos import autenticacion

        return autenticacion.autenticar(self.store, "ana@x.com", clave).ok

    def test_sesiones_y_baja(self):
        ctl = self.ctl(ControladorCuenta)
        self.assertGreaterEqual(ctl.sesiones_activas(), 0)
        self.assertTrue(ctl.cerrar_otras_sesiones("").ok)
        self.assertFalse(ctl.eliminar("clave-incorrecta").ok)


class TestResumenYPlanes(Base):
    def test_panel(self):
        self.repo.agregar_gasto(
            self.hogar["id"], self.ana["id"], "Súper", "10000", "Supermercado",
            self.ana["id"], [self.ana["id"], self.bruno["id"]],
        )
        datos = self.ctl(ControladorResumen).panel().datos
        self.assertEqual(datos["total"], Decimal("10000.00"))
        self.assertEqual(datos["mi_neto"], Decimal("5000.00"))
        self.assertTrue(datos["es_gratis"])

    def test_planes(self):
        estado = self.ctl(ControladorPlanes).estado().datos
        self.assertEqual(estado["plan"], "gratis")
        self.assertEqual(estado["limites"]["miembros"], 3)
        pedido = self.ctl(ControladorPlanes).pedido("anual")
        self.assertIn("mailto:", pedido["mailto"])
        self.assertIn("Casa", pedido["asunto"])


class TestAdmin(Base):
    def test_guardia(self):
        ctl = self.ctl(ControladorAdmin)
        self.assertFalse(ctl.datos().ok)

    def test_panel_y_plan(self):
        jefa = self.repo.crear_usuario("jefa@cuentasclaras.app", "Jefa", CLAVE)
        ctl = ControladorAdmin(self.repo, self.config, self.medios, jefa, self.hogar_ana)
        self.assertTrue(ctl.puede())
        datos = ctl.datos().datos
        self.assertEqual(datos["resumen"]["usuarios"], 3)
        self.assertTrue(ctl.cambiar_plan(self.hogar["id"], "pro").ok)
        self.assertEqual(self.repo.obtener_hogar(self.ana["id"], self.hogar["id"])["plan"], "pro")
        self.assertTrue(ctl.alternar_usuario(self.bruno["id"], False).ok)


class TestImportador(Base):
    def _csv(self, filas: list[dict]) -> Path:
        ruta = Path(self._carpeta.name) / "gastos.csv"
        with ruta.open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.DictWriter(
                archivo, fieldnames=["fecha", "quien", "concepto", "monto", "categoria", "comprobante"]
            )
            escritor.writeheader()
            escritor.writerows(filas)
        return ruta

    def test_importa_csv(self):
        from tools.importar_planilla import importar, leer_csv, normalizar_fila

        ruta = self._csv(
            [
                {"fecha": "05/10/2026", "quien": "Ana", "concepto": "Súper", "monto": "15000", "categoria": "Supermercado", "comprobante": ""},
                {"fecha": "07/10/2026", "quien": "Bruno", "concepto": "Nafta", "monto": "8000", "categoria": "Auto", "comprobante": "https://i.imgur.com/x.jpg"},
                {"fecha": "no-es-fecha", "quien": "Ana", "concepto": "Rota", "monto": "100", "categoria": "Otros", "comprobante": ""},
                {"fecha": "08/10/2026", "quien": "Desconocido", "concepto": "Nadie", "monto": "100", "categoria": "Otros", "comprobante": ""},
            ]
        )
        filas = leer_csv(ruta)
        self.assertEqual(len(filas), 4)
        informe = importar(
            self.repo,
            self.hogar["id"],
            filas,
            {"Ana": self.ana["id"], "Bruno": self.bruno["id"]},
            aplicar=True,
        )
        self.assertEqual(informe.importados, 2)
        self.assertEqual(informe.omitidos, 2)
        self.assertEqual(len(informe.errores), 2)
        gastos = self.repo.gastos(self.hogar["id"], self.ana["id"])
        self.assertEqual(len(gastos), 2)
        self.assertTrue(any(g["comprobante"].startswith("http") for g in gastos))

    def test_normaliza_encabezados(self):
        from tools.importar_planilla import normalizar_fila

        fila = normalizar_fila({"Fecha": "01/01/2026", "Quién pagó": "Ana", "Detalle": "Luz", "Monto": "100", "Categoría": "Servicios"})
        self.assertEqual(fila["quien"], "Ana")
        self.assertEqual(fila["concepto"], "Luz")

    def test_informe_sin_usuarios(self):
        from tools.importar_planilla import asegurar_usuarios

        with self.assertRaises(SystemExit):
            asegurar_usuarios(self.repo, {}, {}, aplicar=False)


class TestDemo(Base):
    def test_datos_demo(self):
        store = MemoryStore()
        repo = Repositorio(store, self.config)
        info = seed.sembrar(repo)
        self.assertTrue(info["creado"])
        usuario = repo.usuario_por_email(seed.EMAIL_DEMO)
        resumen = repo.resumen(info["hogar"]["id"], usuario["id"], historico=True)
        self.assertGreaterEqual(resumen["cantidad"], 10)
        self.assertTrue(resumen["transferencias"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
