"""Vista del hogar: personas, invitaciones, ajustes y actividad."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from cuentasclaras.modelos import planes
from cuentasclaras.modelos.dinero import formatear_fecha

from .componentes import Contexto, aplicar, ejecutar, mostrar, pill

ROLES_ETIQUETA = {
    "propietario": "Propietario/a",
    "admin": "Administrador/a",
    "miembro": "Miembro",
}


def _miembros(ctx: Contexto, datos: dict) -> None:
    miembros = datos["miembros"]
    st.markdown(f"### 👥 Personas ({len(miembros)})")
    st.caption(
        f"El plan {datos['etiqueta_plan']} permite hasta "
        f"{datos['limite_miembros']} personas por hogar."
    )

    filas = [
        {
            "Nombre": m["nombre"],
            "Rol": ROLES_ETIQUETA.get(m["rol"], m["rol"]),
            "Desde": str(m.get("unido_en", ""))[:10],
            "Email": m["email"],
        }
        for m in miembros
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    if not datos["puedo_administrar"]:
        st.info("Sólo quien administra el hogar puede cambiar roles o quitar personas.")
        return

    otros = [m for m in miembros if m["usuario_id"] != ctx.usuario["id"]]
    if not otros:
        st.caption("Todavía no hay otras personas en el hogar. Generá un código de invitación.")
        return

    st.divider()
    nombres = {m["usuario_id"]: m["nombre"] for m in otros}
    elegido = st.selectbox(
        "Persona",
        list(nombres),
        format_func=lambda i: nombres[i],
        key="cc_hogar_persona",
    )
    rol_actual = next((m["rol"] for m in otros if m["usuario_id"] == elegido), "miembro")
    col1, col2, col3 = st.columns(3)
    nuevo_rol = col1.selectbox(
        "Rol",
        ["admin", "miembro"],
        index=0 if rol_actual == "admin" else 1,
        format_func=lambda r: ROLES_ETIQUETA.get(r, r),
        key="cc_hogar_rol",
    )
    if col1.button("Cambiar rol", use_container_width=True):
        ejecutar(lambda: ctx.hogar_ctl().cambiar_rol(elegido, nuevo_rol))
    if col2.button("Quitar del hogar", use_container_width=True):
        ejecutar(lambda: ctx.hogar_ctl().quitar(elegido))
    if datos["es_propietario"] and col3.button(
        "Transferir propiedad", use_container_width=True
    ):
        ejecutar(lambda: ctx.hogar_ctl().transferir(elegido))

    if not datos["es_propietario"]:
        st.divider()
        with st.expander("Salir de este hogar"):
            st.caption("Vas a dejar de ver los gastos. Tu historial de cargas se mantiene.")
            if st.button("Salir del hogar", type="secondary"):
                resultado = ctx.hogar_ctl().salir()
                if resultado.ok:
                    st.session_state.pop("cc_hogar_id", None)
                aplicar(resultado)


def _invitaciones(ctx: Contexto, datos: dict) -> None:
    st.markdown("### 🔗 Invitaciones")
    if not datos["puedo_administrar"]:
        st.info("Sólo quien administra el hogar puede generar códigos.")
        return
    st.caption(
        "Compartí el código con quien quieras sumar. Vence y tiene un límite de usos."
    )

    with st.form("nueva_invitacion"):
        col1, col2, col3 = st.columns(3)
        rol = col1.selectbox(
            "Rol al entrar",
            ["miembro", "admin"],
            format_func=lambda r: ROLES_ETIQUETA.get(r, r),
        )
        dias = col2.number_input("Vence en (días)", min_value=1, max_value=90, value=14)
        usos = col3.number_input("Usos permitidos", min_value=1, max_value=50, value=10)
        enviado = st.form_submit_button("Generar código", type="primary")
    if enviado:
        resultado = ctx.hogar_ctl().invitar(rol, int(dias), int(usos))
        if resultado.ok:
            datos_invitacion = resultado.datos or {}
            st.session_state["cc_ultima_invitacion"] = {
                "codigo": datos_invitacion.get("codigo", ""),
                "expira_en": datos_invitacion.get("expira_en", ""),
            }
            st.rerun()
        else:
            mostrar(resultado)

    ultima = st.session_state.get("cc_ultima_invitacion")
    if ultima:
        _mensaje_whatsapp(ctx, ultima.get("codigo", ""), ultima.get("expira_en", ""))
        if st.button("Listo, ocultar"):
            st.session_state.pop("cc_ultima_invitacion", None)
            st.rerun()

    vigentes = [i for i in datos["invitaciones"] if i.get("vigente")]
    if not vigentes:
        st.caption("No hay códigos activos.")
        return
    st.markdown("#### Códigos activos")
    for invitacion in vigentes:
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.markdown(f"`{invitacion['codigo']}`")
        col2.caption(
            f"{ROLES_ETIQUETA.get(invitacion['rol'], invitacion['rol'])} · "
            f"{invitacion['usos']}/{invitacion['usos_max']} usos · "
            f"vence {str(invitacion['expira_en'])[:10]}"
        )
        if col3.button("Revocar", key=f"rev_{invitacion['id']}"):
            ejecutar(lambda: ctx.hogar_ctl().revocar(invitacion["id"]))
        with st.expander(f"📲 Mensaje para WhatsApp · {invitacion['codigo']}"):
            _mensaje_whatsapp(ctx, invitacion["codigo"], invitacion.get("expira_en", ""))


def _mensaje_whatsapp(ctx: Contexto, codigo: str, expira_en: str = "") -> None:
    """Muestra el código y el mensaje listo para copiar/pegar en WhatsApp."""
    resultado = ctx.hogar_ctl().mensaje_invitacion(codigo, expira_en)
    if not resultado.ok:
        mostrar(resultado)
        return
    datos = resultado.datos or {}

    st.markdown(
        f'<div class="cc-codigo">{datos.get("codigo", codigo)}</div>',
        unsafe_allow_html=True,
    )

    url = (ctx.config.url_publica or "").strip()
    if not url:
        st.warning(
            "El mensaje sale **sin el link de acceso** porque falta `url_publica` en "
            "los Secretos. Agregá esta línea —importante: **antes** de cualquier "
            "sección entre corchetes, como `[gcp_service_account]`, porque en TOML "
            "lo que sigue a un encabezado pertenece a esa sección— y reiniciá la app:"
        )
        st.code('url_publica = "https://litoral825.streamlit.app"', language="toml")
    else:
        st.caption(f"Link de acceso que va en el mensaje: {url}")

    st.caption(
        "Copiá el mensaje con el ícono de la esquina, o abrí WhatsApp directamente "
        "con el texto cargado. Si la persona ya tiene cuenta, puede pegar el código "
        "en «Unirme a otro hogar» (abajo, en esta misma sección)."
    )
    st.code(datos.get("mensaje", ""), language=None)
    st.link_button(
        "📲 Abrir WhatsApp con este mensaje",
        datos.get("enlace", "https://wa.me/"),
        use_container_width=True,
    )


def _ajustes(ctx: Contexto, datos: dict) -> None:
    hogar = datos["hogar"]
    st.markdown("### ⚙️ Ajustes del hogar")

    with st.form("renombrar_hogar"):
        nombre = st.text_input("Nombre del hogar", value=hogar.get("nombre", ""))
        guardar = st.form_submit_button("Guardar nombre", type="primary")
    if guardar:
        resultado = ctx.hogar_ctl().renombrar(nombre)
        if resultado.ok:
            aplicar(resultado)

    st.divider()
    st.markdown("#### Exportar los datos")
    st.caption("Tus datos son tuyos: descargalos cuando quieras.")
    col1, col2 = st.columns(2)
    exportado = ctx.gastos().exportar_csv()
    if exportado.ok:
        col1.download_button(
            "⬇️ Gastos en CSV",
            data=(exportado.datos or {}).get("csv", ""),
            file_name="gastos_hogar.csv",
            mime="text/csv",
            use_container_width=True,
        )
    respaldo = ctx.gastos().exportar_json()
    if respaldo.ok:
        col2.download_button(
            "⬇️ Respaldo completo (JSON)",
            data=(respaldo.datos or {}).get("json", ""),
            file_name="respaldo_hogar.json",
            mime="application/json",
            use_container_width=True,
        )

    st.divider()
    if datos["es_propietario"]:
        _importar_v1(ctx)
    st.divider()
    st.markdown("#### Zona peligrosa")
    if datos["es_propietario"]:
        with st.expander("Eliminar este hogar"):
            st.error(
                "Se borran los gastos, la lista de compras, los pagos y las invitaciones. "
                "No se puede deshacer."
            )
            with st.form("eliminar_hogar"):
                confirmacion = st.text_input(
                    f'Escribí «{hogar.get("nombre", "")}» para confirmar'
                )
                borrar = st.form_submit_button("Eliminar definitivamente", type="secondary")
            if borrar:
                resultado = ctx.hogar_ctl().eliminar(confirmacion)
                if resultado.ok:
                    st.session_state.pop("cc_hogar_id", None)
                    aplicar(resultado)
                else:
                    mostrar(resultado)
    else:
        st.caption("Sólo el propietario o la propietaria puede eliminar el hogar.")


def _importar_v1(ctx: Contexto) -> None:
    """Trae las pestañas de la v1 (`Gastos`, `Lista_Compras`) al hogar activo."""
    with st.expander("📥 Importar los gastos de la planilla anterior"):
        st.caption(
            "Trae al hogar las pestañas viejas «Gastos» y «Lista_Compras» de la misma "
            "planilla. No borra ni modifica esas pestañas: sólo lee."
        )

        ultimo = st.session_state.pop("cc_import_informe", None)
        if ultimo is not None:
            st.success(
                f"Importamos {ultimo.importados} gasto(s)"
                + (f" y {ultimo.compras} compra(s)." if ultimo.compras else ".")
            )
            if ultimo.omitidos:
                st.warning(f"Quedaron {ultimo.omitidos} fila(s) sin importar.")
            for aviso in ultimo.errores[:5]:
                st.caption(f"· {aviso}")
            if len(ultimo.errores) > 5:
                st.caption(f"· y {len(ultimo.errores) - 5} aviso(s) más")

        analisis = ctx.hogar_ctl().analizar_importacion()
        if not analisis.ok:
            mostrar(analisis)
            return
        info = analisis.datos or {}
        if not info.get("filas") and not info.get("compras"):
            _sin_pestanas(ctx, info)
            return

        informe = info["informe"]
        if info.get("origen") == "externa":
            st.caption(
                "Leyendo la planilla anterior configurada en `hoja_url_legacy`."
            )
        elif info.get("origen") == "por_columnas":
            st.caption(
                "La pestaña tiene otro nombre, pero la reconocí por sus columnas "
                "(Fecha, Quien, Concepto, Monto)."
            )
        if info.get("ya_importado"):
            st.warning(
                "Este hogar ya importó estos datos el "
                f"{str(info['ya_importado'])[:16].replace('T', ' ')}. "
                "Si volvés a importar se van a duplicar."
            )
        st.markdown(
            f"**{info['filas']} fila(s) en «Gastos»** · {ctx.dinero_md(informe.total)} · "
            f"del {formatear_fecha(informe.desde)} al {formatear_fecha(informe.hasta)}"
            + (f" · {info['compras']} compra(s) pendientes" if info.get("compras") else "")
        )

        miembros = info.get("miembros") or []
        nombres = {m["usuario_id"]: m["nombre"] for m in miembros}
        ids = list(nombres)
        if not ids:
            st.info("Primero sumá personas al hogar.")
            return

        st.markdown("**¿Quién es quién?**")
        mapeo: dict[str, str] = {}
        for nombre_detectado, cantidad in informe.personas.items():
            propuesto = info.get("mapeo", {}).get(nombre_detectado, "")
            indice = ids.index(propuesto) + 1 if propuesto in ids else 0
            elegido = st.selectbox(
                f"«{nombre_detectado}» ({cantidad} gastos)",
                [""] + ids,
                index=indice,
                format_func=lambda i: nombres.get(i, "— no importar estos gastos —"),
                key=f"cc_map_{nombre_detectado}",
            )
            if elegido:
                mapeo[nombre_detectado] = elegido

        sin_asignar = [n for n in informe.personas if n not in mapeo]
        por_defecto = ""
        if sin_asignar:
            por_defecto = st.selectbox(
                f"«{', '.join(sin_asignar)}» no está(n) asignado(s): ¿a quién le cargamos "
                "esos gastos?",
                [""] + ids,
                format_func=lambda i: nombres.get(i, "— omitir esas filas —"),
                key="cc_import_defecto",
            )

        confirmo = st.checkbox(
            "Confirmo que quiero importar estos gastos a este hogar",
            key="cc_import_confirmo",
        )
        if st.button("Importar ahora", type="primary", disabled=not confirmo):
            resultado = ctx.hogar_ctl().importar_v1(mapeo, por_defecto)
            if resultado.ok:
                st.session_state["cc_import_informe"] = resultado.datos
            aplicar(resultado)


def _sin_pestanas(ctx: Contexto, info: dict) -> None:
    """Explica por qué no hay nada para importar y qué hacer al respecto."""
    st.warning("No encontramos las pestañas «Gastos» ni «Lista_Compras».")
    pestanas = info.get("pestanas") or []
    if pestanas:
        st.caption("Pestañas que ve la app en esta planilla:")
        st.code(", ".join(pestanas), language=None)

    if info.get("origen") == "externa_error":
        st.error(
            "Configuraste `hoja_url_legacy`, pero no pude abrir esa planilla. Revisá "
            "la URL y que la cuenta de servicio tenga acceso (Editor o Lector)."
        )
        return
    if info.get("hoja_legacy"):
        st.info(
            "Busqué también en la planilla de `hoja_url_legacy` y tampoco encontré "
            "esas pestañas."
        )
        return

    st.markdown(
        "Puede que los gastos viejos estén en **otra planilla** (por ejemplo, una "
        "copia de la original). En ese caso agregá en los Secretos de Streamlit la "
        "URL de esa planilla —la cuenta de servicio tiene que tener acceso de "
        "lectura— y reiniciá la app:"
    )
    st.code(
        'hoja_url_legacy = "https://docs.google.com/spreadsheets/d/XXXX/edit"',
        language="toml",
    )
    st.caption(
        "Si las pestañas se llaman distinto (por ejemplo «Gastos 2025»), renombralas "
        "a «Gastos» y «Lista_Compras» en esa planilla, o decime el nombre y lo agrego "
        "como alias."
    )


def _actividad(ctx: Contexto, datos: dict) -> None:
    st.markdown("### 🧭 Actividad reciente")
    if not datos["puedo_administrar"]:
        st.info("Sólo quien administra el hogar puede ver la actividad.")
        return
    eventos = datos["eventos"]
    if not eventos:
        st.caption("Todavía no hay movimientos registrados.")
        return

    etiquetas = {
        "hogar_creado": "Hogar creado",
        "hogar_renombrado": "Nombre cambiado",
        "gasto_agregado": "Gasto agregado",
        "gasto_editado": "Gasto editado",
        "gasto_anulado": "Gasto eliminado",
        "pago_registrado": "Pago registrado",
        "pago_borrado": "Pago eliminado",
        "miembro_unido": "Persona que se sumó",
        "miembro_quitado": "Persona quitada",
        "miembro_salio": "Persona que salió",
        "rol_cambiado": "Rol cambiado",
        "propiedad_transferida": "Propiedad transferida",
        "invitacion_creada": "Invitación creada",
        "plan_cambiado": "Plan cambiado",
    }
    filas = [
        {
            "Cuándo": str(e.get("creado_en", ""))[:16].replace("T", " "),
            "Acción": etiquetas.get(e.get("accion", ""), e.get("accion", "")),
            "Detalle": e.get("detalle", ""),
        }
        for e in eventos
    ]
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)


def render(ctx: Contexto) -> None:
    ctx.exigir_hogar()
    resultado = ctx.hogar_ctl().datos()
    if not resultado.ok:
        mostrar(resultado)
        return
    datos = resultado.datos or {}
    hogar = datos["hogar"]

    st.markdown(f"### 🏡 {hogar['nombre']}")
    st.markdown(
        f"{pill(datos['etiqueta_plan'], gris=datos['plan'] == planes.GRATIS)} "
        f"{pill(ROLES_ETIQUETA.get(hogar.get('rol', 'miembro'), ''), gris=True)}",
        unsafe_allow_html=True,
    )

    tab_personas, tab_invitaciones, tab_ajustes, tab_actividad = st.tabs(
        ["👥 Personas", "🔗 Invitaciones", "⚙️ Ajustes", "🧭 Actividad"]
    )
    with tab_personas:
        _miembros(ctx, datos)
    with tab_invitaciones:
        _invitaciones(ctx, datos)
    with tab_ajustes:
        _ajustes(ctx, datos)
    with tab_actividad:
        _actividad(ctx, datos)

    _unirme(ctx)


def _unirme(ctx: Contexto) -> None:
    """Permite sumarse a otro hogar con un código (para quien ya tiene cuenta)."""
    st.divider()
    with st.expander("🔗 Unirme a otro hogar con un código"):
        st.caption(
            "Si te invitaron a otra casa, pegá acá el código. Vas a poder cambiar "
            "de hogar desde la barra lateral."
        )
        with st.form("unirme_hogar"):
            codigo = st.text_input("Código de invitación", placeholder="ABC123")
            enviado = st.form_submit_button("Unirme", use_container_width=True)
        if enviado:
            resultado = ctx.sesion().unirse(ctx.usuario["id"], codigo)
            if resultado.ok:
                st.session_state["cc_hogar_id"] = (resultado.datos or {}).get("id", "")
            aplicar(resultado)
