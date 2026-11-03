"""Cifra los datos que ya estaban guardados en texto plano.

Cuando activás el cifrado en una instalación que ya tenía datos (por ejemplo, la
planilla con las pestañas `cc_*` creadas sin clave), las filas viejas siguen
legibles. Este script las vuelve a escribir pasando por el cifrador.

Uso:
    python tools/cifrar_existente.py --aplicar
    python tools/cifrar_existente.py            # sólo informa

Necesita la misma configuración que la app (`.streamlit/secrets.toml` o variables
`CUENTASCLARAS_*`). Hacé una copia de la planilla antes de correrlo.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cuentasclaras.modelos import cifrado  # noqa: E402
from cuentasclaras.modelos.almacen import TABLAS  # noqa: E402
from cuentasclaras.modelos.configuracion import armar  # noqa: E402
from cuentasclaras.modelos.fabrica import abrir_almacen  # noqa: E402


def leer_secretos(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    with ruta.open("rb") as archivo:
        return tomllib.load(archivo)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cifra los datos existentes.")
    parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios")
    parser.add_argument("--secrets", default=str(RAIZ / ".streamlit" / "secrets.toml"))
    args = parser.parse_args()

    config = armar(leer_secretos(Path(args.secrets)))
    store, origen = abrir_almacen(config)
    if not origen:
        print("No hay clave de cifrado configurada: no hay nada que hacer.")
        print("Generá una con `python tools/generar_clave.py` y agregala a los secretos.")
        return 1

    print(f"Cifrado activo (clave: {origen})")
    print(f"Almacén: {store.ping()}\n")

    if not isinstance(store, cifrado.AlmacenCifrado):
        print("El almacén no está envuelto en cifrado; revisá la configuración.")
        return 1

    total = 0
    for tabla in TABLAS:
        filas = store.all(tabla)
        pendientes = 0
        for fila in filas:
            crudo = store.crudo.uno(tabla, fila["id"]) or {}
            if any(cifrado.es_cifrado(valor) for valor in crudo.values()):
                continue
            pendientes += 1
            if args.aplicar:
                store.update(tabla, fila["id"], fila)
        total += pendientes
        print(f"  {tabla:<14} {len(filas):>5} filas · {pendientes:>5} sin cifrar")

    if args.aplicar:
        print(f"\nListo: {total} fila(s) cifradas.")
    else:
        print(f"\nInforme: {total} fila(s) se cifrarían. Volvé a correr con --aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
