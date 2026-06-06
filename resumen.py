import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta

# --- CONEXIÓN DIRECTA A GSHEETS PARA EDICIÓN ---
def get_gsheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

# --- MODAL: VISOR, EDICIÓN Y ELIMINACIÓN ---
@st.dialog("📝 Gestionar Gasto")
def abrir_visor_y_editor(fila_idx, datos_gasto, df_original):
    url_img = datos_gasto['Comprobante']
    if pd.notna(url_img) and str(url_img).startswith('http'):
        st.image(url_img, caption="Comprobante actual", use_container_width=True)
        try:
            img_data = requests.get(url_img).content
            st.download_button(
                label="⬇️ Descargar Ticket",
                data=img_data,
                file_name=f"ticket_{str(datos_gasto['Concepto']).replace(' ', '_')}.jpg",
                mime="image/jpeg",
                use_container_width=True
            )
        except:
            st.caption("No se pudo procesar la descarga de la imagen.")
    else:
        st.info("Este gasto no tiene un comprobante adjunto.")

    st.write("---")
    st.markdown("### Editar Datos")

    nuevo_concepto = st.text_input("Concepto / Detalle:", value=str(datos_gasto['Concepto']))
    nuevo_monto = st.number_input("Monto ($):", value=float(datos_gasto['Monto']), min_value=0.0, step=50.0)
    
    categorias = ["Supermercado", "Servicios", "Internet", "Auto", "Salidas", "Casa", "Otros"]
    try:
        idx_cat = categorias.index(datos_gasto['Categoria'])
    except:
        idx_cat = 0
    nueva_cat = st.selectbox("Categoría:", categorias, index=idx_cat)

    col_guardar, col_eliminar = st.columns(2)

    if col_guardar.button("💾 Guardar Cambios", type="primary", use_container_width=True):
        with st.spinner("Actualizando planilla..."):
            client = get_gsheets_client()
            sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Gastos")
            num_fila_sheet = int(fila_idx) + 2
            sheet.update_cell(num_fila_sheet, 3, nuevo_concepto)
            sheet.update_cell(num_fila_sheet, 4, nuevo_monto)
            sheet.update_cell(num_fila_sheet, 5, nueva_cat)
            st.cache_data.clear()
            st.success("¡Modificado con éxito!")
            st.rerun()

    if col_eliminar.button("🗑️ Eliminar Gasto", type="secondary", use_container_width=True):
        with st.spinner("Borrando fila..."):
            client = get_gsheets_client()
            sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Gastos")
            num_fila_sheet = int(fila_idx) + 2
            sheet.delete_rows(num_fila_sheet)
            st.cache_data.clear()
            st.success("Gasto eliminado.")
            st.rerun()

# --- INTERFAZ DEL RESUMEN ---
def mostrar_vista_resumen(df):
    if st.sidebar.button("♻️ Forzar Actualización de Planilla"):
        st.cache_data.clear() 
        st.rerun()           

    st.subheader("📊 Resumen de Gastos")

    df_res = df.copy()
    df_res['sheet_idx'] = df_res.index
    df_res['Fecha_DT'] = pd.to_datetime(df_res['Fecha'], dayfirst=True, errors='coerce')
    df_res = df_res.dropna(subset=['Fecha_DT'])

    if df_res.empty:
        st.info("Todavía no hay gastos cargados para mostrar el resumen.")
        return

    df_res['Año'] = df_res['Fecha_DT'].dt.year
    df_res['Mes'] = df_res['Fecha_DT'].dt.month_name()

    traduccion_meses_en = {
        'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo', 'April': 'Abril',
        'May': 'Mayo', 'June': 'Junio', 'July': 'Julio', 'August': 'Agosto',
        'September': 'Septiembre', 'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
    }
    df_res['Mes'] = df_res['Mes'].map(traduccion_meses_en)

    # --- FILTROS (REPARADO PARA PARARSE EN JUNIO POR DEFECTO) ---
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    
    zona_ar = timezone(timedelta(hours=-3))
    hoy = datetime.now(zona_ar)
    anio_actual = hoy.year
    
    traduccion_meses_num = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    mes_actual_nombre = traduccion_meses_num[hoy.month] # Nos da 'Junio'

    anios_disponibles = list(df_res['Año'].unique())
    if anio_actual not in anios_disponibles:
        anios_disponibles.append(anio_actual)
    anios_disponibles = sorted(list(set(anios_disponibles)), reverse=True)
    
    anio_sel = st.sidebar.selectbox("Año", anios_disponibles, key="sel_anio")
    
    meses_disponibles = list(df_res[df_res['Año'] == anio_sel]['Mes'].unique())
    if anio_sel == anio_actual and mes_actual_nombre not in meses_disponibles:
        meses_disponibles.append(mes_actual_nombre)
        
    orden_meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    meses_disponibles = sorted(list(set(meses_disponibles)), key=lambda x: orden_meses.index(x) if x in orden_meses else 0)

    try:
        idx_mes_defecto = meses_disponibles.index(mes_actual_nombre)
    except ValueError:
        idx_mes_defecto = 0

    mes_sel = st.sidebar.selectbox("Mes", meses_disponibles, index=idx_mes_defecto, key="sel_mes")

    df_filtrado = df_res[(df_res['Año'] == anio_sel) & (df_res['Mes'] == mes_sel)].copy()

    # --- MÉTRICAS ---
    total_mes = df_filtrado['Monto'].sum()
    col_a, col_b = st.columns(2)
    col_a.metric(f"Total {mes_sel}", f"${total_mes:,.2f}")
    col_b.metric("Movimientos", len(df_filtrado))

    # --- CÁLCULO DE DEUDAS (SIN ACENTO) ---
    total_agus = df_filtrado[df_filtrado['Quien'] == 'Agustin']['Monto'].sum()
    total_jorge = df_filtrado[df_filtrado['Quien'] == 'Jorge']['Monto'].sum()
    diferencia = abs(total_agus - total_jorge) / 2

    if total_agus > total_jorge:
        st.info(f"💸 **Jorge le debe a Agustin:** ${diferencia:,.2f}")
    elif total_jorge > total_agus:
        st.warning(f"💸 **Agustin le debe a Jorge:** ${diferencia:,.2f}")
    else:
        st.success("✨ **¡Están empatados! Nadie le debe a nadie este mes.**")

    st.write("---")
    
    # --- TABLA Y GRÁFICO ---
    col_izq, col_der = st.columns([0.6, 0.4])

    with col_izq:
        st.markdown("**Detalle de Gastos** *(Clic en cualquier fila para Editar o ver Ticket)*")
        df_tabla = df_filtrado.copy().reset_index(drop=True)
        df_tabla['Comprobante'] = df_tabla['Comprobante'].apply(lambda x: "📎 Adjunto" if str(x).startswith('http') else "❌ Sin foto")

        evento_tabla = st.dataframe(
            df_tabla[['Fecha', 'Quien', 'Concepto', 'Monto', 'Categoria', 'Comprobante']],
            hide_index=True,
            width='stretch',
            selection_mode="single-row",
            on_select="rerun"
        )

        if len(evento_tabla.selection.rows) > 0:
            fila_seleccionada_tabla = evento_tabla.selection.rows[0]
            datos_gasto = df_filtrado.iloc[fila_seleccionada_tabla]
            real_sheet_idx = datos_gasto['sheet_idx']
            abrir_visor_y_editor(real_sheet_idx, datos_gasto, df_res)

    with col_der:
        st.markdown("**Gastos por Categoría**")
        df_cat = df_filtrado.groupby('Categoria')['Monto'].sum()
        if not df_cat.empty:
            fig, ax = plt.subplots(figsize=(5, 5))
            df_cat.plot(kind='pie', autopct='%1.1f%%', ax=ax, startangle=90, cmap='Pastel1')
            ax.set_ylabel('')
            st.pyplot(fig)