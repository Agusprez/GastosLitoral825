"""Alias de compatibilidad para Streamlit Cloud.

La versión 1 desplegaba `gastos.py` como archivo principal. A partir de la v2 el
punto de entrada es `app.py`, pero muchas apps ya configuradas siguen apuntando
acá: este archivo sólo ejecuta `app.py` para que el despliegue siga funcionando
sin tocar la configuración del panel de Streamlit.

Recomendación: en Streamlit Cloud → *Settings → Main file path*, poner `app.py` y
este alias deja de ser necesario.
"""

import runpy
from pathlib import Path

ENTRADA = Path(__file__).resolve().parent / "app.py"
runpy.run_path(str(ENTRADA), run_name="__main__")
