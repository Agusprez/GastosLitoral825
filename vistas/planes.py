"""Vista de planes y límites (y pedido de upgrade)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cuentasclaras.modelos import planes

from .componentes import Contexto, pill, mostrar


def _uso(etiqueta: str, actual: int, tope: int | None) -> None:
    if tope is None:
        st.markdown(f"**{etiqueta}**: {actual} · *sin límite*")
        return
    st.markdown(f"**{etiqueta}**: {actual} de {tope}")
    st.progress(min(actual / max(tope, 1), 1.0))


def _solicitud(ctx: Contexto, estado: dict) -> None:
    if estado.get("es_pro"):
        st.success("🎉 Este hogar ya tiene el plan Pro. ¡Gracias por bancar el proyecto!")
        return

    st.markdown("### Pasar a Pro")
    st.caption(
        "El cobro se coordina por transferencia o link de pago. Apenas se acredita, "
        "activamos el plan y te avisamos."
    )
    col1, col2 = st.columns(2)
    with col1:
        mensual = ctx.config.precio_mensual_num
        st.metric("Pro mensual", ctx.dinero(mensual), help="Por hogar, cancelás cuando quieras")
        pedido = ctx.planes().pedido("mensual")
        st.link_button("Pedir Pro mensual", pedido["mailto"], use_container_width=True)
    with col2:
        anual = ctx.config.precio_anual_num
        st.metric(
            "Pro anual",
            ctx.dinero(anual),
            delta=f"-{ctx.config.ahorro_anual_pct}%",
            delta_color="normal",
        )
        pedido_anual = ctx.planes().pedido("anual")
        st.link_button("Pedir Pro anual", pedido_anual["mailto"], use_container_width=True)

    with st.expander("¿Qué incluye exactamente?"):
        for fila in estado["comparativa"]:
            st.markdown(
                f"**{fila['caracteristica']}** — Gratis: {fila['gratis']} · "
                f"Pro: {fila['pro']}"
            )


def render(ctx: Contexto) -> None:
    ctx.exigir_hogar()
    resultado = ctx.planes().estado()
    if not resultado.ok:
        mostrar(resultado)
        return
    estado = resultado.datos or {}
    uso = estado["uso"]
    plan = estado["plan"]

    st.markdown("## 💳 Plan del hogar")
    st.markdown(
        f"{pill(estado['etiqueta'], gris=plan == planes.GRATIS)} "
        f"<span class='cc-nota'>· {planes.DESCRIPCION.get(plan, '')}</span>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("### Consumo actual")
    _uso("Hogares propios", uso["hogares"], estado["limites"]["hogares"])
    _uso("Personas en este hogar", uso["miembros"], estado["limites"]["miembros"])
    _uso("Gastos este mes", uso["gastos_mes"], estado["limites"]["gastos_mes"])
    historial = estado["historial_meses"]
    st.markdown(
        f"**Historial consultable**: {'completo' if historial is None else str(historial) + ' meses'}"
    )

    st.divider()
    st.markdown("### Comparación")
    st.dataframe(
        pd.DataFrame(estado["comparativa"]).rename(
            columns={"caracteristica": "Característica", "gratis": "Gratis", "pro": "Pro"}
        ),
        hide_index=True,
        use_container_width=True,
    )

    st.divider()
    _solicitud(ctx, estado)
