"""Vista de gastos: alta, listado con filtros, detalle editable y comprobantes."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from cuentasclaras.modelos.dinero import hoy

from .componentes import Contexto, aplicar, ejecutar, formato_mes, mostrar

CATEGORIAS = (
    "Supermercado", "Servicios", "Internet", "Auto", "Salidas",
    "Casa", "Salud", "Mascotas", "Otros",
)


# --------------------------------------------------------------------------- #
# Alta
# --------------------------------------------------------------------------- #
def _archivo_subido(subido: Any) -> tuple[str, bytes] | None:
    if subido is None:
        return None
    return (subido.name, subido.getvalue())


def _formulario(ctx: Contexto, miembros: list[dict[str, Any]]) -> None:
    nombres = {m["usuario_id"]: m["nombre"] for m in miembros}
    ids = list(nombres)
    yo = ctx.usuario["id"]

    st.markdown("### Registrar un gasto")
    with st.form("nuevo_gasto", clear_on_submit=True):
        col1, col2 = st.columns(2)
        fecha = col1.date_input("Fecha", value=hoy(), max_value=hoy(), format="DD/MM/YYYY")
        monto = col2.number_input(
            "Monto", min_value=0.0, step=100.0, format="%.2f", help="En pesos"
        )
        col3, col4 = st.columns([3, 2])
        concepto = col3.text_input("Detalle", placeholder="Compra semanal en Coto")
        categoria = col4.selectbox("Categoría", CATEGORIAS)
        col5, col6 = st.columns(2)
        quien = col5.selectbox(
            "¿Quién pagó?",
            ids,
            index=ids.index(yo) if yo in ids else 0,
            format_func=lambda i: nombres[i],
        )
        entre = col6.multiselect(
            "¿Entre quiénes se divide?",
            ids,
            default=ids,
            format_func=lambda i: nombres[i],
            help="Si pagaste algo sólo para otra persona, dejá únicamente a esa persona.",
        )
        subido = st.file_uploader(
            "Comprobante (opcional)", type=["jpg", "jpeg", "png", "webp"]
        )
        enviado = st.form_submit_button(
            "Guardar gasto", type="primary", use_container_width=True
        )

    if not enviado:
        return
    ejecutar(
        lambda: ctx.gastos().agregar(
            concepto,
            monto,
            categoria,
            quien,
            entre or ids,
            fecha=fecha,
            archivo=_archivo_subido(subido),
        )
    )


# --------------------------------------------------------------------------- #
# Filtros y tabla
# --------------------------------------------------------------------------- #
def _filtros(ctx: Contexto, miembros: list[dict[str, Any]]) -> dict[str, Any]:
    meses = ctx.gastos().meses()
    opciones = {m: formato_mes(m) for m in meses}
    opciones[""] = "Histórico completo"
    nombres = {m["usuario_id"]: m["nombre"] for m in miembros}

    col1, col2, col3, col4 = st.columns([1.2, 1, 1, 1.6])
    mes = col1.selectbox(
        "Período",
        list(opciones),
        format_func=lambda k: opciones[k],
        key="cc_filtro_mes",
    )
    categoria = col2.selectbox(
        "Categoría", ["Todas"] + list(CATEGORIAS), key="cc_filtro_categoria"
    )
    persona = col3.selectbox(
        "Pagó",
        ["Todos"] + list(nombres),
        format_func=lambda i: "Todos" if i == "Todos" else nombres[i],
        key="cc_filtro_persona",
    )
    texto = col4.text_input("Buscar en el detalle", key="cc_filtro_texto")
    return {
        "mes": mes,
        "historico": mes == "",
        "categoria": None if categoria == "Todas" else categoria,
        "persona": None if persona == "Todos" else persona,
        "texto": texto,
    }


def _tabla(ctx: Contexto, gastos: list[dict[str, Any]], nombres: dict[str, str]) -> list[int]:
    filas = []
    for gasto in gastos:
        filas.append(
            {
                "Fecha": gasto["fecha_dt"].strftime("%d/%m/%Y"),
                "Detalle": gasto["concepto"],
                "Categoría": gasto["categoria"],
                "Quién pagó": gasto.get(
                    "pagado_por_nombre", nombres.get(gasto.get("pagado_por", ""), "")
                ),
                "Entre": len(gasto.get("participantes", [])),
                "Monto": ctx.dinero(gasto["monto"]),
                "Ticket": "📎" if gasto.get("comprobante") else "—",
            }
        )
    evento = st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        use_container_width=True,
        selection_mode="single-row",
        on_select="rerun",
        key="cc_tabla_gastos",
    )
    try:
        return list(evento.selection.rows)
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------- #
# Detalle (modal)
# --------------------------------------------------------------------------- #
@st.dialog("Detalle del gasto")
def _detalle(ctx: Contexto, gasto_id: str, miembros: list[dict[str, Any]]) -> None:
    resultado = ctx.gastos().detalle(gasto_id)
    if not resultado.ok:
        mostrar(resultado)
        return
    gasto = resultado.datos or {}
    nombres = {m["usuario_id"]: m["nombre"] for m in miembros}
    ids = list(nombres) or [ctx.usuario["id"]]

    comprobante = ctx.gastos().comprobante(gasto_id)
    datos_comprobante = (comprobante.datos or {}) if comprobante.ok else {}
    contenido = datos_comprobante.get("bytes")
    if contenido:
        st.image(contenido, caption="Comprobante")
        st.download_button(
            "⬇️ Descargar comprobante",
            data=contenido,
            file_name=datos_comprobante.get("nombre", "comprobante.jpg"),
            mime=datos_comprobante.get("mime", "image/jpeg"),
            use_container_width=True,
        )
    elif datos_comprobante.get("ref", "").startswith("http"):
        st.image(datos_comprobante["ref"], caption="Comprobante (versión anterior)")
        st.caption("Este comprobante está alojado en un servicio externo de la versión 1.")
    else:
        st.caption("Este gasto no tiene comprobante adjunto.")

    st.write("---")
    with st.form("editar_gasto"):
        concepto = st.text_input("Detalle", value=gasto.get("concepto", ""))
        col1, col2 = st.columns(2)
        monto = col1.number_input(
            "Monto", min_value=0.0, value=float(gasto.get("monto", 0)), step=100.0, format="%.2f"
        )
        categoria_actual = gasto.get("categoria", "Otros")
        categoria = col2.selectbox(
            "Categoría",
            CATEGORIAS,
            index=CATEGORIAS.index(categoria_actual) if categoria_actual in CATEGORIAS else len(CATEGORIAS) - 1,
        )
        col3, col4 = st.columns(2)
        fecha = col3.date_input(
            "Fecha",
            value=gasto.get("fecha_dt", hoy()),
            max_value=hoy(),
            format="DD/MM/YYYY",
        )
        pagador_actual = gasto.get("pagado_por", ids[0])
        quien = col4.selectbox(
            "Quién pagó",
            ids,
            index=ids.index(pagador_actual) if pagador_actual in ids else 0,
            format_func=lambda i: nombres.get(i, i),
        )
        participantes = st.multiselect(
            "Entre quiénes se divide",
            ids,
            default=[p for p in gasto.get("participantes", []) if p in ids],
            format_func=lambda i: nombres.get(i, i),
        )
        nuevo_comprobante = st.file_uploader(
            "Reemplazar comprobante (opcional)", type=["jpg", "jpeg", "png", "webp"]
        )
        guardar = st.form_submit_button("💾 Guardar cambios", type="primary", use_container_width=True)

    if guardar:
        st.session_state["cc_dialogo_cerrado"] = gasto_id
        aplicar(
            ctx.gastos().editar(
                gasto_id,
                concepto=concepto,
                monto=monto,
                categoria=categoria,
                pagado_por=quien,
                participantes=participantes or ids,
                fecha=fecha,
                archivo=_archivo_subido(nuevo_comprobante),
            )
        )

    with st.expander("Eliminar este gasto"):
        st.caption("El gasto deja de contar en los saldos. Queda registrado en la actividad.")
        if st.button("🗑️ Eliminar gasto", type="secondary", use_container_width=True):
            st.session_state["cc_dialogo_cerrado"] = gasto_id
            aplicar(ctx.gastos().anular(gasto_id))


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(ctx: Contexto) -> None:
    ctx.exigir_hogar()
    st.markdown("### 🧾 Gastos")

    miembros = ctx.gastos().miembros()
    if not miembros:
        st.info("Sumá a alguien al hogar para empezar a cargar gastos.")
        return

    tab_lista, tab_nuevo = st.tabs(["📋 Movimientos", "➕ Cargar gasto"])
    with tab_nuevo:
        _formulario(ctx, miembros)
    with tab_lista:
        filtros = _filtros(ctx, miembros)
        listado = ctx.gastos().listar(
            mes=filtros["mes"],
            historico=filtros["historico"],
            categoria=filtros["categoria"],
            persona=filtros["persona"],
            texto=filtros["texto"],
        )
        if not listado.ok:
            mostrar(listado)
            return
        datos = listado.datos or {}
        gastos = datos.get("gastos", [])
        nombres = datos.get("nombres", {})

        col_a, col_b = st.columns([1, 1])
        col_a.metric("Total filtrado", ctx.dinero(datos.get("total", 0)))
        col_b.metric("Movimientos", datos.get("cantidad", 0))

        if not gastos:
            st.info("No hay gastos con esos filtros.")
        else:
            seleccion = _tabla(ctx, gastos, nombres)
            st.caption(
                "Hacé clic en una fila para ver el comprobante, editarla o eliminarla. "
                f"Mostrando {len(gastos)} movimiento(s)."
            )
            if seleccion:
                gasto = gastos[seleccion[0]]
                if st.session_state.get("cc_dialogo_cerrado") != gasto["id"]:
                    _detalle(ctx, gasto["id"], miembros)

        with st.expander("⬇️ Exportar"):
            exportado = ctx.gastos().exportar_csv(
                mes=filtros["mes"], historico=filtros["historico"]
            )
            if exportado.ok:
                st.download_button(
                    "Descargar CSV de este período",
                    data=(exportado.datos or {}).get("csv", ""),
                    file_name=(exportado.datos or {}).get("nombre", "gastos.csv"),
                    mime="text/csv",
                    use_container_width=True,
                )
            st.caption("El CSV abre en Excel o Google Sheets sin conversiones.")
