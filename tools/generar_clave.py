"""Genera una clave de cifrado para Cuentas Claras.

Uso:
    python tools/generar_clave.py

Pegá el resultado en `.streamlit/secrets.toml` como `clave_cifrado` (o en la
variable de entorno `CUENTASCLARAS_CLAVE_CIFRADO`) y **guardala también fuera del
servidor**: si la perdés, los datos cifrados no se pueden recuperar.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cuentasclaras.modelos.cifrado import generar_clave


def main() -> int:
    clave = generar_clave()
    print("Clave de cifrado generada:\n")
    print(f'clave_cifrado = "{clave}"\n')
    print("Guardala en un gestor de contraseñas. No la subas al repositorio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
