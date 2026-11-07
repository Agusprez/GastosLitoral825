"""Tests de comprobantes: imgbb (servicio de la v1), Drive, disco y elección."""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from cuentasclaras.modelos import archivos
from cuentasclaras.modelos.configuracion import armar

JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)


class Respuesta:
    def __init__(self, status_code: int = 200, payload=None, texto: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = texto
        self.content = payload if isinstance(payload, bytes) else b""

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class Cliente:
    def __init__(self, respuesta_post=None, respuesta_get=None) -> None:
        self.respuesta_post = respuesta_post
        self.respuesta_get = respuesta_get
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def post(self, url, data=None, timeout=None, **kwargs):
        self.posts.append((url, data or {}))
        if isinstance(self.respuesta_post, Exception):
            raise self.respuesta_post
        return self.respuesta_post

    def get(self, url, timeout=None, **kwargs):
        self.gets.append(url)
        if isinstance(self.respuesta_get, Exception):
            raise self.respuesta_get
        return self.respuesta_get


def respuesta_ok(url="https://i.ibb.co/abc123/ticket.jpg"):
    return Respuesta(200, {"data": {"url": url, "display_url": url}, "success": True})


class TestImgbb(unittest.TestCase):
    def test_sube_con_la_clave_y_devuelve_la_url(self):
        cliente = Cliente(respuesta_post=respuesta_ok())
        medios = archivos.MediosImgbb("mi-clave", cliente=cliente)
        referencia = medios.guardar("hogar1", JPEG, "ticket.jpg")

        self.assertEqual(referencia, "https://i.ibb.co/abc123/ticket.jpg")
        self.assertEqual(len(cliente.posts), 1)
        url, carga = cliente.posts[0]
        self.assertEqual(url, archivos.MediosImgbb.URL_SUBIDA)
        self.assertEqual(carga["key"], "mi-clave")
        # La imagen viaja en base64 y sigue siendo una imagen válida.
        self.assertTrue(base64.b64decode(carga["image"]).startswith(b"\xff\xd8\xff"))

    def test_error_de_la_api(self):
        cliente = Cliente(
            respuesta_post=Respuesta(400, {"error": {"message": "Invalid API key"}})
        )
        medios = archivos.MediosImgbb("clave-mala", cliente=cliente)
        with self.assertRaises(archivos.ErrorArchivo) as contexto:
            medios.guardar("h", JPEG, "ticket.jpg")
        mensaje = str(contexto.exception)
        self.assertIn("400", mensaje)
        self.assertIn("Invalid API key", mensaje)

    def test_respuesta_inesperada(self):
        cliente = Cliente(respuesta_post=Respuesta(200, {"ok": True}))
        medios = archivos.MediosImgbb("k", cliente=cliente)
        with self.assertRaises(archivos.ErrorArchivo):
            medios.guardar("h", JPEG, "ticket.jpg")

    def test_sin_url_en_la_respuesta(self):
        cliente = Cliente(respuesta_post=Respuesta(200, {"data": {}}))
        medios = archivos.MediosImgbb("k", cliente=cliente)
        with self.assertRaises(archivos.ErrorArchivo):
            medios.guardar("h", JPEG, "ticket.jpg")

    def test_error_de_red(self):
        cliente = Cliente(respuesta_post=OSError("sin conexión"))
        medios = archivos.MediosImgbb("k", cliente=cliente)
        with self.assertRaises(archivos.ErrorArchivo) as contexto:
            medios.guardar("h", JPEG, "ticket.jpg")
        self.assertIn("imgbb", str(contexto.exception))

    def test_archivo_invalido_no_llega_a_la_red(self):
        cliente = Cliente(respuesta_post=respuesta_ok())
        medios = archivos.MediosImgbb("k", cliente=cliente)
        with self.assertRaises(archivos.ErrorArchivo):
            medios.guardar("h", b"MZ\x90\x00 ejecutable", "virus.jpg")
        self.assertEqual(cliente.posts, [])

    def test_sin_clave_falla_al_construir(self):
        with self.assertRaises(archivos.ErrorArchivo):
            archivos.MediosImgbb("")

    def test_lee_la_imagen_remota_y_la_cachea(self):
        cliente = Cliente(respuesta_get=Respuesta(200, JPEG))
        medios = archivos.MediosImgbb("k", cliente=cliente)
        url = "https://i.ibb.co/cache-test/ticket.jpg"
        self.assertEqual(medios.leer(url), JPEG)
        self.assertEqual(medios.leer(url), JPEG)
        self.assertEqual(cliente.gets, [url])  # segunda vez: desde la caché

    def test_leer_otras_referencias(self):
        medios = archivos.MediosImgbb("k", cliente=Cliente())
        self.assertIsNone(medios.leer("local:h1/foto.jpg"))
        self.assertIsNone(medios.leer("drive:abc"))

    def test_descarga_fallida_devuelve_none(self):
        medios = archivos.MediosImgbb("k", cliente=Cliente(respuesta_get=Respuesta(404)))
        self.assertIsNone(medios.leer("https://i.ibb.co/roto.jpg"))

    def test_borrar_no_hace_nada(self):
        medios = archivos.MediosImgbb("k", cliente=Cliente())
        self.assertIsNone(medios.borrar("https://i.ibb.co/x.jpg"))


class TestEleccionDeMedios(unittest.TestCase):
    def test_imgbb_por_tener_api_key(self):
        config = armar({"almacen": "memoria", "imgbb_api_key": "abc"})
        self.assertEqual(config.medios, "imgbb")
        self.assertIsInstance(archivos.construir(config), archivos.MediosImgbb)

    def test_medios_explicito_gana(self):
        config = armar({"almacen": "memoria", "imgbb_api_key": "abc", "medios": "local"})
        self.assertEqual(config.medios, "local")
        self.assertIsInstance(archivos.construir(config), archivos.MediosLocal)

    def test_drive_si_hay_carpeta(self):
        config = armar(
            {
                "almacen": "memoria",
                "drive_carpeta_id": "carpeta",
                "gcp_credenciales": {"type": "service_account"},
            }
        )
        self.assertEqual(config.medios, "drive")

    def test_local_por_defecto(self):
        config = armar({"almacen": "memoria"})
        self.assertEqual(config.medios, "local")

    def test_prioridad_imgbb_sobre_drive(self):
        config = armar(
            {
                "almacen": "memoria",
                "imgbb_api_key": "abc",
                "drive_carpeta_id": "carpeta",
                "gcp_credenciales": {"type": "service_account"},
            }
        )
        self.assertEqual(config.medios, "imgbb")


class TestDisco(unittest.TestCase):
    def test_guardar_y_leer_local(self):
        with tempfile.TemporaryDirectory() as carpeta:
            medios = archivos.MediosLocal(Path(carpeta))
            referencia = medios.guardar("hogar1", JPEG, "ticket.jpg")
            self.assertTrue(referencia.startswith("local:"))
            self.assertTrue(medios.leer(referencia))
            medios.borrar(referencia)
            self.assertIsNone(medios.leer(referencia))


class TestTamanoDeFoto(unittest.TestCase):
    """Las fotos de celular pesan varios MB: se aceptan y se comprimen."""

    def test_acepta_foto_grande_y_la_comprime(self):
        grande = JPEG + b"\x00" * (6 * 1024 * 1024)  # ~6 MB
        contenido, mime = archivos.comprimir(grande, "foto.jpg", 10)
        self.assertEqual(mime, "image/jpeg")
        self.assertLess(len(contenido), len(grande))

    def test_rechaza_entradas_enormes(self):
        enorme = JPEG + b"\x00" * (6 * 1024 * 1024)
        with self.assertRaises(archivos.ErrorArchivo) as contexto:
            archivos.comprimir(enorme, "foto.jpg", 1)  # tope 1 MB → entrada 4 MB
        self.assertIn("grande", str(contexto.exception))

    def test_limite_final_del_archivo(self):
        """Si después de comprimir no baja del tope, se avisa."""
        original = archivos.optimizar
        archivos.optimizar = lambda datos, ext: (datos, "image/jpeg")
        try:
            with self.assertRaises(archivos.ErrorArchivo):
                archivos.comprimir(JPEG + b"\x00" * (3 * 1024 * 1024), "foto.jpg", 1)
        finally:
            archivos.optimizar = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
