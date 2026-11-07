"""Copia el proyecto a una carpeta de Hugging Face Space y lo deja listo para subir.

Uso típico:

    git clone https://huggingface.co/spaces/TU-USUARIO/cuentas-claras ../space-cc
    python tools/publicar_space.py --destino ../space-cc
    cd ../space-cc
    git add -A && git commit -m "Cuentas Claras" && git push

El script copia sólo lo que el Space necesita (app, paquete, vistas, requirements y
configuración de Streamlit) y **nunca** copia secretos, la base local ni las
pruebas. Con `--verificar` sólo chequea la carpeta, sin escribir.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ARCHIVOS = (
    "app.py",
    "requirements.txt",
    ".streamlit/config.toml",
    "README.md",
)
CARPETAS = ("cuentasclaras", "vistas")

# Nada de esto debe terminar en un Space público (`.git` sí, porque se usa para
# subir; `README.md` se copia a propósito con su cabecera).
PROHIBIDOS = (
    ".streamlit/secrets.toml",
    "data",
    "tests",
    "legacy",
    "docs",
    "web",
    "tools",
)


def _ignorar(directorio: str, nombres: list[str]) -> set[str]:
    return {
        nombre
        for nombre in nombres
        if nombre == "__pycache__" or nombre.endswith((".pyc", ".pyo"))
    }


def copiar(destino: Path) -> list[Path]:
    """Copia los archivos del Space a `destino` y devuelve lo copiado."""
    destino.mkdir(parents=True, exist_ok=True)
    copiados: list[Path] = []

    for nombre in ARCHIVOS:
        origen = RAIZ / nombre
        if not origen.exists():
            raise SystemExit(f"Falta {nombre} en el proyecto.")
        objetivo = destino / nombre
        objetivo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, objetivo)
        copiados.append(objetivo)

    for nombre in CARPETAS:
        origen = RAIZ / nombre
        if not origen.is_dir():
            raise SystemExit(f"Falta la carpeta {nombre} en el proyecto.")
        objetivo = destino / nombre
        if objetivo.exists():
            shutil.rmtree(objetivo)
        shutil.copytree(origen, objetivo, ignore=_ignorar)
        copiados.append(objetivo)

    return copiados


def verificar(destino: Path) -> list[str]:
    """Devuelve la lista de problemas (vacía = el Space está listo)."""
    problemas: list[str] = []
    for nombre in ARCHIVOS:
        if not (destino / nombre).exists():
            problemas.append(f"falta {nombre}")
    for nombre in CARPETAS:
        if not (destino / nombre).is_dir():
            problemas.append(f"falta la carpeta {nombre}")

    readme = destino / "README.md"
    if readme.exists():
        texto = readme.read_text(encoding="utf-8")
        partes = texto.split("---", 2) if texto.startswith("---") else []
        cabecera = partes[1] if len(partes) > 1 else ""
        if "sdk:" not in cabecera:
            problemas.append("el README no tiene la cabecera de Space (falta `sdk:`)")
        elif "sdk: docker" in cabecera and "app_port" not in cabecera:
            problemas.append("con `sdk: docker` falta `app_port: 8501` en la cabecera")

    for nombre in PROHIBIDOS:
        if (destino / nombre).exists():
            problemas.append(f"no debería estar en el Space: {nombre}")
    return problemas


def main(argv: list[str] | None = None) -> int:
    # Las consolas de Windows pueden no soportar todos los caracteres.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(description="Prepara una carpeta para Hugging Face Space")
    parser.add_argument("--destino", required=True, help="Carpeta del Space clonado")
    parser.add_argument("--verificar", action="store_true", help="Sólo revisa, no copia")
    args = parser.parse_args(argv)

    destino = Path(args.destino).expanduser().resolve()
    if not args.verificar:
        copiados = copiar(destino)
        print(f"Copiados {len(copiados)} elementos en {destino}")

    problemas = verificar(destino)
    if problemas:
        print("\nRevisá esto antes de subir:")
        for problema in problemas:
            print(f"  - {problema}")
        return 1

    print("\nTodo listo. Próximos pasos:")
    print(f"  cd {destino}")
    print('  git add -A && git commit -m "Cuentas Claras" && git push')
    print("\nY en el Space: Settings > Variables and secrets (ver docs/HUGGINGFACE.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
