"""Tests del núcleo (sin Streamlit): dinero, auth, store, reglas de negocio."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cuentasclaras.modelos import autenticacion as auth
from cuentasclaras.modelos import cifrado, dinero
from cuentasclaras.modelos import planes as plans
from cuentasclaras.modelos import saldos as balances
from cuentasclaras.modelos.almacen import MemoryStore, SqliteStore
from cuentasclaras.modelos.configuracion import Config, armar
from cuentasclaras.modelos.repositorio import (
    ErrorNegocio,
    LimiteAlcanzado,
    NoAutorizado,
    Repositorio,
)

CLAVE = "ClaveSegura2026"


def nuevo_repo(store=None, **config) -> Repositorio:
    base = dict(almacen="memoria", registro_abierto=True)
    base.update(config)
    return Repositorio(store or MemoryStore(), Config(**base))


class TestDinero(unittest.TestCase):
    def test_formato_es_ar(self):
        self.assertEqual(dinero.formatear(1234.5), "$1.234,50")
        self.assertEqual(dinero.formatear(0), "$0,00")
        self.assertEqual(dinero.formatear(-1500), "-$1.500,00")
        self.assertEqual(dinero.formatear(1234567.891), "$1.234.567,89")

    def test_parseo(self):
        self.assertEqual(dinero.decimal("1.234,56"), Decimal("1234.56"))
        self.assertEqual(dinero.decimal("$ 12.500"), Decimal("12500"))
        self.assertEqual(dinero.decimal("1234.56"), Decimal("1234.56"))
        self.assertEqual(dinero.decimal(""), Decimal("0"))
        self.assertEqual(dinero.decimal("basura"), Decimal("0"))

    def test_redondeo_comercial(self):
        self.assertEqual(dinero.redondear(Decimal("10.005")), Decimal("10.01"))
        self.assertEqual(dinero.redondear("1234.565"), Decimal("1234.57"))
        self.assertEqual(dinero.monto_texto("1234.5"), "1234.50")

    def test_miles_argentinos(self):
        # "10.005" sin coma es diez mil cinco (formato es-AR), no diez coma cero cero cinco.
        self.assertEqual(dinero.decimal("10.005"), Decimal("10005"))
        self.assertEqual(dinero.decimal("1.234.567,89"), Decimal("1234567.89"))

    def test_fechas(self):
        self.assertEqual(dinero.parsear_fecha("31/12/2025").isoformat(), "2025-12-31")
        self.assertEqual(dinero.parsear_fecha("2025-01-09").isoformat(), "2025-01-09")
        with self.assertRaises(ValueError):
            dinero.parsear_fecha("32/13/2025")
        inicio, fin = dinero.periodo("2024-02")
        self.assertEqual((inicio.day, fin.day), (1, 29))


class TestAuth(unittest.TestCase):
    def test_hash_y_verificacion(self):
        guardado = auth.hash_clave(CLAVE)
        self.assertTrue(guardado.startswith("scrypt$"))
        self.assertTrue(auth.verificar_clave(CLAVE, guardado))
        self.assertFalse(auth.verificar_clave("otra", guardado))
        self.assertFalse(auth.verificar_clave(CLAVE, "texto-plano"))
        self.assertNotEqual(guardado, auth.hash_clave(CLAVE))  # sal distinta

    def test_politica_de_claves(self):
        self.assertTrue(auth.revisar_clave("1234"))
        self.assertTrue(auth.revisar_clave("12345678"))
        self.assertFalse(auth.revisar_clave("claveSinNumero", "ana@x.com", "Ana"))
        self.assertTrue(auth.revisar_clave("anaLaura2026", "analaura@x.com"))
        self.assertEqual(auth.revisar_clave(CLAVE, "jorge@x.com", "Jorge"), [])

    def test_email(self):
        self.assertTrue(auth.email_valido("A@B.com"))
        self.assertFalse(auth.email_valido("sinarroba.com"))

    def test_sesion(self):
        store = MemoryStore()
        token = auth.crear_sesion(store, "u1")
        self.assertIsNotNone(auth.sesion_por_token(store, token))
        auth.revocar(store, token)
        self.assertIsNone(auth.sesion_por_token(store, token))
        self.assertIsNone(auth.sesion_por_token(store, "token-inventado"))

    def test_bloqueo_tras_intentos(self):
        store = MemoryStore()
        repo = nuevo_repo(store)
        repo.crear_usuario("a@x.com", "Ana", CLAVE)
        for _ in range(auth.MAX_INTENTOS):
            self.assertFalse(auth.autenticar(store, "a@x.com", "mal").ok)
        resultado = auth.autenticar(store, "a@x.com", CLAVE)
        self.assertFalse(resultado.ok)
        self.assertIn("intentos", resultado.mensaje.lower())

    def test_login_ok(self):
        store = MemoryStore()
        repo = nuevo_repo(store)
        repo.crear_usuario("a@x.com", "Ana", CLAVE)
        self.assertTrue(auth.autenticar(store, "A@X.com ", CLAVE).ok)
        self.assertFalse(auth.autenticar(store, "a@x.com", "otraClave1").ok)


class ContratoStore:
    """Batería común: cualquier implementación de Store debe pasarla."""

    def crear(self):  # pragma: no cover - lo define la subclase
        raise NotImplementedError

    def test_crud(self):
        store = self.crear()
        fila = store.insert("usuarios", {"email": "a@x.com", "nombre": "Ana"})
        self.assertTrue(fila["id"])
        self.assertEqual(len(store.all("usuarios")), 1)
        store.update("usuarios", fila["id"], {"nombre": "Ana María"})
        self.assertEqual(store.uno("usuarios", fila["id"])["nombre"], "Ana María")
        store.delete("usuarios", fila["id"])
        self.assertEqual(store.all("usuarios"), [])

    def test_normaliza_columnas(self):
        store = self.crear()
        fila = store.insert("gastos", {"concepto": "Luz", "monto": "100"})
        self.assertEqual(fila["estado"], "")
        self.assertEqual(sorted(fila), sorted(
            ["id", "hogar_id", "fecha", "concepto", "monto", "categoria", "pagado_por",
             "division", "comprobante", "creado_por", "creado_en", "estado"]
        ))

    def test_borrar_donde(self):
        store = self.crear()
        store.insert("compras", {"hogar_id": "h1", "texto": "Leche"})
        store.insert("compras", {"hogar_id": "h1", "texto": "Pan", "estado": "comprado"})
        self.assertEqual(store.borrar_donde("compras", estado="comprado"), 1)
        self.assertEqual(len(store.all("compras")), 1)

    def test_id_inexistente(self):
        store = self.crear()
        with self.assertRaises(Exception):
            store.update("usuarios", "no-existe", {"nombre": "x"})
        with self.assertRaises(Exception):
            store.delete("usuarios", "no-existe")


class TestMemoryStore(ContratoStore, unittest.TestCase):
    def crear(self):
        return MemoryStore()


class TestSqliteStore(ContratoStore, unittest.TestCase):
    def crear(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)  # se ejecuta último (LIFO)
        store = SqliteStore(Path(carpeta.name) / "test.db")
        self.addCleanup(store.cerrar)  # se ejecuta primero
        return store

    def test_persistencia_entre_conexiones(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "persistente.db"
            store1 = SqliteStore(ruta)
            store1.insert("usuarios", {"email": "a@x.com", "nombre": "Ana"})
            store2 = SqliteStore(ruta)
            self.assertEqual(len(store2.all("usuarios")), 1)
            store1.cerrar()
            store2.cerrar()


class TestBalances(unittest.TestCase):
    def test_reparto_exacto(self):
        partes = balances.repartir("100", ["a", "b", "c"])
        self.assertEqual(sum(partes.values()), Decimal("100.00"))
        self.assertEqual(partes["a"], Decimal("33.34"))

    def test_reparto_con_pesos(self):
        partes = balances.redondear_reparto("100", {"a": 2, "b": 1})
        self.assertEqual(partes, {"a": Decimal("66.67"), "b": Decimal("33.33")})

    def test_saldos_con_pago(self):
        gastos = [{"monto": "100", "pagado_por": "a", "division": '{"a": "50", "b": "50"}',
                   "estado": "activo"}]
        saldos = balances.saldos(gastos, [], ["a", "b"])
        self.assertEqual(saldos["a"]["neto"], Decimal("50.00"))
        self.assertEqual(saldos["b"]["neto"], Decimal("-50.00"))
        transferencias = balances.sugerir_transferencias({k: v["neto"] for k, v in saldos.items()})
        self.assertEqual(len(transferencias), 1)
        self.assertEqual(transferencias[0]["de"], "b")
        self.assertEqual(transferencias[0]["monto"], Decimal("50.00"))

        pagos = [{"de_usuario": "b", "a_usuario": "a", "monto": "50"}]
        saldos2 = balances.saldos(gastos, pagos, ["a", "b"])
        self.assertEqual(saldos2["a"]["neto"], Decimal("0.00"))
        self.assertEqual(saldos2["b"]["neto"], Decimal("0.00"))

    def test_anulados_no_cuentan(self):
        gastos = [{"monto": "100", "pagado_por": "a", "division": "{}", "estado": "anulado"}]
        saldos = balances.saldos(gastos, [], ["a"])
        self.assertEqual(saldos["a"]["neto"], Decimal("0.00"))


class TestRepositorioCuentas(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.repo = nuevo_repo(self.store)
        self.ana = self.repo.crear_usuario("ana@x.com", "Ana", CLAVE)
        self.bruno = self.repo.crear_usuario("bruno@x.com", "Bruno", CLAVE)
        self.carla = self.repo.crear_usuario("carla@x.com", "Carla", CLAVE)

    def test_email_duplicado(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.crear_usuario("ana@x.com", "Otra Ana", CLAVE)

    def test_clave_debil(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.crear_usuario("debil@x.com", "Débil", "1234")

    def test_hogar_y_rol(self):
        hogar = self.repo.crear_hogar(self.ana["id"], "Casa San Pedro")
        self.assertEqual(hogar["rol"], "propietario")
        self.assertEqual(hogar["plan"], plans.GRATIS)
        self.assertEqual(self.repo.rol_en(hogar["id"], self.bruno["id"]), None)

    def test_limite_de_hogares_gratis(self):
        self.repo.crear_hogar(self.ana["id"], "Casa 1")
        with self.assertRaises(LimiteAlcanzado):
            self.repo.crear_hogar(self.ana["id"], "Casa 2")

    def test_invitacion_y_union(self):
        hogar = self.repo.crear_hogar(self.ana["id"], "Casa")
        invitacion = self.repo.invitar(hogar["id"], self.ana["id"])
        self.assertEqual(len(invitacion["codigo"]), 6)
        self.assertEqual(len(self.repo.miembros(hogar["id"])), 1)

        unido = self.repo.unirse_por_codigo(self.bruno["id"], invitacion["codigo"].lower())
        self.assertEqual(unido["id"], hogar["id"])
        self.assertEqual(len(self.repo.miembros(hogar["id"])), 2)
        with self.assertRaises(ErrorNegocio):
            self.repo.unirse_por_codigo(self.bruno["id"], invitacion["codigo"])

    def test_codigo_invalido(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.unirse_por_codigo(self.bruno["id"], "ZZZZZZ")

    def test_limite_de_miembros(self):
        hogar = self.repo.crear_hogar(self.ana["id"], "Casa")
        for usuario in (self.bruno, self.carla):
            self.repo.unirse_por_codigo(
                usuario["id"], self.repo.invitar(hogar["id"], self.ana["id"])["codigo"]
            )
        with self.assertRaises(LimiteAlcanzado):
            self.repo.invitar(hogar["id"], self.ana["id"])

    def test_solo_admin_puede_invitar(self):
        hogar = self.repo.crear_hogar(self.ana["id"], "Casa")
        self.repo.unirse_por_codigo(
            self.bruno["id"], self.repo.invitar(hogar["id"], self.ana["id"])["codigo"]
        )
        with self.assertRaises(NoAutorizado):
            self.repo.invitar(hogar["id"], self.bruno["id"])

    def test_cambiar_clave_cierra_sesiones(self):
        token = auth.crear_sesion(self.store, self.ana["id"])
        otro = auth.crear_sesion(self.store, self.ana["id"])
        self.repo.cambiar_clave(self.ana["id"], CLAVE, "NuevaClave2026", token_actual=token)
        self.assertIsNotNone(auth.sesion_por_token(self.store, token))
        self.assertIsNone(auth.sesion_por_token(self.store, otro))
        self.assertTrue(auth.autenticar(self.store, "ana@x.com", "NuevaClave2026").ok)

    def test_revocar_todas(self):
        t1 = auth.crear_sesion(self.store, self.ana["id"])
        t2 = auth.crear_sesion(self.store, self.ana["id"])
        auth.revocar_todas(self.store, self.ana["id"])
        self.assertIsNone(auth.sesion_por_token(self.store, t1))
        self.assertIsNone(auth.sesion_por_token(self.store, t2))


class TestRepositorioGastos(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.repo = nuevo_repo(self.store)
        self.ana = self.repo.crear_usuario("ana@x.com", "Ana", CLAVE)
        self.bruno = self.repo.crear_usuario("bruno@x.com", "Bruno", CLAVE)
        self.hogar = self.repo.crear_hogar(self.ana["id"], "Casa")
        self.repo.unirse_por_codigo(
            self.bruno["id"], self.repo.invitar(self.hogar["id"], self.ana["id"])["codigo"]
        )
        self.hid = self.hogar["id"]

    def test_alta_y_resumen(self):
        self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Supermercado", "15000", "Supermercado",
            self.ana["id"], [self.ana["id"], self.bruno["id"]],
        )
        resumen = self.repo.resumen(self.hid, self.ana["id"])
        self.assertEqual(resumen["total"], Decimal("15000.00"))
        self.assertEqual(resumen["cantidad"], 1)
        self.assertEqual(resumen["saldos"][self.ana["id"]]["neto"], Decimal("7500.00"))
        self.assertEqual(resumen["saldos"][self.bruno["id"]]["neto"], Decimal("-7500.00"))
        self.assertEqual(resumen["transferencias"][0]["monto"], Decimal("7500.00"))
        self.assertEqual(resumen["por_categoria"]["Supermercado"], Decimal("15000.00"))
        self.assertEqual(resumen["gastos"][0]["pagado_por_nombre"], "Ana")

    def test_monto_invalido(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.agregar_gasto(
                self.hid, self.ana["id"], "Nada", "0", "Otros", self.ana["id"]
            )

    def test_pagador_de_otro_hogar(self):
        intruso = self.repo.crear_usuario("x@x.com", "Ximena", CLAVE)
        with self.assertRaises(ErrorNegocio):
            self.repo.agregar_gasto(
                self.hid, self.ana["id"], "Cena", "100", "Otros", intruso["id"]
            )

    def test_division_personalizada(self):
        gasto = self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Regalo", "1000", "Otros",
            self.ana["id"], [self.bruno["id"]],
        )
        self.assertEqual(gasto["division_detalle"][self.bruno["id"]], Decimal("1000.00"))

    def test_editar_anular(self):
        gasto = self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Luz", "1000", "Servicios", self.ana["id"]
        )
        editado = self.repo.editar_gasto(self.hid, self.ana["id"], gasto["id"], monto="2000")
        self.assertEqual(editado["monto"], Decimal("2000.00"))
        self.repo.anular_gasto(self.hid, self.ana["id"], gasto["id"])
        self.assertEqual(self.repo.gastos(self.hid, self.ana["id"]), [])
        resumen = self.repo.resumen(self.hid, self.ana["id"])
        self.assertEqual(resumen["total"], Decimal("0.00"))

    def test_miembro_no_puede_editar_ajeno(self):
        gasto = self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Luz", "1000", "Servicios", self.ana["id"]
        )
        with self.assertRaises(NoAutorizado):
            self.repo.editar_gasto(self.hid, self.bruno["id"], gasto["id"], monto="1")

    def test_pago_saldas(self):
        self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Cena", "10000", "Salidas",
            self.ana["id"], [self.ana["id"], self.bruno["id"]],
        )
        self.repo.registrar_pago(
            self.hid, self.bruno["id"], self.bruno["id"], self.ana["id"], "3000"
        )
        resumen = self.repo.resumen(self.hid, self.ana["id"])
        self.assertEqual(resumen["saldos"][self.ana["id"]]["neto"], Decimal("2000.00"))
        self.assertEqual(resumen["transferencias"][0]["monto"], Decimal("2000.00"))

    def test_pago_a_si_mismo(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.registrar_pago(self.hid, self.ana["id"], self.ana["id"], self.ana["id"], "10")

    def test_filtros(self):
        self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Verdulería", "100", "Supermercado", self.ana["id"],
            fecha="01/03/2024",
        )
        self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Pizza", "200", "Salidas", self.ana["id"],
            fecha="15/03/2024",
        )
        self.assertEqual(len(self.repo.gastos(self.hid, self.ana["id"], texto="pizza")), 1)
        self.assertEqual(
            len(self.repo.gastos(self.hid, self.ana["id"], categoria="Salidas")), 1
        )
        self.assertEqual(
            len(self.repo.gastos(self.hid, self.ana["id"], desde="10/03/2024")), 1
        )

    def test_compras(self):
        self.repo.agregar_compra(self.hid, self.ana["id"], "Detergente")
        item = self.repo.compras(self.hid, self.ana["id"])[0]
        self.repo.cambiar_estado_compra(self.hid, self.bruno["id"], item["id"], True)
        self.assertEqual(self.repo.compras(self.hid, self.ana["id"]), [])
        self.assertEqual(len(self.repo.compras(self.hid, self.ana["id"], True)), 1)
        self.repo.limpiar_compradas(self.hid, self.ana["id"])
        self.assertEqual(self.repo.compras(self.hid, self.ana["id"], True), [])

    def test_exportacion(self):
        self.repo.agregar_gasto(
            self.hid, self.ana["id"], "Feria", "3000", "Supermercado", self.ana["id"]
        )
        csv_texto = self.repo.exportar_csv(self.hid, self.ana["id"])
        self.assertIn("Feria", csv_texto)
        self.assertIn("fecha,quien,concepto", csv_texto)
        respaldo = self.repo.exportar_json(self.hid, self.ana["id"])
        self.assertIn("Feria", respaldo)


class TestAislamiento(unittest.TestCase):
    """Un hogar jamás ve ni toca los datos de otro."""

    def setUp(self):
        self.store = MemoryStore()
        self.repo = nuevo_repo(self.store)
        self.ana = self.repo.crear_usuario("ana@x.com", "Ana", CLAVE)
        self.bruno = self.repo.crear_usuario("bruno@x.com", "Bruno", CLAVE)
        self.casa_ana = self.repo.crear_hogar(self.ana["id"], "Casa Ana")
        self.casa_bruno = self.repo.crear_hogar(self.bruno["id"], "Casa Bruno")
        self.gasto_ana = self.repo.agregar_gasto(
            self.casa_ana["id"], self.ana["id"], "Heladera", "500000",
            "Casa", self.ana["id"],
        )

    def test_no_ve_gastos_ajenos(self):
        with self.assertRaises(NoAutorizado):
            self.repo.gastos(self.casa_ana["id"], self.bruno["id"])

    def test_no_ve_resumen_ajeno(self):
        with self.assertRaises(NoAutorizado):
            self.repo.resumen(self.casa_ana["id"], self.bruno["id"])

    def test_no_edita_gasto_ajeno(self):
        with self.assertRaises(NoAutorizado):
            self.repo.editar_gasto(
                self.casa_ana["id"], self.bruno["id"], self.gasto_ana["id"], monto="1"
            )

    def test_no_borra_gasto_ajeno(self):
        with self.assertRaises(NoAutorizado):
            self.repo.anular_gasto(self.casa_ana["id"], self.bruno["id"], self.gasto_ana["id"])

    def test_no_invita_en_hogar_ajeno(self):
        with self.assertRaises(NoAutorizado):
            self.repo.invitar(self.casa_ana["id"], self.bruno["id"])

    def test_no_exporta_hogar_ajeno(self):
        with self.assertRaises(NoAutorizado):
            self.repo.exportar_csv(self.casa_ana["id"], self.bruno["id"])

    def test_listados_propios(self):
        self.assertEqual([h["id"] for h in self.repo.hogares_de(self.ana["id"])], [self.casa_ana["id"]])
        self.assertEqual([h["id"] for h in self.repo.hogares_de(self.bruno["id"])], [self.casa_bruno["id"]])


class TestCifrado(unittest.TestCase):
    def test_chacha20_vector_rfc8439(self):
        # RFC 8439 §2.3.2: bloque de keystream con contador 1.
        clave = bytes(range(32))
        nonce = bytes.fromhex("000000090000004a00000000")
        esperado = bytes.fromhex(
            "10f1e7e4d13b5915500fdd1fa32071c4"
            "c7d1f4c733c068030422aa9ac3d46c4e"
            "d2826446079faa0914c2d705d98b02a2"
            "b5129cd1de164eb9cbd083e8a2503c4e"
        )
        self.assertEqual(cifrado.bloque_chacha20(clave, nonce, 1), esperado)

    def test_ida_y_vuelta(self):
        cifrador = cifrado.Cifrador("clave-de-prueba")
        self.assertEqual(cifrador.cifrar("", "gastos.concepto"), "")
        for texto in ("Ana", "Compra en el supermercado $12.345,67", "ñandú 🐦"):
            cifrado_texto = cifrador.cifrar(texto, "gastos.concepto")
            self.assertNotEqual(cifrado_texto, texto)
            self.assertTrue(cifrado.es_cifrado(cifrado_texto))
            self.assertEqual(
                cifrador.descifrar(cifrado_texto, "gastos.concepto"), texto
            )

    def test_mismo_texto_distinto_cifrado(self):
        cifrador = cifrado.Cifrador("clave-de-prueba")
        a = cifrador.cifrar("Ana", "usuarios.email")
        b = cifrador.cifrar("Ana", "usuarios.email")
        self.assertNotEqual(a, b)  # nonce aleatorio

    def test_contexto_equivocado_falla(self):
        cifrador = cifrado.Cifrador("clave-de-prueba")
        valor = cifrador.cifrar("Ana", "usuarios.email")
        with self.assertRaises(cifrado.ErrorCifrado):
            cifrador.descifrar(valor, "gastos.concepto")

    def test_clave_incorrecta_falla(self):
        valor = cifrado.Cifrador("clave-uno").cifrar("dato", "usuarios.nombre")
        with self.assertRaises(cifrado.ErrorCifrado):
            cifrado.Cifrador("clave-dos").descifrar(valor, "usuarios.nombre")

    def test_valor_manipulado_falla(self):
        cifrador = cifrado.Cifrador("clave-de-prueba")
        valor = cifrador.cifrar("1000", "gastos.monto")
        crudo = bytearray(cifrado._de_b64(valor[len(cifrado.PREFIJO):]))
        crudo[-1] ^= 0x01  # cambiamos un bit de la etiqueta
        manipulado = cifrado.PREFIJO + cifrado._b64(bytes(crudo))
        with self.assertRaises(cifrado.ErrorCifrado):
            cifrador.descifrar(manipulado, "gastos.monto")

    def test_texto_viejo_sin_cifrar(self):
        cifrador = cifrado.Cifrador("clave-de-prueba")
        self.assertEqual(cifrador.descifrar("Agustin", "usuarios.nombre"), "Agustin")

    def test_almacen_cifrado_no_filtra_el_texto(self):
        base = MemoryStore()
        store = cifrado.AlmacenCifrado(base, cifrado.Cifrador("clave-de-prueba"))
        fila = store.insert(
            "usuarios", {"email": "ana@x.com", "nombre": "Ana", "hash_clave": "x"}
        )
        cruda = base.uno("usuarios", fila["id"])
        self.assertEqual(cruda["id"], fila["id"])  # el id queda legible
        for columna in ("email", "nombre", "hash_clave"):
            self.assertNotIn("Ana" if columna == "nombre" else "ana@x.com", cruda[columna])
            self.assertTrue(cifrado.es_cifrado(cruda[columna]))
        self.assertEqual(store.uno("usuarios", fila["id"])["email"], "ana@x.com")

    def test_update_cifra_y_lee(self):
        base = MemoryStore()
        store = cifrado.AlmacenCifrado(base, cifrado.Cifrador("clave"))
        fila = store.insert("gastos", {"concepto": "Luz"})
        store.update("gastos", fila["id"], {"concepto": "Gas"})
        self.assertEqual(store.uno("gastos", fila["id"])["concepto"], "Gas")
        self.assertTrue(cifrado.es_cifrado(base.uno("gastos", fila["id"])["concepto"]))

    def test_repositorio_completo_cifrado(self):
        store = cifrado.AlmacenCifrado(MemoryStore(), cifrado.Cifrador("clave"))
        repo = Repositorio(store, Config(almacen="memoria"))
        ana = repo.crear_usuario("ana@x.com", "Ana", CLAVE)
        hogar = repo.crear_hogar(ana["id"], "Casa Cifrada")
        repo.agregar_gasto(
            hogar["id"], ana["id"], "Súper", "1500", "Supermercado", ana["id"]
        )
        resumen = repo.resumen(hogar["id"], ana["id"])
        self.assertEqual(resumen["total"], Decimal("1500.00"))
        self.assertEqual(repo.usuario_por_email("ana@x.com")["nombre"], "Ana")
        # Buscar por email sigue funcionando porque se compara en texto claro.
        self.assertTrue(auth.autenticar(store, "ana@x.com", CLAVE).ok)

    def test_resolver_clave_genera_archivo_local(self):
        with tempfile.TemporaryDirectory() as carpeta:
            config = Config(
                almacen="sqlite",
                cifrado=True,
                clave_archivo=str(Path(carpeta) / "clave.key"),
            )
            clave, origen = cifrado.resolver_clave(config)
            self.assertTrue(clave)
            self.assertIn("generada", origen)
            # La segunda vez reutiliza el archivo, no genera otra.
            self.assertEqual(cifrado.resolver_clave(config)[0], clave)

    def test_planilla_sin_clave_no_inventa_una(self):
        config = Config(almacen="sheets", cifrado=True, clave_cifrado="")
        clave, origen = cifrado.resolver_clave(config)
        self.assertEqual((clave, origen), ("", ""))


class TestPlanes(unittest.TestCase):
    def test_limites(self):
        self.assertTrue(plans.permite(plans.GRATIS, "hogares", 0))
        self.assertFalse(plans.permite(plans.GRATIS, "hogares", 1))
        self.assertTrue(plans.permite(plans.PRO, "hogares", 4))
        self.assertFalse(plans.permite(plans.PRO, "hogares", 5))
        self.assertTrue(plans.permite(plans.PRO, "gastos_mes", 10_000))
        self.assertEqual(plans.normalizar_plan("Free"), plans.GRATIS)
        self.assertEqual(plans.normalizar_plan("PRO"), plans.PRO)

    def test_precios(self):
        config = Config(precio_mensual="4.900", precio_anual="49.000")
        self.assertEqual(plans.precio(plans.GRATIS, config=config), Decimal("0"))
        self.assertEqual(plans.precio(plans.PRO, config=config), Decimal("4900.00"))
        self.assertEqual(plans.precio(plans.PRO, "anual", config), Decimal("49000.00"))
        self.assertEqual(config.ahorro_anual_pct, 17)

    def test_historial_gratis(self):
        config = Config()
        self.assertEqual(plans.meses_visibles(plans.GRATIS, config), 12)
        self.assertIsNone(plans.meses_visibles(plans.PRO, config))


class TestConfiguracion(unittest.TestCase):
    """Los secretos se pegan a mano y en TOML el orden importa: toleramos ambos."""

    def test_url_publica_dentro_de_una_seccion(self):
        # Caso real: pegar la línea al final del archivo la mete en [gcp_service_account].
        config = armar({"gcp_service_account": {"url_publica": "https://x.app"}})
        self.assertEqual(config.url_publica, "https://x.app")

    def test_url_publica_de_arriba_gana(self):
        config = armar(
            {
                "url_publica": "https://arriba",
                "gcp_service_account": {"url_publica": "https://anidada"},
            }
        )
        self.assertEqual(config.url_publica, "https://arriba")

    def test_alias_app_url(self):
        self.assertEqual(armar({"app_url": "https://y.app"}).url_publica, "https://y.app")

    def test_url_publica_por_defecto(self):
        """Sin configurar nada, el mensaje de invitación ya trae el link real."""
        self.assertEqual(
            armar({"almacen": "memoria"}).url_publica,
            "https://litoral825.streamlit.app",
        )
        self.assertEqual(armar({"almacen": "memoria", "url_publica": ""}).url_publica, "https://litoral825.streamlit.app")

    def test_credenciales_como_json_en_variable_de_entorno(self):
        """En Render/Fly/Cloud Run la service account viaja como JSON en una variable."""
        texto = '{"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com"}'
        config = armar(
            {
                "gcp_credenciales": texto,
                "hoja_url": "https://docs.google.com/spreadsheets/d/x/edit",
            }
        )
        self.assertIsInstance(config.gcp_credenciales, dict)
        self.assertEqual(config.gcp_credenciales["type"], "service_account")
        self.assertEqual(config.almacen, "sheets")

    def test_credenciales_json_invalido_no_rompe(self):
        config = armar({"gcp_credenciales": "{no es json", "hoja_url": "x"})
        self.assertIsNone(config.gcp_credenciales)
        self.assertEqual(config.almacen, "sqlite")

    def test_variables_de_entorno_sin_prefijo(self):
        """Hugging Face Spaces inyecta los secretos con el nombre exacto."""
        from cuentasclaras.modelos.configuracion import desde_entorno

        datos = desde_entorno(
            {
                "sheet_url_gastos": "https://docs.google.com/spreadsheets/d/x/edit",
                "imgbb_api_key": "clave-imgbb",
                "CUENTASCLARAS_ADMINS": "yo@x.com",
                "PATH": "/usr/bin",
                "HOME": "/home/user",
            }
        )
        self.assertEqual(datos["sheet_url_gastos"], "https://docs.google.com/spreadsheets/d/x/edit")
        self.assertEqual(datos["imgbb_api_key"], "clave-imgbb")
        self.assertEqual(datos["admins"], "yo@x.com")
        self.assertNotIn("path", datos)
        self.assertNotIn("home", datos)

    def test_credenciales_armadas_con_partes(self):
        config = armar(
            {
                "hoja_url": "https://docs.google.com/spreadsheets/d/x/edit",
                "gcp_client_email": "bot@proyecto.iam.gserviceaccount.com",
                "gcp_private_key": "-----BEGIN PRIVATE KEY-----\\nMIIE...\\n-----END PRIVATE KEY-----",
                "gcp_project_id": "proyecto",
            }
        )
        self.assertIsInstance(config.gcp_credenciales, dict)
        self.assertEqual(
            config.gcp_credenciales["client_email"], "bot@proyecto.iam.gserviceaccount.com"
        )
        self.assertIn("\n", config.gcp_credenciales["private_key"])  # "\n" literales
        self.assertEqual(config.gcp_credenciales["project_id"], "proyecto")
        self.assertEqual(config.almacen, "sheets")

    def test_partes_incompletas_no_arman_credenciales(self):
        config = armar({"gcp_client_email": "bot@x.iam.gserviceaccount.com"})
        self.assertIsNone(config.gcp_credenciales)

    def test_otros_ajustes_anidados(self):
        config = armar(
            {
                "gcp_service_account": {
                    "admins": "jefa@x.com",
                    "imgbb_api_key": "clave",
                    "soporte_email": "soporte@x.com",
                }
            }
        )
        self.assertEqual(config.admins, ("jefa@x.com",))
        self.assertEqual(config.imgbb_api_key, "clave")
        self.assertEqual(config.soporte_email, "soporte@x.com")
        self.assertEqual(config.medios, "imgbb")


class TestCicloDeVidaHogar(unittest.TestCase):
    def setUp(self):
        self.repo = nuevo_repo()
        self.ana = self.repo.crear_usuario("ana@x.com", "Ana", CLAVE)
        self.bruno = self.repo.crear_usuario("bruno@x.com", "Bruno", CLAVE)
        self.hogar = self.repo.crear_hogar(self.ana["id"], "Depto")

    def test_expulsar_y_salir(self):
        self.repo.unirse_por_codigo(
            self.bruno["id"], self.repo.invitar(self.hogar["id"], self.ana["id"])["codigo"]
        )
        self.repo.quitar_miembro(self.hogar["id"], self.ana["id"], self.bruno["id"])
        self.assertEqual(len(self.repo.miembros(self.hogar["id"])), 1)

        self.repo.unirse_por_codigo(
            self.bruno["id"], self.repo.invitar(self.hogar["id"], self.ana["id"])["codigo"]
        )
        self.repo.salir_del_hogar(self.hogar["id"], self.bruno["id"])
        self.assertEqual(self.repo.rol_en(self.hogar["id"], self.bruno["id"]), None)

    def test_propietario_no_puede_salir(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.salir_del_hogar(self.hogar["id"], self.ana["id"])

    def test_transferir_propiedad(self):
        self.repo.unirse_por_codigo(
            self.bruno["id"], self.repo.invitar(self.hogar["id"], self.ana["id"])["codigo"]
        )
        self.repo.transferir_propiedad(self.hogar["id"], self.ana["id"], self.bruno["id"])
        self.assertEqual(self.repo.rol_en(self.hogar["id"], self.bruno["id"]), "propietario")
        self.assertEqual(self.repo.rol_en(self.hogar["id"], self.ana["id"]), "admin")

    def test_eliminar_hogar_con_confirmacion(self):
        with self.assertRaises(ErrorNegocio):
            self.repo.eliminar_hogar(self.hogar["id"], self.ana["id"], "otro nombre")
        self.repo.eliminar_hogar(self.hogar["id"], self.ana["id"], "Depto")
        self.assertEqual(self.repo.hogares_de(self.ana["id"]), [])

    def test_plan_pro_permite_mas(self):
        with self.assertRaises(LimiteAlcanzado):
            self.repo.crear_hogar(self.ana["id"], "Casa 2")
        self.repo.cambiar_plan(self.hogar["id"], plans.PRO)
        segunda = self.repo.crear_hogar(self.ana["id"], "Casa 2")
        self.assertEqual(segunda["plan"], plans.GRATIS)
        self.assertEqual(len(self.repo.hogares_de(self.ana["id"])), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
