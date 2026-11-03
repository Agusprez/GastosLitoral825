"""Vista de la lista de compras compartida."""

from __future__ import annotations

import streamlit as st

from .componentes import Contexto, ejecutar, mostrar


def _alta(ctx: Contexto) -> None:
    with st.form("nueva_compra", clear_on_submit=True):
        col_texto, col_boton = st.columns([3, 1])
        texto = col_texto.text_input(
            "¿Qué hace falta?",
            placeholder="Detergente, leche, yerba…",
            label_visibility="collapsed",
        )
        enviado = col_boton.form_submit_button(
            "➕ Añadir", type="primary", use_container_width=True
        )
    if enviado:
        ejecutar(lambda: ctx.compras().agregar(texto), recargar=False)
        st.rerun()


def _items(ctx: Contexto, items: list[dict], ver_compradas: bool) -> None:
    if not items:
        st.success("✨ ¡No hay nada pendiente! La alacena está completa.")
        return

    for item in items:
        col_info, col_accion = st.columns([4, 1])
        comprada = item.get("comprada")
        if comprada:
            col_info.markdown(
                f"~~{item['texto']}~~ "
                f"<span class='cc-nota'>· lo compró "
                f"{item.get('comprado_por_nombre') or 'alguien'}</span>",
                unsafe_allow_html=True,
            )
            if col_accion.button("↩️", key=f"volver_{item['id']}", help="Volver a pendientes"):
                ejecutar(lambda: ctx.compras().marcar(item["id"], False), recargar=False)
                st.rerun()
        else:
            col_info.markdown(
                f"🛍️ **{item['texto']}**  \n"
                f"<span class='cc-nota'>lo anotó {item.get('anotado_por_nombre', '—')}</span>",
                unsafe_allow_html=True,
            )
            botones = col_accion.columns(2)
            if botones[0].button("✅", key=f"ok_{item['id']}", help="Marcar como comprado"):
                ejecutar(lambda: ctx.compras().marcar(item["id"], True), recargar=False)
                st.rerun()
            if botones[1].button("🗑️", key=f"del_{item['id']}", help="Borrar de la lista"):
                ejecutar(lambda: ctx.compras().borrar(item["id"]), recargar=False)
                st.rerun()


def render(ctx: Contexto) -> None:
    ctx.exigir_hogar()
    st.markdown("### 🛒 Lista de compras")
    st.caption("Cualquiera del hogar puede anotar, tildar o borrar ítems.")

    _alta(ctx)

    ver_compradas = st.toggle("Ver también lo ya comprado", value=False, key="cc_ver_compradas")
    resultado = ctx.compras().listar(incluir_compradas=ver_compradas)
    if not resultado.ok:
        mostrar(resultado)
        return
    items = (resultado.datos or {}).get("items", [])
    pendientes = (resultado.datos or {}).get("compras_pendientes", 0)

    st.markdown(f"**{pendientes} pendiente(s)**")
    st.divider()
    _items(ctx, items, ver_compradas)

    if ver_compradas and any(i.get("comprada") for i in items):
        st.divider()
        if st.button("🧹 Limpiar las compradas", use_container_width=False):
            ejecutar(ctx.compras().limpiar_compradas)
