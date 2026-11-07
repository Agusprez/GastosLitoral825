"""Tests del publicador de Hugging Face Space (sin red ni git)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import publicar_space


class TestPublicarSpace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.destino = Path(self._tmp.name) / "space"
        self.copiados = publicar_space.copiar(self.destino)

    def test_copia_lo_necesario(self):
        for nombre in ("app.py", "requirements.txt", "README.md"):
            self.assertTrue((self.destino / nombre).exists(), nombre)
        self.assertTrue((self.destino / ".streamlit" / "config.toml").exists())
        self.assertTrue((self.destino / "vistas").is_dir())
        self.assertTrue(
            (self.destino / "cuentasclaras" / "modelos" / "repositorio.py").exists()
        )

    def test_no_copia_secretos_ni_basura(self):
        for nombre in ("data", "tests", "legacy", "docs", "web", "tools"):
            self.assertFalse((self.destino / nombre).exists(), nombre)
        self.assertFalse((self.destino / ".streamlit" / "secrets.toml").exists())
        self.assertEqual(list(self.destino.rglob("__pycache__")), [])
        self.assertEqual(list(self.destino.rglob("*.pyc")), [])

    def test_verificacion_limpia(self):
        self.assertEqual(publicar_space.verificar(self.destino), [])

    def test_detecta_readme_sin_cabecera(self):
        (self.destino / "README.md").write_text("# sin cabecera\n", encoding="utf-8")
        problemas = " ".join(publicar_space.verificar(self.destino))
        self.assertIn("cabecera", problemas)

    def test_detecta_faltantes(self):
        (self.destino / "app.py").unlink()
        problemas = " ".join(publicar_space.verificar(self.destino))
        self.assertIn("app.py", problemas)


if __name__ == "__main__":
    unittest.main(verbosity=2)
