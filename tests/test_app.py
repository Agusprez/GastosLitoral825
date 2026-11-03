"""Prueba de humo del punto de entrada real (`app.py`).

Levanta la app completa contra el doble de Streamlit: configuración desde
entorno, SQLite en un directorio temporal, cifrado activo, datos de demo y
navegación por todas las secciones. Es lo más parecido a "abrir la app" que se
puede hacer sin red.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests import pandas_falso, streamlit_falso

pandas_falso.instalar()
streamlit_falso.instalar()

import app  # noqa: E402  (importa Streamlit: el doble ya está instalado)
from cuentasclaras.modelos import datos_demo  # noqa: E402
from cuentasclaras.modelos.configuracion import armar  # noqa: E402
from cuentasclaras.modelos.fabrica import abrir_almacen  # noqa: E402
from cuentasclaras.modelos.repositorio import Repositorio  # noqa: E402

FALLAS = ("Ocurrió un error", "No pudimos")


class TestAppCompleta(unittest.TestCase):
    def setUp(self) -> None:
        self._carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self._carpeta.cleanup)
        base = Path(self._carpeta.name)
        self.ruta_db = base / "datos.db"
        self.entorno = {
            "CUENTASCLARAS_ALMACEN": "sqlite",
            "CUENTASCLARAS_SQLITE_RUTA": str(self.ruta_db),
            "CUENTASCLARAS_CLAVE_ARCHIVO": str(base / "clave.key"),
            "CUENTASCLARAS_MEDIOS_DIR": str(base / "comprobantes"),
            "CUENTASCLARAS_DEMO": "1",
            "CUENTASCLARAS_ADMINS": "jefa@cuentasclaras.app",
            "CUENTASCLARAS_REGISTRO_ABIERTO": "1",
        }
        self._previos = {clave: os.environ.get(clave) for clave in self.entorno}
        os.environ.update(self.entorno)
        _cerrar_store_sesion()
        streamlit_falso.falso_config()

    def tearDown(self) -> None:
        _cerrar_store_sesion()
        for clave, valor in self._previos.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor

    # --- utilidades ------------------------------------------------------- #
    def correr_app(self) -> None:
        try:
            app.main()
        except (streamlit_falso.RerunStop, streamlit_falso.StopAplicacion):
            pass

    def repo(self) -> Repositorio:
        """Repo sobre el mismo archivo, con la clave real (datos descifrados)."""
        config = armar({})
        store, _ = abrir_almacen(config)
        self.addCleanup(lambda: store.cerrar() if hasattr(store, "cerrar") else None)
        return Repositorio(store, config)

    def store(self):
        config = armar({})
        store, _ = abrir_almacen(config)
        self.addCleanup(lambda: store.cerrar() if hasattr(store, "cerrar") else None)
        return store

    def errores_graves(self) -> list[str]:
        return [
            str(args[0])
            for (args, _) in streamlit_falso.llamadas("error")
            if any(marca in str(args[0]) for marca in FALLAS)
        ]

    # --- pruebas ---------------------------------------------------------- #
    def test_primer_arranque_siembra_y_muestra_landing(self):
        self.correr_app()
        textos = " ".join(
            str(args[0]) for (args, _) in streamlit_falso.llamadas("markdown")
        )
        self.assertIn("Cuentas Claras", textos)

        repo = self.repo()
        usuario = repo.usuario_por_email(datos_demo.EMAIL_DEMO)
        self.assertIsNotNone(usuario)
        self.assertGreaterEqual(len(repo.hogares_de(usuario["id"])), 1)

        # En el archivo, los datos están cifrados de verdad.
        crudo = self.store().crudo.all("usuarios")[0]
        self.assertTrue(crudo["email"].startswith("enc1:"))

    def test_navegacion_por_las_secciones(self):
        self.correr_app()
        repo = self.repo()
        usuario = repo.usuario_por_email(datos_demo.EMAIL_DEMO)
        hogar = repo.hogares_de(usuario["id"])[0]

        streamlit_falso.ESTADO["cc_usuario_id"] = usuario["id"]
        streamlit_falso.ESTADO["cc_token"] = "token"
        streamlit_falso.ESTADO["cc_hogar_id"] = hogar["id"]

        for seccion in (
            "🏠 Inicio",
            "🧾 Gastos",
            "🛒 Compras",
            "🏡 Hogar",
            "💳 Plan",
            "👤 Mi cuenta",
        ):
            streamlit_falso.ESTADO["cc_pagina"] = seccion
            self.correr_app()
            self.assertEqual(self.errores_graves(), [], f"falló la sección {seccion}")

    def test_usuario_sin_hogar_ve_onboarding(self):
        self.correr_app()
        repo = self.repo()
        self.repo_usuario = repo.crear_usuario("solo@x.com", "Solo", "ClaveSegura2026")

        streamlit_falso.ESTADO["cc_usuario_id"] = self.repo_usuario["id"]
        streamlit_falso.ESTADO["cc_token"] = "token"
        self.correr_app()
        textos = " ".join(
            str(args[0]) for (args, _) in streamlit_falso.llamadas("markdown")
        )
        self.assertIn("Creá tu hogar", textos)


def _cerrar_store_sesion() -> None:
    store = streamlit_falso.ESTADO.get("cc_store")
    cerrar = getattr(store, "cerrar", None)
    if callable(cerrar):
        try:
            cerrar()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
