"""Vista de inicio: balance del período, gráfico y últimos movimientos."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from cuentasclaras.modelos import planes

from .componentes import Contexto, ejecutar, formato_mes, mostrar

PALETA = [
    "#0f766e", "#14b8a6", "#f59e0b", "#fb7185",
    "#6366f1", "#84cc16", "#f97316", "#94a3b8",
]
CATEGORIAS = (
    "Supermercado", "Servicios", "Internet", "Auto", "Salidas",
    "Casa", "Salud", "Mascotas", "Otros",
)


def _pyplot():
    """Matplotlib es opcional: si no está, el gráfico se dibuja con barras CSS."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except Exception:  # noqa: BLE001 - ImportError o backend roto
        return None


def _elegir_periodo(ctx: Contexto) -> tuple[str, bool]:
    meses = ctx.resumen().meses()
    opciones = {m: formato_mes(m) for m in meses}
    opciones[""] = "Histórico completo"
    claves = list(opciones)
    elegido = st.selectbox(
        "Período",
        claves,
        index=0,
        format_func=lambda k: opciones[k],
        key="cc_periodo_inicio",
        label_visibility="collapsed",
    )
    return elegido, elegido == ""


def _cargar_rapido(ctx: Contexto, datos: dict) -> None:
    miembros = datos.get("miembros") or []
    if not miembros:
        return
    nombres = {m["usuario_id"]: m["nombre"] for m in miembros}
    ids = list(nombres)
    yo = ctx.usuario["id"]
    with st.expander("➕ Cargar un gasto rápido", expanded=False):
        with st.form("carga_rapida", clear_on_submit=True):
            col1, col2, col3 = st.columns([2, 1, 1])
            concepto = col1.text_input("Detalle", placeholder="Supermercado Coto")
            monto = col2.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
            categoria = col3.selectbox("Categoría", CATEGORIAS)
            col4, col5 = st.columns(2)
            quien = col4.selectbox(
                "¿Quién pagó?",
                ids,
                index=ids.index(yo) if yo in ids else 0,
                format_func=lambda i: nombres[i],
            )
            entre = col5.multiselect(
                "Entre quiénes",
                ids,
                default=ids,
                format_func=lambda i: nombres[i],
            )
            enviado = st.form_submit_button(
                "Guardar gasto", type="primary", use_container_width=True
            )
        if enviado:
            ejecutar(
                lambda: ctx.gastos().agregar(
                    concepto, monto, categoria, quien, entre or ids
                )
            )


def _metricas(ctx: Contexto, datos: dict) -> None:
    neto = datos.get("mi_neto", Decimal("0"))
    if neto > 0:
        etiqueta, valor = "Te deben", ctx.dinero(neto)
    elif neto < 0:
        etiqueta, valor = "Debés", ctx.dinero(-neto)
    else:
        etiqueta, valor = "Estás al día", ctx.dinero(0)

    columnas = st.columns(4, gap="medium")
    columnas[0].metric("Total del período", ctx.dinero(datos["total"]))
    columnas[1].metric("Movimientos", datos["cantidad"])
    columnas[2].metric(etiqueta, valor)
    columnas[3].metric("Compras pendientes", datos["compras_pendientes"])


def _balance(ctx: Contexto, datos: dict) -> None:
    saldos = datos["saldos"]
    nombres = datos["nombres"]
    st.markdown("#### ⚖️ Balance del período")
    columnas = st.columns(max(1, len(saldos)), gap="medium")
    for columna, (usuario_id, valores) in zip(columnas, saldos.items()):
        neto = valores["neto"]
        if neto > 0:
            texto, ayuda = f"+{ctx.dinero(neto)}", "le deben"
        elif neto < 0:
            texto, ayuda = f"-{ctx.dinero(-neto)}", "debe"
        else:
            texto, ayuda = ctx.dinero(0), "al día"
        columna.metric(nombres.get(usuario_id, "—"), texto, help=ayuda)
        columna.caption(
            f"Pagó {ctx.dinero_md(valores['pagado'])} · "
            f"le corresponde {ctx.dinero_md(valores['parte'])}"
        )

    transferencias = datos["transferencias"]
    if transferencias:
        for transferencia in transferencias:
            st.info(
                f"💸 **{transferencia['de_nombre']}** le transfiere "
                f"**{ctx.dinero_md(transferencia['monto'])}** a "
                f"**{transferencia['a_nombre']}**"
            )
        _registrar_pago(ctx, datos)
    elif datos["cantidad"]:
        st.success("✨ Están al día: nadie le debe nada a nadie en este período.")


def _registrar_pago(ctx: Contexto, datos: dict) -> None:
    miembros = datos.get("miembros") or []
    if len(miembros) < 2:
        return
    nombres = {m["usuario_id"]: m["nombre"] for m in miembros}
    ids = list(nombres)
    primera = datos["transferencias"][0]
    with st.expander("Registrar que ya se pagó"):
        with st.form("registrar_pago"):
            col1, col2 = st.columns(2)
            de = col1.selectbox(
                "Pagó",
                ids,
                index=ids.index(primera["de"]) if primera["de"] in ids else 0,
                format_func=lambda i: nombres[i],
            )
            a = col2.selectbox(
                "A",
                ids,
                index=ids.index(primera["a"]) if primera["a"] in ids else min(1, len(ids) - 1),
                format_func=lambda i: nombres[i],
            )
            col3, col4 = st.columns(2)
            monto = col3.number_input(
                "Monto",
                min_value=0.0,
                value=float(primera["monto"]),
                step=100.0,
                format="%.2f",
            )
            nota = col4.text_input("Nota (opcional)", placeholder="Transferencia MP")
            enviado = st.form_submit_button("Registrar pago", use_container_width=True)
        if enviado:
            ejecutar(
                lambda: ctx.hogar_ctl().registrar_pago(de, a, monto, nota=nota)
            )


def _grafico(ctx: Contexto, datos: dict) -> None:
    categorias = datos["por_categoria"]
    if not categorias:
        st.info("Todavía no hay gastos en este período. Cargá el primero arriba ☝️")
        return

    plt = _pyplot()
    st.markdown("#### 🍰 Gastos por categoría")
    if plt is None:
        total = float(datos["total"]) or 1.0
        for categoria, monto in categorias.items():
            st.markdown(f"**{categoria}** · {ctx.dinero_md(monto)}")
            st.progress(min(float(monto) / total, 1.0))
        return

    etiquetas = list(categorias)[::-1]
    valores = [float(v) for v in categorias.values()][::-1]
    figura, eje = plt.subplots(figsize=(6, max(2.2, 0.45 * len(etiquetas) + 1)))
    figura.patch.set_alpha(0.0)
    eje.patch.set_alpha(0.0)
    colores = [PALETA[i % len(PALETA)] for i in range(len(etiquetas))]
    barras = eje.barh(etiquetas, valores, color=colores, height=0.62)
    eje.set_xticks([])
    for lado in ("top", "right", "bottom"):
        eje.spines[lado].set_visible(False)
    eje.spines["left"].set_color("#cbd5e1")
    eje.tick_params(axis="y", length=0, labelsize=10)
    total = float(datos["total"]) or 1.0
    for barra, valor in zip(barras, valores):
        eje.text(
            barra.get_width() + total * 0.012,
            barra.get_y() + barra.get_height() / 2,
            ctx.dinero_corto(valor),
            va="center",
            fontsize=9,
            color="#334155",
        )
    eje.set_xlim(0, max(valores) * 1.25 if valores else 1)
    st.pyplot(figura)
    plt.close(figura)


def _ultimos(ctx: Contexto, datos: dict) -> None:
    gastos = datos["gastos"][:8]
    if not gastos:
        return
    st.markdown("#### 🧾 Últimos movimientos")
    filas = [
        {
            "Fecha": gasto["fecha_dt"].strftime("%d/%m"),
            "Detalle": gasto["concepto"],
            "Categoría": gasto["categoria"],
            "Quién pagó": gasto.get("pagado_por_nombre", ""),
            "Monto": ctx.dinero(gasto["monto"]),
        }
        for gasto in gastos
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.caption("El detalle completo, con edición y comprobantes, está en «Gastos».")


def render(ctx: Contexto) -> None:
    hogar = ctx.exigir_hogar()
    st.markdown(f"### 🏠 {hogar['nombre']}")
    if hogar["plan"] == planes.GRATIS:
        st.caption(
            f"Plan Gratis · {hogar['miembros']} de "
            f"{planes.LIMITES[planes.GRATIS]['miembros']} personas · "
            f"historial de {ctx.config.historial_gratis_meses} meses"
        )

    mes, historico = _elegir_periodo(ctx)
    st.caption(f"Mostrando: {formato_mes('' if historico else mes)}")

    resultado = ctx.resumen().panel(mes if not historico else "", historico)
    if not resultado.ok:
        mostrar(resultado)
        return
    datos = resultado.datos or {}

    if datos.get("recortado"):
        st.warning(
            "Tu plan Gratis muestra los últimos "
            f"{ctx.config.historial_gratis_meses} meses. Con el plan Pro ves "
            "todo el historial."
        )

    _cargar_rapido(ctx, datos)
    _metricas(ctx, datos)
    st.divider()
    _balance(ctx, datos)
    st.divider()

    col_grafico, col_categorias = st.columns([1.4, 1], gap="large")
    with col_grafico:
        _grafico(ctx, datos)
    with col_categorias:
        st.markdown("#### Detalle por categoría")
        if datos["por_categoria"]:
            total = float(datos["total"]) or 1.0
            for categoria, monto in datos["por_categoria"].items():
                porcentaje = float(monto) / total * 100
                st.markdown(
                    f"**{categoria}** · {ctx.dinero_md(monto)} "
                    f"<span class='cc-nota'>({porcentaje:.0f}%)</span>",
                    unsafe_allow_html=True,
                )
                st.progress(min(porcentaje / 100, 1.0))
        else:
            st.caption("Sin datos en el período.")

    st.divider()
    _ultimos(ctx, datos)
