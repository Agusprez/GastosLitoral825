"""Smoke tests de las vistas contra dobles de Streamlit y pandas.

No reemplazan a una prueba en el navegador, pero detectan lo más común:
imports rotos, parámetros inventados en las widgets, `NameError` y flujos de
acción que explotan con datos reales.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import pandas_falso, streamlit_falso

pandas_falso.instalar()
streamlit_falso.instalar()

from cuentasclaras.modelos import datos_demo as seed  # noqa: E402
from cuentasclaras.modelos.almacen import MemoryStore  # noqa: E402
from cuentasclaras.modelos.archivos import MediosLocal  # noqa: E402
from cuentasclaras.modelos.configuracion import armar  # noqa: E402
from cuentasclaras.modelos.repositorio import Repositorio  # noqa: E402
from vistas import admin, compras, cuenta, gastos, hogar, inicio, landing, navegacion  # noqa: E402
from vistas import planes as vista_planes  # noqa: E402
from vistas.componentes import Contexto, sin_hogar  # noqa: E402

MARCAS_DE_FALLA = (
    "Ocurrió un error",
    "No pudimos",
    "No tenés permiso",
    "error inesperado",
    "Traceback",
)


class BaseVistas(unittest.TestCase):
    modo_click = False

    def setUp(self) -> None:
        streamlit_falso.falso_config(modo_click=self.modo_click)
        self._carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self._carpeta.cleanup)

        self.config = armar(
            {
                "almacen": "memoria",
                "cifrado": False,
                "registro_abierto": True,
                "admins": "admin@cuentasclaras.app",
                "precio_mensual": "4.900",
                "precio_anual": "49.000",
            }
        )
        self.store = MemoryStore()
        self.repo = Repositorio(self.store, self.config)
        self.demo = seed.sembrar(self.repo)
        self.usuario = self.repo.usuario_por_email(seed.EMAIL_DEMO)
        self.hogar = self.repo.obtener_hogar(self.usuario["id"], self.demo["hogar"]["id"])
        self.medios = MediosLocal(Path(self._carpeta.name) / "comprobantes")
        self.ctx = self._contexto(self.usuario, self.hogar)

    def _contexto(self, usuario, hogar) -> Contexto:
        return Contexto(
            config=self.config,
            store=self.store,
            repo=self.repo,
            medios=self.medios,
            ctrl=streamlit_falso._CookieController(),
            usuario=usuario,
            token="token-de-prueba",
            hogar=hogar,
            origen_clave="prueba",
        )

    def correr(self, funcion, *args) -> None:
        """Ejecuta una vista aceptando los cortes de st.rerun / st.stop."""
        try:
            funcion(*args)
        except (streamlit_falso.RerunStop, streamlit_falso.StopAplicacion):
            pass

    def errores_mostrados(self) -> list[str]:
        return [str(args[0]) for (args, _) in streamlit_falso.llamadas("error")]

    def fallos(self) -> list[str]:
        """Errores que delatan una falla real (no avisos propios de la interfaz)."""
        return [
            mensaje
            for mensaje in self.errores_mostrados()
            if any(marca in mensaje for marca in MARCAS_DE_FALLA)
        ]


class TestLanding(BaseVistas):
    def test_landing_sin_sesion(self):
        ctx = self._contexto(None, None)
        self.correr(landing.render, ctx)
        textos = " ".join(str(a[0]) for (a, _) in streamlit_falso.llamadas("markdown"))
        self.assertIn("Cuentas Claras", textos)
        self.assertEqual(self.fallos(), [])


class TestOnboarding(BaseVistas):
    def test_sin_hogar(self):
        self.repo.crear_usuario("nuevo@x.com", "Nuevo", "ClaveSegura2026")
        usuario = self.repo.usuario_por_email("nuevo@x.com")
        ctx = self._contexto(usuario, None)
        self.correr(sin_hogar, ctx)
        self.assertEqual(self.fallos(), [])


class TestVistasApp(BaseVistas):
    def test_inicio(self):
        self.correr(inicio.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_gastos(self):
        self.correr(gastos.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_compras(self):
        self.correr(compras.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_hogar(self):
        self.correr(hogar.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_cuenta(self):
        self.correr(cuenta.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_planes(self):
        self.correr(vista_planes.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_navegacion(self):
        paginas = {"🏠 Inicio": inicio.render, "🧾 Gastos": gastos.render}
        elegida = navegacion.render(self.ctx, paginas)
        self.assertIn(elegida, paginas)

    def test_hogar_como_miembro_sin_permisos(self):
        bruno = self.repo.usuario_por_email(seed.EMAIL_DEMO2)
        self.repo.cambiar_rol(self.hogar["id"], self.usuario["id"], bruno["id"], "miembro")
        ctx = self._contexto(bruno, self.repo.obtener_hogar(bruno["id"], self.hogar["id"]))
        self.correr(hogar.render, ctx)
        self.assertEqual(self.fallos(), [])


    def test_hogar_muestra_mensaje_para_whatsapp(self):
        """Recién generada la invitación, la vista deja el texto listo para copiar."""
        codigo = self.repo.invitar(self.hogar["id"], self.usuario["id"])["codigo"]
        streamlit_falso.ESTADO["cc_ultima_invitacion"] = {
            "codigo": codigo,
            "expira_en": "",
        }
        self.correr(hogar.render, self.ctx)

        textos = [str(args[0]) for (args, _) in streamlit_falso.llamadas("code")]
        self.assertTrue(any(codigo in texto for texto in textos), textos)
        enlaces = [args[1] for (args, _) in streamlit_falso.llamadas("link_button")]
        self.assertTrue(any("wa.me" in str(enlace) for enlace in enlaces), enlaces)
        self.assertEqual(self.fallos(), [])


class TestAdmin(BaseVistas):
    def test_admin(self):
        usuario = self.repo.crear_usuario(
            "admin@cuentasclaras.app", "Admin", "ClaveSegura2026"
        )
        self.assertTrue(usuario["es_admin_plataforma"])
        ctx = self._contexto(usuario, self.hogar)
        self.correr(admin.render, ctx)
        self.assertEqual(self.fallos(), [])

    def test_admin_sin_permiso(self):
        self.correr(admin.render, self.ctx)
        mensajes = " ".join(self.errores_mostrados())
        self.assertIn("administración", mensajes)


class TestVistasConClicks(BaseVistas):
    """Con todos los botones apretados: los flujos no deben romper."""

    modo_click = True

    def test_inicio(self):
        self.correr(inicio.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_gastos(self):
        self.correr(gastos.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_compras(self):
        self.correr(compras.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_hogar(self):
        self.correr(hogar.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_cuenta(self):
        self.correr(cuenta.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_planes(self):
        self.correr(vista_planes.render, self.ctx)
        self.assertEqual(self.fallos(), [])

    def test_landing(self):
        self.correr(landing.render, self._contexto(None, None))


class TestNavegacion(BaseVistas):
    """El radio manda: la sección elegida no puede rebotar a Inicio."""

    PAGINAS = {"🏠 Inicio": inicio.render, "🧾 Gastos": gastos.render}

    def test_respeta_la_seccion_elegida(self):
        streamlit_falso.ESTADO["cc_navegacion"] = "🧾 Gastos"
        streamlit_falso.ESTADO["cc_pagina"] = "🏠 Inicio"  # valor viejo
        self.assertEqual(navegacion.render(self.ctx, self.PAGINAS), "🧾 Gastos")

    def test_pedido_por_codigo(self):
        streamlit_falso.ESTADO["cc_ir_a"] = "🧾 Gastos"
        self.assertEqual(navegacion.render(self.ctx, self.PAGINAS), "🧾 Gastos")
        self.assertNotIn("cc_ir_a", streamlit_falso.ESTADO)

    def test_seccion_que_ya_no_existe(self):
        streamlit_falso.ESTADO["cc_navegacion"] = "🛠️ Plataforma"
        self.assertEqual(navegacion.render(self.ctx, self.PAGINAS), "🏠 Inicio")


class TestCodificacion(unittest.TestCase):
    """Los .py del proyecto tienen que estar en UTF-8 limpio, sin mojibake."""

    # Se construyen con chr() para que este mismo archivo no quede marcado.
    MARCAS = tuple(chr(c) for c in (0xC3, 0xC2, 0xFFFD))

    def test_archivos_en_utf8(self):
        raiz = Path(__file__).resolve().parent.parent
        este = Path(__file__).resolve()
        problemas = []
        for ruta in sorted(raiz.rglob("*.py")):
            if "__pycache__" in ruta.parts or ruta.name.startswith("reparar"):
                continue
            if ruta.resolve() == este:
                continue
            crudo = ruta.read_bytes()
            try:
                texto = crudo.decode("utf-8")
            except UnicodeDecodeError:
                problemas.append(f"{ruta.relative_to(raiz)}: no es UTF-8")
                continue
            if crudo.startswith(b"\xef\xbb\xbf"):
                problemas.append(f"{ruta.relative_to(raiz)}: tiene BOM")
            for marca in self.MARCAS:
                if marca in texto:
                    problemas.append(f"{ruta.relative_to(raiz)}: contiene {marca!r}")
                    break
        self.assertEqual(problemas, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
