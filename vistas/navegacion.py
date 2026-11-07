"""Vista de navegación lateral (hogar activo, secciones y sesión)."""

from __future__ import annotations

import streamlit as st

from cuentasclaras import BUILD, __version__
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

        # Navegación pedida por código (un solo uso): la sección "Ver planes" o
        # cualquier vista que quiera llevar a la persona a otro lado deja acá el
        # destino y recarga. Se consume ANTES de dibujar el radio.
        pedido = st.session_state.pop("cc_ir_a", None)
        if pedido in opciones:
            st.session_state["cc_navegacion"] = pedido

        # El estado del widget manda: si la persona eligió "Gastos", seguimos en
        # "Gastos" (ésta era la causa del rebote a Inicio). Sólo se descarta si
        # apunta a una sección que ya no existe (por ejemplo, perdió el rol admin).
        actual = st.session_state.get("cc_navegacion")
        if actual not in opciones:
            st.session_state.pop("cc_navegacion", None)
            actual = st.session_state.get("cc_pagina")
        if actual not in opciones:
            actual = opciones[0]

        elegida = st.radio(
            "Navegación",
            opciones,
            index=opciones.index(actual),
            key="cc_navegacion",
            label_visibility="collapsed",
        )
        st.session_state["cc_pagina"] = elegida

        st.divider()
        st.markdown(f"**{ctx.nombre or 'Cuenta'}**")
        st.caption((ctx.usuario or {}).get("email", ""))

        if ctx.config.almacen == "sheets":
            if st.button("🔄 Sincronizar", use_container_width=True, key="btn_sync"):
                limpiar = getattr(ctx.store, "limpiar_cache", None)
                if callable(limpiar):
                    limpiar()
                st.rerun()
            st.caption("Trae los últimos cambios de la planilla.")

        if st.button("Cerrar sesión", use_container_width=True):
            salir(ctx)

        if ctx.hogar and ctx.hogar["plan"] == planes.GRATIS:
            st.caption("¿Más hogares o historial completo? Pasate a Pro.")
            if st.button("Ver planes", use_container_width=True, key="btn_planes_sidebar"):
                st.session_state["cc_ir_a"] = "💳 Plan"
                st.rerun()

        st.caption(f"v{__version__} · {BUILD}")

    return elegida
