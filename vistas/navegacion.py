"""Vista de navegación lateral (hogar activo, secciones y sesión)."""

from __future__ import annotations

import streamlit as st

from cuentasclaras.modelos import planes

from .componentes import Contexto, cambiar_hogar, pill, salir


def render(ctx: Contexto, paginas: dict[str, str]) -> str:
    """Dibuja la sidebar y devuelve la etiqueta de la página elegida."""
    with st.sidebar:
        st.markdown(f"### 💸 {ctx.config.app_nombre}")

        hogares = ctx.repo.hogares_de(ctx.usuario["id"]) if ctx.usuario else []
        if len(hogares) > 1:
            nombres = {h["id"]: h["nombre"] for h in hogares}
            ids = list(nombres)
            actual = ctx.hogar["id"] if ctx.hogar else ids[0]
            eleccion = st.selectbox(
                "Hogar",
                ids,
                index=ids.index(actual) if actual in ids else 0,
                format_func=lambda i: nombres[i],
                key="cc_selector_hogar",
            )
            if eleccion != actual:
                cambiar_hogar(ctx, eleccion)
        elif hogares:
            st.markdown(f"**{hogares[0]['nombre']}**")

        if ctx.hogar:
            etiqueta = planes.etiqueta(ctx.hogar["plan"])
            rol = (ctx.hogar.get("rol") or "miembro").capitalize()
            st.markdown(
                f"{pill(etiqueta, gris=ctx.hogar['plan'] == planes.GRATIS)} "
                f"{pill(rol, gris=True)}",
                unsafe_allow_html=True,
            )

        st.divider()

        opciones = list(paginas)
        destino = st.session_state.get("cc_pagina")
        # Si otra parte de la app pidió cambiar de sección (por ejemplo el botón
        # "Ver planes"), sincronizamos el estado del widget antes de dibujarlo.
        if destino in opciones and st.session_state.get("cc_navegacion") != destino:
            st.session_state["cc_navegacion"] = destino
        if destino not in opciones:
            destino = opciones[0]
        elegida = st.radio(
            "Navegación",
            opciones,
            index=opciones.index(destino),
            key="cc_navegacion",
            label_visibility="collapsed",
        )
        st.session_state["cc_pagina"] = elegida

        st.divider()
        st.markdown(f"**{ctx.nombre or 'Cuenta'}**")
        st.caption((ctx.usuario or {}).get("email", ""))

        if st.button("Cerrar sesión", use_container_width=True):
            salir(ctx)

        if ctx.hogar and ctx.hogar["plan"] == planes.GRATIS:
            st.caption("¿Más hogares o historial completo? Pasate a Pro.")
            if st.button("Ver planes", use_container_width=True, key="btn_planes_sidebar"):
                st.session_state["cc_pagina"] = "💳 Plan"
                st.rerun()

    return elegida
