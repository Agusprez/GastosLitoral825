"""Cuentas Claras — gastos compartidos del hogar.

Punto de entrada de la aplicación (Streamlit):

    streamlit run app.py

Arquitectura MVC:
    cuentasclaras/modelos/       -> datos, reglas y cifrado (M)
    cuentasclaras/controladores/ -> casos de uso, validación y mensajes (C)
    vistas/                      -> pantallas Streamlit (V)

Funciona sin configuración en modo local (SQLite + demo) y en producción usa
Google Sheets como base de datos, con los datos cifrados.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Cuentas Claras · gastos compartidos",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

from vistas import admin, compras, cuenta, gastos, hogar, inicio, landing, navegacion  # noqa: E402
from vistas import planes  # noqa: E402
from vistas.componentes import arrancar, css, pie, sin_hogar  # noqa: E402

PAGINAS = {
    "🏠 Inicio": inicio.render,
    "🧾 Gastos": gastos.render,
    "🛒 Compras": compras.render,
    "🏡 Hogar": hogar.render,
    "💳 Plan": planes.render,
    "👤 Mi cuenta": cuenta.render,
}
PAGINA_ADMIN = "🛠️ Plataforma"


def main() -> None:
    ctx = arrancar()
    css()

    if not ctx.usuario:
        landing.render(ctx)
        return

    if not ctx.hogar:
        sin_hogar(ctx)
        return

    paginas = dict(PAGINAS)
    if ctx.es_admin:
        paginas[PAGINA_ADMIN] = admin.render

    pagina = navegacion.render(ctx, paginas)
    if ctx.es_admin and ctx.config.cifrado and not ctx.origen_clave:
        st.warning(ctx.aviso_cifrado())

    renderizador = paginas.get(pagina, inicio.render)
    renderizador(ctx)
    pie()


main()
