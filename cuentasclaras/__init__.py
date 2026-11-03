"""Cuentas Claras — gestión de gastos compartidos para hogares.

Organización (MVC):

* `cuentasclaras.modelos`       → datos, reglas de negocio y cifrado.
* `cuentasclaras.controladores` → casos de uso (validan y devuelven `Resultado`).
* `vistas`                      → pantallas Streamlit.

El paquete no importa Streamlit: se puede usar desde scripts, tests o una API sin
arrastrar la interfaz.
"""

__version__ = "2.0.0"
