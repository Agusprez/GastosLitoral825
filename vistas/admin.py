"""Vista del panel de plataforma (sólo staff de Cuentas Claras)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cuentasclaras.modelos import planes

from .componentes import Contexto, ejecutar, mostrar


def _metricas(resumen: dict) -> None:
    columnas = st.columns(4, gap="medium")
    columnas[0].metric("Personas", resumen["usuarios"])
    columnas[1].metric("Hogares", resumen["hogares"])
    columnas[2].metric("Hogares Pro", resumen["hogares_pro"])
    columnas[3].metric("MRR estimado", f"${resumen['mrr']:,.0f}".replace(",", "."))


def _usuarios(ctx: Contexto, usuarios: list[dict]) -> None:
    st.markdown("### Personas registradas")
    filas = [
        {
            "Nombre": u.get("nombre", ""),
            "Email": u.get("email", ""),
            "Hogares": u.get("hogares", ""),
            "Alta": str(u.get("creado_en", ""))[:10],
            "Último ingreso": str(u.get("ultimo_login", ""))[:16].replace("T", " ") or "—",
            "Activo": "Sí" if u.get("activo_booleano") else "No",
            "Admin": "Sí" if u.get("es_admin_plataforma") else "",
        }
        for u in usuarios
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    st.divider()
    nombres = {u["id"]: f"{u.get('nombre','')} ({u.get('email','')})" for u in usuarios}
    elegido = st.selectbox("Elegir persona", list(nombres), format_func=lambda i: nombres[i])
    actual = next((u for u in usuarios if u["id"] == elegido), {})
    activo = bool(actual.get("activo_booleano"))
    col1, col2 = st.columns(2)
    if col1.button("Deshabilitar cuenta" if activo else "Habilitar cuenta", use_container_width=True):
        ejecutar(lambda: ctx.admin().alternar_usuario(elegido, not activo))
    col2.caption(
        "Deshabilitar cierra todas sus sesiones y le impide entrar. No borra sus datos."
    )


def _hogares(ctx: Contexto, hogares: list[dict]) -> None:
    st.markdown("### Hogares")
    filas = [
        {
            "Hogar": h.get("nombre", ""),
            "Plan": planes.etiqueta(h.get("plan")),
            "Personas": h.get("miembros", 0),
            "Gastos": h.get("gastos", 0),
            "Propietario": h.get("propietario", ""),
            "Creado": str(h.get("creado_en", ""))[:10],
        }
        for h in hogares
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    st.divider()
    nombres = {h["id"]: h.get("nombre", "") for h in hogares}
    if not nombres:
        return
    elegido = st.selectbox("Elegir hogar", list(nombres), format_func=lambda i: nombres[i])
    destino = st.selectbox(
        "Plan",
        [planes.GRATIS, planes.PRO],
        format_func=planes.etiqueta,
        index=0,
    )
    if st.button("Aplicar plan", type="primary"):
        ejecutar(lambda: ctx.admin().cambiar_plan(elegido, destino))


def _salud(ctx: Contexto) -> None:
    st.markdown("### Estado del servicio")
    info = ctx.admin().almacen()
    col1, col2, col3 = st.columns(3)
    col1.metric("Almacenamiento", info["almacen"])
    col2.metric("Comprobantes", info["medios"])
    col3.metric("Cifrado", "Activo" if ctx.origen_clave else "Sin clave")
    st.caption(f"Almacén: {info['descripcion']}")
    if ctx.origen_clave:
        st.caption(f"Clave de cifrado: {ctx.origen_clave}")
    else:
        st.warning(ctx.aviso_cifrado() or "El cifrado está desactivado por configuración.")
    st.caption(
        "Las claves y las sesiones se guardan hasheadas. Si cambiás la clave de cifrado, "
        "los datos anteriores dejan de poder leerse."
    )


def render(ctx: Contexto) -> None:
    if not ctx.es_admin:
        st.error("Esta sección es sólo para administración de la plataforma.")
        return

    resultado = ctx.admin().datos()
    if not resultado.ok:
        mostrar(resultado)
        return
    datos = resultado.datos or {}
    resumen = datos["resumen"]

    st.markdown("## 🛠️ Panel de la plataforma")
    st.caption("Métricas del servicio, alta de planes y estado técnico.")
    _metricas(resumen)

    tab_usuarios, tab_hogares, tab_salud = st.tabs(["Personas", "Hogares", "Servicio"])
    with tab_usuarios:
        _usuarios(ctx, datos["usuarios"])
    with tab_hogares:
        _hogares(ctx, datos["hogares"])
    with tab_salud:
        _salud(ctx)
