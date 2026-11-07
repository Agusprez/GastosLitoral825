"""Cuentas Claras — gestión de gastos compartidos para hogares.

Organización (MVC):

* `cuentasclaras.modelos`       → datos, reglas de negocio y cifrado.
* `cuentasclaras.controladores` → casos de uso (validan y devuelven `Resultado`).
* `vistas`                      → pantallas Streamlit.

El paquete no importa Streamlit: se puede usar desde scripts, tests o una API sin
arrastrar la interfaz.
"""

__version__ = "2.1.0"

# Se muestra en la barra lateral para saber de un vistazo qué versión está
# desplegada (Streamlit Cloud a veces tarda en reiniciar tras un push).
BUILD = "2026-11-07 · comprobante como la v1"
