"""Vista pública: acceso (login y registro) con la información en un modal.

La página de entrada es sólo el acceso. Todo lo comercial —qué es, cómo funciona,
planes y preguntas— vive detrás del botón "Información", en un diálogo, para que
quien ya es usuario no tenga que scrollear media landing para entrar.
"""

from __future__ import annotations

import streamlit as st

from cuentasclaras.modelos import planes
from cuentasclaras.modelos.dinero import formatear

from .componentes import Contexto, css, entrar, pie


@st.dialog("Cuentas Claras", width="large")
def _informacion(ctx: Contexto) -> None:
    """Todo lo que antes ocupaba la landing, ahora en un modal."""
    st.markdown(
        "**Gastos compartidos sin planillas, sin cuentas a mano y sin discusiones.** "
        "Cargá quién pagó, dividí automático y sabé al instante quién le debe a quién."
    )

    st.markdown("#### Qué resuelve")
    st.markdown(
        "- ⚖️ **División automática:** cada gasto se reparte entre quienes corresponde "
        "y el saldo se recalcula solo.\n"
        "- 📎 **Comprobantes:** adjuntás la foto del ticket y queda visible sólo para "
        "las personas del hogar.\n"
        "- 🛒 **Lista de compras:** lo que falta en la casa, compartido y tildable "
        "desde el celular.\n"
        "- 🏡 **Varios hogares:** tu casa y la de un familiar, separadas, con roles y "
        "códigos de invitación."
    )

    st.markdown("#### Cómo funciona")
    st.markdown(
        "1. **Creá tu hogar.** Poné un nombre y listo.\n"
        "2. **Sumá a las personas.** Con un código de 6 caracteres.\n"
        "3. **Cargá y mirá.** Quién pagó qué, cuánto toca a cada uno y qué transferir."
    )

    st.markdown("#### Planes")
    gratis = planes.LIMITES[planes.GRATIS]
    pro = planes.LIMITES[planes.PRO]
    st.markdown(
        f"""
| | Gratis | Pro |
| --- | --- | --- |
| Precio | $0 | {formatear(ctx.config.precio_mensual_num, ctx.config.simbolo)}/mes o {formatear(ctx.config.precio_anual_num, ctx.config.simbolo)}/año |
| Hogares | {gratis['hogares']} | {pro['hogares']} |
| Personas por hogar | {gratis['miembros']} | {pro['miembros']} |
| Gastos por mes | {gratis['gastos_mes']} | Ilimitados |
| Historial | {ctx.config.historial_gratis_meses} meses | Completo |
| Comprobantes | {gratis['comprobantes_mes']}/mes | Ilimitados |
"""
    )
    st.caption(
        f"El plan anual ahorra {ctx.config.ahorro_anual_pct}%. El cobro se coordina "
        "por transferencia o link de pago; podés empezar gratis y pasar a Pro cuando quieras."
    )

    st.markdown("#### Preguntas")
    st.markdown(
        "**¿Sirve para compañeros de casa?** Sí: en cada gasto elegís entre quiénes se "
        "divide, así podés repartir el súper entre tres y el internet entre dos.\n\n"
        "**¿Y si pagué algo que era sólo para otra persona?** Esa persona queda "
        "debiendo el 100% de ese gasto.\n\n"
        "**¿Necesito instalar algo?** No, se usa desde el navegador del celular o la "
        "computadora.\n\n"
        "**¿Puedo llevarme mis datos?** Sí, desde «Mi cuenta» exportás CSV y JSON."
    )

    st.divider()
    st.caption(
        "🔒 **Privado por diseño:** cada hogar ve sólo sus datos, las contraseñas se "
        "guardan con `scrypt` y la información se guarda cifrada en el almacenamiento. "
        f"¿Dudas? {ctx.config.soporte_email}"
    )


def _acceso(ctx: Contexto) -> None:
    """Formularios de entrada y registro, en una tarjeta centrada."""
    col_izq, centro, col_der = st.columns([1, 1.2, 1], gap="large")
    with centro:
        st.markdown("## 💸 Cuentas Claras")
        st.caption("Gastos compartidos del hogar. Entrá o creá tu cuenta en un minuto.")
        st.write("")

        tab_login, tab_registro = st.tabs(["Ya tengo cuenta", "Crear cuenta gratis"])
        with tab_login:
            _entrar(ctx)
        with tab_registro:
            _registro(ctx)

        st.write("")
        if st.button("ℹ️ Información y planes", use_container_width=True):
            _informacion(ctx)


def _entrar(ctx: Contexto) -> None:
    with st.form("login"):
        email = st.text_input("Email", key="login_email", placeholder="vos@email.com")
        clave = st.text_input("Contraseña", type="password", key="login_clave")
        recordar = st.checkbox("Mantener la sesión abierta en este dispositivo", value=True)
        enviado = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if enviado:
        resultado = ctx.sesion().iniciar(email, clave, recordar=recordar)
        if resultado.ok and resultado.datos:
            entrar(ctx, resultado.datos)
        else:
            st.error(resultado.mensaje)
    st.caption(f"¿No te acordás la contraseña? Escribinos a {ctx.config.soporte_email}.")


def _registro(ctx: Contexto) -> None:
    if not ctx.config.registro_abierto:
        st.info(
            "Las inscripciones están cerradas por ahora. Escribinos a "
            f"{ctx.config.soporte_email} si querés probar el servicio."
        )
        return

    with st.form("registro"):
        nombre = st.text_input("Tu nombre", placeholder="Ana")
        email = st.text_input("Email", placeholder="vos@email.com")
        col_a, col_b = st.columns(2)
        clave = col_a.text_input("Contraseña", type="password", help="Mínimo 8 caracteres")
        clave2 = col_b.text_input("Repetir contraseña", type="password")
        codigo = st.text_input(
            "Código de invitación (opcional)",
            placeholder="ABC123",
            help="Si alguien ya te invitó a su hogar, pegalo acá.",
        )
        acepto = st.checkbox("Acepto los términos del servicio y la política de privacidad")
        enviado = st.form_submit_button(
            "Crear cuenta", type="primary", use_container_width=True
        )

    if not enviado:
        return
    resultado = ctx.sesion().registrar(nombre, email, clave, clave2, acepto, codigo)
    if resultado.ok and resultado.datos:
        entrar(ctx, resultado.datos)
    else:
        st.error(resultado.mensaje)


def render(ctx: Contexto) -> None:
    css()
    _acceso(ctx)
    st.write("")
    pie()
