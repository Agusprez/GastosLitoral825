"""Smoke tests de las vistas contra dobles de Streamlit y pandas.

No reemplazan a una prueba en el navegador, pero detectan lo más común:
imports rotos, parámetros inventados en las widgets, `NameError` y flujos de
acción que explotan con datos reales.
"""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from tests import pandas_falso, streamlit_falso

pandas_falso.instalar()
streamlit_falso.instalar()

from cuentasclaras.modelos import datos_demo as seed  # noqa: E402
from cuentasclaras.modelos import migracion  # noqa: E402
from cuentasclaras.modelos.almacen import MemoryStore  # noqa: E402
from cuentasclaras.modelos.archivos import MediosLocal  # noqa: E402
from cuentasclaras.modelos.configuracion import armar  # noqa: E402
from cuentasclaras.modelos.repositorio import Repositorio  # noqa: E402
from vistas import admin, compras, cuenta, gastos, hogar, inicio, landing, navegacion  # noqa: E402
from vistas import componentes  # noqa: E402
from vistas import planes as vista_planes  # noqa: E402
from vistas.componentes import Contexto, sin_hogar  # noqa: E402

MARCAS_DE_FALLA = (
    "Ocurrió un error",
    "No pudimos",
    "No tenés permiso",
    "error inesperado",
    "Traceback",
)

JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
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

    def dolares_peligrosos(self) -> list[str]:
        """Textos con 2+ `$` sin escapar: Streamlit los renderiza como LaTeX."""
        problemas = []
        for widget in ("markdown", "caption", "info", "warning", "success"):
            for args, _ in streamlit_falso.llamadas(widget):
                texto = str(args[0]) if args else ""
                if texto.replace("\\$", "").count("$") >= 2:
                    problemas.append(f"{widget}: {texto[:90]}")
        return problemas


class TestLanding(BaseVistas):
    def test_landing_solo_tiene_acceso(self):
        """La página de entrada no muestra la info comercial: eso vive en el modal."""
        ctx = self._contexto(None, None)
        self.correr(landing.render, ctx)
        textos = " ".join(str(a[0]) for (a, _) in streamlit_falso.llamadas("markdown"))
        self.assertIn("Cuentas Claras", textos)
        for seccion in ("Qué resuelve", "Cómo funciona", "Preguntas", "| Precio |"):
            self.assertNotIn(seccion, textos)
        # Los formularios están en la página.
        self.assertTrue(streamlit_falso.llamadas("form"))
        self.assertEqual(self.fallos(), [])

    def test_boton_de_informacion(self):
        ctx = self._contexto(None, None)
        self.correr(landing.render, ctx)
        etiquetas = [str(args[0]) for (args, _) in streamlit_falso.llamadas("button")]
        self.assertTrue(any("Información" in etiqueta for etiqueta in etiquetas), etiquetas)


class TestLandingInfoModal(BaseVistas):
    """Con el botón apretado, el modal de información se arma completo."""

    modo_click = True

    def test_modal_con_planes_y_preguntas(self):
        ctx = self._contexto(None, None)
        self.correr(landing.render, ctx)
        textos = " ".join(str(a[0]) for (a, _) in streamlit_falso.llamadas("markdown"))
        for seccion in ("Qué resuelve", "Cómo funciona", "Preguntas", "Gratis"):
            self.assertIn(seccion, textos)
        self.assertEqual(self.fallos(), [])
        # Los precios de la tabla no deben quedar como fórmula matemática.
        self.assertEqual(self.dolares_peligrosos(), [])


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
        self.assertEqual(self.dolares_peligrosos(), [])

    def test_inicio_muestra_pagado_y_correspondiente(self):
        self.correr(inicio.render, self.ctx)
        textos = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("caption"))
        self.assertIn("Pagó", textos)
        self.assertIn("le corresponde", textos)
        self.assertNotIn("le tocó", textos)

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


    def test_avisa_si_falta_url_publica(self):
        """Si alguien la deja vacía a propósito, la vista lo avisa en vez de mentir."""
        from cuentasclaras.modelos.configuracion import Config

        config = Config(almacen="memoria", cifrado=False, url_publica="")
        ctx = Contexto(
            config=config,
            store=self.store,
            repo=Repositorio(self.store, config),
            medios=self.medios,
            ctrl=streamlit_falso._CookieController(),
            usuario=self.usuario,
            token="token",
            hogar=self.hogar,
            origen_clave="prueba",
        )
        codigo = self.repo.invitar(self.hogar["id"], self.usuario["id"])["codigo"]
        streamlit_falso.ESTADO["cc_ultima_invitacion"] = {"codigo": codigo, "expira_en": ""}
        self.correr(hogar.render, ctx)
        avisos = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("warning"))
        self.assertIn("url_publica", avisos)

    def test_el_mensaje_incluye_la_url_configurada(self):
        config = armar(
            {
                "almacen": "memoria",
                "cifrado": False,
                "url_publica": "https://litoral825.streamlit.app",
            }
        )
        ctx = Contexto(
            config=config,
            store=self.store,
            repo=Repositorio(self.store, config),
            medios=self.medios,
            ctrl=streamlit_falso._CookieController(),
            usuario=self.usuario,
            token="token",
            hogar=self.hogar,
            origen_clave="prueba",
        )
        codigo = self.repo.invitar(self.hogar["id"], self.usuario["id"])["codigo"]
        streamlit_falso.ESTADO["cc_ultima_invitacion"] = {"codigo": codigo, "expira_en": ""}
        self.correr(hogar.render, ctx)
        textos = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("code"))
        self.assertIn("https://litoral825.streamlit.app", textos)


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


class TestCookieDeSesion(BaseVistas):
    """El login tiene que sobrevivir a un F5 (cookie escrita en un run limpio)."""

    def _token(self) -> str:
        from cuentasclaras.modelos import autenticacion as auth

        return auth.crear_sesion(self.store, self.usuario["id"])

    def test_login_encola_la_cookie_y_la_escribe_despues(self):
        token = self._token()
        ctx = self._contexto(self.usuario, self.hogar)

        with self.assertRaises(streamlit_falso.RerunStop):
            componentes.entrar(ctx, {"usuario": self.usuario, "token": token})

        # No se escribe en el mismo run: el rerun desmontaría el componente.
        self.assertEqual(streamlit_falso.COOKIE_LLAMADAS, [])
        self.assertEqual(streamlit_falso.ESTADO["cc_pendiente_cookie"], token)

        # El run siguiente la escribe y limpia el pendiente.
        componentes._aplicar_cookies_pendientes(ctx)
        self.assertIn(
            ("set", componentes.COOKIE, token), streamlit_falso.COOKIE_LLAMADAS
        )
        self.assertNotIn("cc_pendiente_cookie", streamlit_falso.ESTADO)
        self.assertEqual(
            streamlit_falso.SESION_COOKIES[componentes.COOKIE], token
        )

    def test_logout_encola_el_borrado(self):
        token = self._token()
        streamlit_falso.ESTADO["cc_usuario_id"] = self.usuario["id"]
        streamlit_falso.ESTADO["cc_token"] = token
        ctx = self._contexto(self.usuario, self.hogar)
        ctx.token = token

        with self.assertRaises(streamlit_falso.RerunStop):
            componentes.salir(ctx)

        self.assertTrue(streamlit_falso.ESTADO["cc_pendiente_borrar"])
        self.assertNotIn("cc_usuario_id", streamlit_falso.ESTADO)

        componentes._aplicar_cookies_pendientes(ctx)
        self.assertIn(
            ("remove", componentes.COOKIE, ""), streamlit_falso.COOKIE_LLAMADAS
        )
        self.assertNotIn(componentes.COOKIE, streamlit_falso.SESION_COOKIES)

    def test_f5_restaura_la_sesion_desde_la_cookie(self):
        token = self._token()
        # Un F5 es una sesión nueva: session_state vacío, cookie presente.
        streamlit_falso.SESION_COOKIES[componentes.COOKIE] = token
        ctx = self._contexto(None, None)
        ctx.ctrl = streamlit_falso._CookieController()

        componentes._restaurar(ctx)

        self.assertIsNotNone(ctx.usuario)
        self.assertEqual(ctx.usuario["id"], self.usuario["id"])
        self.assertEqual(ctx.token, token)

    def test_cookie_vencida_no_loguea(self):
        streamlit_falso.SESION_COOKIES[componentes.COOKIE] = "token-inventado"
        ctx = self._contexto(None, None)
        ctx.ctrl = streamlit_falso._CookieController()

        componentes._restaurar(ctx)

        self.assertIsNone(ctx.usuario)
        # Además se borra la cookie rota.
        self.assertNotIn(componentes.COOKIE, streamlit_falso.SESION_COOKIES)


class TestImportarDesdeLaApp(BaseVistas):
    """El panel de importación lee las pestañas viejas sin tocar nada."""

    GASTOS_V1 = [
        {"Fecha": "05/10/2026", "Quien": "Ana", "Concepto": "Compra Coto", "Monto": "48500", "Categoria": "Supermercado"},
        {"Fecha": "12/10/2026", "Quien": "Bruno", "Concepto": "Nafta", "Monto": "32000", "Categoria": "Auto"},
    ]

    def setUp(self) -> None:
        super().setUp()
        self.pestanas = {
            "Gastos": self.GASTOS_V1,
            "Lista_Compras": [{"Elemento": "Yerba", "Quién Anotó": "Ana"}],
        }
        self.lecturas = 0

        def leer(titulo: str):
            self.lecturas += 1
            return list(self.pestanas.get(titulo, []))

        # El store de test gana la capacidad de leer pestañas ajenas.
        self.store.leer_pestana = leer
        self.store.buscar_pestana_por_columnas = lambda columnas: None

    def _analizar(self):
        resultado = self.ctx.hogar_ctl().analizar_importacion()
        streamlit_falso.ESTADO["cc_import_analisis"] = resultado
        return resultado

    def test_no_lee_la_planilla_al_entrar(self):
        """Abrir Hogar no debe consumir la cuota de lecturas de Google."""
        self.correr(hogar.render, self.ctx)
        self.assertEqual(self.lecturas, 0)

    def test_ofrece_el_boton_de_analisis(self):
        self.correr(hogar.render, self.ctx)
        etiquetas = [str(args[0]) for (args, _) in streamlit_falso.llamadas("button")]
        self.assertTrue(any("Buscar los datos" in e for e in etiquetas), etiquetas)

    def test_muestra_la_previsualizacion_al_analizar(self):
        self._analizar()
        self.correr(hogar.render, self.ctx)
        textos = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("markdown"))
        self.assertIn("2 gasto(s)", textos)
        self.assertIn("80.500,00", textos)
        self.assertEqual(self.fallos(), [])
        self.assertEqual(self.dolares_peligrosos(), [])

    def test_ofrece_mapear_cada_persona(self):
        self._analizar()
        self.correr(hogar.render, self.ctx)
        etiquetas = [str(args[0]) for (args, _) in streamlit_falso.llamadas("selectbox")]
        self.assertTrue(any("Ana" in e for e in etiquetas), etiquetas)
        self.assertTrue(any("Bruno" in e for e in etiquetas), etiquetas)

    def test_no_importa_solo_por_entrar(self):
        antes = len(self.repo.gastos(self.hogar["id"], self.usuario["id"]))
        self._analizar()
        self.correr(hogar.render, self.ctx)
        despues = len(self.repo.gastos(self.hogar["id"], self.usuario["id"]))
        self.assertEqual(antes, despues)

    def test_diagnostico_cuando_no_hay_pestanas(self):
        """Sin pestañas viejas, la app muestra lo que ve y cómo apuntar a la otra."""
        self.pestanas = {}
        self.store.pestanas = lambda: ["cc_gastos", "cc_usuarios", "Gastos 2025"]
        self._analizar()
        self.correr(hogar.render, self.ctx)
        codigos = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("code"))
        self.assertIn("Gastos 2025", codigos)        # lista de pestañas visibles
        self.assertIn("hoja_url_legacy", codigos)    # instrucción de configuración


class TestImportarDesdeArchivo(BaseVistas):
    """Subir el CSV evita leer Google: sólo una escritura en bloque."""

    CSV = (
        "Fecha;Quien;Concepto;Monto;Categoria\n"
        "05/10/2026;Ana;Compra Coto;48500;Supermercado\n"
        "12/10/2026;Bruno;Nafta;32000;Auto\n"
        "20/10/2026;Ana;Internet;21500;Internet\n"
    )

    class _Archivo:
        name = "gastos.csv"

        def __init__(self, datos: bytes) -> None:
            self._datos = datos

        def getvalue(self) -> bytes:
            return self._datos

    def setUp(self) -> None:
        super().setUp()
        self.lecturas = 0

        def leer(titulo: str):
            self.lecturas += 1
            return []

        self.store.leer_pestana = leer
        self.store.buscar_pestana_por_columnas = lambda columnas: None
        streamlit_falso.ARCHIVO_SUBIDO = self._Archivo(self.CSV.encode("utf-8"))

    def test_previsualiza_sin_leer_google(self):
        self.correr(hogar.render, self.ctx)
        textos = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("markdown"))
        self.assertIn("3 gasto(s)", textos)
        self.assertIn("102.000,00", textos)
        self.assertEqual(self.lecturas, 0)  # no se tocó la planilla
        self.assertEqual(self.fallos(), [])

    def test_importa_las_filas_del_archivo(self):
        filas, compras = migracion.leer_archivo("gastos.csv", self.CSV.encode("utf-8"))
        datos = self.ctx.hogar_ctl().analizar_filas(filas, compras).datos
        mapeo = {"Ana": datos["mapeo"].get("Ana") or self.usuario["id"]}
        mapeo["Bruno"] = self.usuario["id"]
        antes = len(self.repo.gastos(self.hogar["id"], self.usuario["id"]))

        resultado = self.ctx.hogar_ctl().importar_filas(filas, mapeo, compras=compras)

        self.assertTrue(resultado.ok, resultado.mensaje)
        self.assertEqual(resultado.datos.importados, 3)
        gastos = self.repo.gastos(self.hogar["id"], self.usuario["id"])
        self.assertEqual(len(gastos), antes + 3)
        self.assertIn("Internet", {g["concepto"] for g in gastos})

    def test_archivo_ilegible(self):
        streamlit_falso.ARCHIVO_SUBIDO = self._Archivo(b"")
        self.correr(hogar.render, self.ctx)
        errores = " ".join(str(args[0]) for (args, _) in streamlit_falso.llamadas("error"))
        self.assertIn("No pude leer el archivo", errores)


class TestCamaraDelTicket(BaseVistas):
    """Desde el celular se puede sacar la foto en el momento."""

    class _Foto:
        name = "camera_input.jpg"

        def __init__(self, datos: bytes) -> None:
            self._datos = datos

        def getvalue(self) -> bytes:
            return self._datos

    def setUp(self) -> None:
        super().setUp()
        self.foto = self._Foto(JPEG)

    def test_ofrece_sacar_foto(self):
        self.correr(gastos.render, self.ctx)
        opciones = " ".join(
            str(k.get("options")) for (_, k) in streamlit_falso.llamadas("radio")
        )
        self.assertIn("Sacar foto", opciones)

    def test_con_camara_elegida_abre_el_widget(self):
        streamlit_falso.ESTADO["cc_fuente_ticket"] = "📷 Sacar foto"
        streamlit_falso.ARCHIVO_SUBIDO = self.foto
        self.correr(gastos.render, self.ctx)
        self.assertTrue(streamlit_falso.llamadas("camera_input"))
        self.assertFalse(
            [c for c in streamlit_falso.llamadas("file_uploader") if c[1][0] == "Comprobante"]
        )

    def test_con_archivo_elegido_no_abre_la_camara(self):
        streamlit_falso.ESTADO["cc_fuente_ticket"] = "🖼️ Subir archivo"
        streamlit_falso.ARCHIVO_SUBIDO = self.foto
        self.correr(gastos.render, self.ctx)
        self.assertFalse(streamlit_falso.llamadas("camera_input"))

    def test_guarda_el_gasto_con_la_foto_de_la_camara(self):
        # Sin nombre de archivo útil: el formato se valida por la firma.
        self.foto.name = ""
        subido = gastos._archivo_subido(self.foto)
        self.assertEqual(subido[0], "foto.jpg")
        resultado = self.ctx.gastos().agregar(
            "Ticket con cámara", "1500", "Supermercado",
            self.usuario["id"], [self.usuario["id"]], archivo=subido,
        )
        self.assertTrue(resultado.ok, resultado.mensaje)
        comprobante = self.ctx.gastos().comprobante(resultado.datos["id"])
        self.assertTrue(comprobante.datos["bytes"])


class TestEspacioHuggingFace(unittest.TestCase):
    """El repo tiene que seguir sirviendo como Space (cabecera YAML en el README)."""

    def test_readme_con_metadatos_de_space(self):
        raiz = Path(__file__).resolve().parent.parent
        texto = (raiz / "README.md").read_text(encoding="utf-8")
        self.assertTrue(
            texto.startswith("---"), "el README debe empezar con la cabecera YAML"
        )
        cabecera = texto.split("---", 2)[1]
        # HF ya no ofrece el SDK de Streamlit: el Space va con Docker.
        self.assertIn("sdk: docker", cabecera)
        self.assertIn("app_port: 8501", cabecera)
        self.assertTrue((raiz / "app.py").exists())
        self.assertTrue((raiz / "requirements.txt").exists())
        self.assertTrue((raiz / "Dockerfile").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
