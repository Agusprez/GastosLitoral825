"""Vista pública: landing y acceso.

Streamlit no es una web de marketing (sin SEO ni rutas amigables), así que la
landing vive dentro de la app; además `web/landing.html` tiene una versión
estática para publicar aparte y linkear al servicio.
"""

from __future__ import annotations

import streamlit as st

from cuentasclaras.modelos import planes
from cuentasclaras.modelos.dinero import formatear

from .componentes import Contexto, css, entrar, pie, tarjeta


def _hero(ctx: Contexto) -> None:
    st.markdown(
        f"""
        <div class="cc-hero">
          <h1>💸 {ctx.config.app_nombre}</h1>
          <p>Gastos compartidos sin planillas, sin cuentas a mano y sin discusiones.
          Cargá quién pagó, dividí automático y sabé al instante quién le debe a quién.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    columnas = st.columns(3, gap="large")
    with columnas[0]:
        st.markdown(
            tarjeta(
                "División automática",
                "Cada gasto se reparte entre quienes corresponde y el saldo se recalcula solo.",
                "⚖️",
            ),
            unsafe_allow_html=True,
        )
    with columnas[1]:
        st.markdown(
            tarjeta(
                "Comprobantes privados",
                "Adjuntá la foto del ticket. Sólo las personas del hogar pueden verla.",
                "📎",
            ),
            unsafe_allow_html=True,
        )
    with columnas[2]:
        st.markdown(
            tarjeta(
                "Lista de compras",
                "Lo que falta en la casa, compartido y tildable desde el celular.",
                "🛒",
            ),
            unsafe_allow_html=True,
        )


def _como_funciona() -> None:
    st.markdown("### Cómo funciona")
    pasos = st.columns(3, gap="large")
    with pasos[0]:
        st.markdown("**1. Creá tu hogar**  \nPoné un nombre y listo. Podés tener más de uno.")
    with pasos[1]:
        st.markdown("**2. Sumá a las personas**  \nCon un código de 6 caracteres, sin vueltas.")
    with pasos[2]:
        st.markdown(
            "**3. Cargá y mirá**  \nQuién pagó qué, cuánto toca a cada uno y qué transferir."
        )


def _precios(ctx: Contexto) -> None:
    st.markdown("### Planes")
    gratis, pro_mes, pro_anio = st.columns(3, gap="large")
    with gratis:
        st.markdown(
            f"""<div class="cc-card">
            <h4>Gratis</h4>
            <div class="cc-precio">$0</div>
            <p class="cc-nota">para siempre</p>
            <p style="margin-top:.6rem">1 hogar · hasta {planes.LIMITES[planes.GRATIS]['miembros']} personas ·
            {planes.LIMITES[planes.GRATIS]['gastos_mes']} gastos por mes ·
            {ctx.config.historial_gratis_meses} meses de historial</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with pro_mes:
        st.markdown(
            f"""<div class="cc-card">
            <h4>Pro mensual</h4>
            <div class="cc-precio">{formatear(ctx.config.precio_mensual_num, ctx.config.simbolo)}</div>
            <p class="cc-nota">por mes, por hogar</p>
            <p style="margin-top:.6rem">{planes.LIMITES[planes.PRO]['hogares']} hogares ·
            hasta {planes.LIMITES[planes.PRO]['miembros']} personas · gastos y comprobantes
            ilimitados · historial completo</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with pro_anio:
        st.markdown(
            f"""<div class="cc-card">
            <h4>Pro anual <span class="cc-pill">-{ctx.config.ahorro_anual_pct}%</span></h4>
            <div class="cc-precio">{formatear(ctx.config.precio_anual_num, ctx.config.simbolo)}</div>
            <p class="cc-nota">por año <span class="cc-tachado">
            {formatear(ctx.config.precio_mensual_num * 12, ctx.config.simbolo)}</span></p>
            <p style="margin-top:.6rem">Todo lo de Pro, pagando 10 meses en vez de 12.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    st.caption(
        "El cobro se coordina por transferencia o link de pago mientras no esté "
        "integrada la pasarela. Podés empezar gratis y pasar a Pro cuando quieras."
    )


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
    st.caption(
        f"¿No te acordás la contraseña? Escribinos a {ctx.config.soporte_email} "
        "y te ayudamos a recuperar la cuenta."
    )


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
        clave2 = col_b.text_input("Repetí la contraseña", type="password")
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
    _hero(ctx)

    col_info, col_acceso = st.columns([1.15, 1], gap="large")
    with col_acceso:
        st.markdown("### Entrá o creá tu cuenta")
        tab_login, tab_registro = st.tabs(["Ya tengo cuenta", "Crear cuenta gratis"])
        with tab_login:
            _entrar(ctx)
        with tab_registro:
            _registro(ctx)

    with col_info:
        _como_funciona()
        st.markdown("")
        st.markdown(
            tarjeta(
                "Privado por diseño",
                "Cada hogar ve sólo sus datos. Las contraseñas se guardan cifradas "
                "con scrypt y la información se guarda cifrada en el almacenamiento.",
                "🔒",
            ),
            unsafe_allow_html=True,
        )
        st.markdown("")
        if ctx.config.almacen == "sheets":
            st.caption(
                "Datos alojados en Google Sheets, cifrados con ChaCha20 "
                "(sin la clave no se pueden leer)."
            )
        else:
            st.caption("Datos alojados en la base de datos del servidor, cifrados en reposo.")

    _precios(ctx)

    st.markdown("### Preguntas frecuentes")
    with st.expander("¿Sirve para una pareja, una familia o compañeros de casa?"):
        st.write(
            "Sí. Los gastos se dividen entre las personas que elijas en cada movimiento, "
            "así que podés repartir 50/50 con tu pareja o dividir sólo la compra del súper "
            "entre tres compañeros de departamento."
        )
    with st.expander("¿Qué pasa si alguien pagó algo que no era para todos?"):
        st.write(
            "Al cargar el gasto elegís entre quiénes se divide. Si pagaste un regalo sólo "
            "para otra persona, esa persona queda debiendo el 100%."
        )
    with st.expander("¿Puedo exportar mis datos?"):
        st.write(
            "Sí, desde «Mi cuenta» podés descargar un CSV de los movimientos y un JSON "
            "con el hogar completo."
        )
    with st.expander("¿Dónde quedan mis datos si el servicio cierra?"):
        st.write(
            "Son tuyos: podés exportarlos cuando quieras. Si los datos están en una "
            "planilla de Google, además quedan en tu propio Drive."
        )

    st.markdown("---")
    pie()
