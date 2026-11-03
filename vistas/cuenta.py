"""Vista de la cuenta personal: perfil, contraseña, sesiones y baja."""

from __future__ import annotations

import streamlit as st

from .componentes import Contexto, aplicar, ejecutar, mostrar


def _perfil(ctx: Contexto) -> None:
    perfil = ctx.cuenta().perfil()
    if not perfil.ok:
        mostrar(perfil)
        return
    usuario = perfil.datos or {}

    st.markdown("### 👤 Mis datos")
    with st.form("perfil"):
        nombre = st.text_input("Nombre", value=usuario.get("nombre", ""))
        email = st.text_input("Email", value=usuario.get("email", ""))
        guardar = st.form_submit_button("Guardar", type="primary")
    if guardar:
        resultado = ctx.cuenta().actualizar(nombre, email)
        if resultado.ok:
            st.session_state["cc_usuario_id"] = (resultado.datos or {}).get("id", "")
        aplicar(resultado)

    st.caption(f"Cuenta creada el {str(usuario.get('creado_en', ''))[:10]} · "
               f"último ingreso {str(usuario.get('ultimo_login', ''))[:16].replace('T', ' ') or '—'}")


def _clave(ctx: Contexto) -> None:
    st.markdown("### 🔑 Contraseña")
    sesiones = ctx.cuenta().sesiones_activas()
    st.caption(f"Tenés {sesiones} sesión(es) abierta(s) en este momento.")

    with st.form("cambiar_clave"):
        actual = st.text_input("Contraseña actual", type="password")
        nueva = st.text_input("Nueva contraseña", type="password", help="Mínimo 8 caracteres")
        repetir = st.text_input("Repetir la nueva", type="password")
        guardar = st.form_submit_button("Cambiar contraseña", type="primary")
    if guardar:
        resultado = ctx.cuenta().cambiar_clave(
            actual, nueva, repetir, token=ctx.token
        )
        aplicar(resultado, recargar=resultado.ok)

    if st.button("Cerrar las sesiones de otros dispositivos"):
        ejecutar(lambda: ctx.cuenta().cerrar_otras_sesiones(ctx.token))


def _exportar(ctx: Contexto) -> None:
    st.markdown("### ⬇️ Mis datos")
    st.caption("Exportá lo que hay en el hogar activo. Podés cambiarlo desde la barra lateral.")
    col1, col2 = st.columns(2)
    csv_resultado = ctx.gastos().exportar_csv()
    if csv_resultado.ok:
        col1.download_button(
            "Gastos en CSV",
            data=(csv_resultado.datos or {}).get("csv", ""),
            file_name="mis_gastos.csv",
            mime="text/csv",
            use_container_width=True,
        )
    json_resultado = ctx.gastos().exportar_json()
    if json_resultado.ok:
        col2.download_button(
            "Respaldo completo (JSON)",
            data=(json_resultado.datos or {}).get("json", ""),
            file_name="respaldo_hogar.json",
            mime="application/json",
            use_container_width=True,
        )


def _baja(ctx: Contexto) -> None:
    st.markdown("### 🗑️ Eliminar mi cuenta")
    with st.expander("Quiero eliminar mi cuenta"):
        st.error(
            "Se borran tu usuario y los gastos que cargaste. Si sos propietario de un "
            "hogar con más personas, primero transferí la propiedad."
        )
        with st.form("eliminar_cuenta"):
            clave = st.text_input("Confirmá con tu contraseña", type="password")
            seguro = st.checkbox("Entiendo que esta acción no se puede deshacer")
            borrar = st.form_submit_button("Eliminar mi cuenta", type="secondary")
        if borrar and seguro:
            resultado = ctx.cuenta().eliminar(clave, token=ctx.token)
            if resultado.ok:
                for clave_sesion in ("cc_usuario_id", "cc_token", "cc_hogar_id"):
                    st.session_state.pop(clave_sesion, None)
            aplicar(resultado)


def render(ctx: Contexto) -> None:
    st.markdown("## 👤 Mi cuenta")
    tab_perfil, tab_clave, tab_datos, tab_baja = st.tabs(
        ["Perfil", "Contraseña", "Datos", "Baja"]
    )
    with tab_perfil:
        _perfil(ctx)
    with tab_clave:
        _clave(ctx)
    with tab_datos:
        _exportar(ctx)
    with tab_baja:
        _baja(ctx)
