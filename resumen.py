import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime

# --- FUNCIÓN DEL MODAL (VENTANA EMERGENTE) ---
@st.dialog("🖼️ Visor de Comprobante")
def abrir_visor_imagen(url, nombre_archivo):
    st.image(url)
    st.write("---")
    try:
        img_data = requests.get(url).content
        st.download_button(
            label="⬇️ Guardar imagen en mi equipo",
            data=img_data,
            file_name=nombre_archivo,
            mime="image/jpeg",
            type="primary"
        )
    except:
        st.error("No se pudo cargar la descarga.")

def mostrar_vista_resumen(df):
    if st.sidebar.button("♻️ Forzar Actualización de Planilla"):
        st.cache_data.clear() 
        st.rerun()           

    st.subheader("📊 Resumen de Gastos")

    # --- PROCESAMIENTO DE DATOS ---
    df_res = df.copy()
    df_res['Fecha_DT'] = pd.to_datetime(df_res['Fecha'], dayfirst=True, errors='coerce')
    df_res = df_res.dropna(subset=['Fecha_DT'])

    if df_res.empty:
        st.info("Todavía no hay gastos cargados para mostrar el resumen.")
        return

    df_res['Año'] = df_res['Fecha_DT'].dt.year

    traduccion_meses = {
    'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo', 
    'April': 'Abril', 'May': 'Mayo', 'June': 'Junio', 
    'July': 'Julio', 'August': 'Agosto', 'September': 'Septiembre', 
    'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
    }
    df_res['Mes'] = df_res['Fecha_DT'].dt.month_name().map(traduccion_meses)

    # --- LÓGICA DE MES EN CURSO ---
    ahora = datetime.now()
    nombre_mes_actual = ahora.strftime("%B") # Obtiene el nombre del mes en inglés (ej: 'May')
    anio_actual = ahora.year

    st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    
    # 1. Selector de Año con default al año actual
    anios_disponibles = sorted(df_res['Año'].unique(), reverse=True)
    try:
        index_anio = anios_disponibles.index(anio_actual)
    except ValueError:
        index_anio = 0 # Si el año actual no tiene gastos, elige el primero de la lista
        
    anio_sel = st.sidebar.selectbox("Año", anios_disponibles, index=index_anio, key="sel_anio")
    
    # 2. Selector de Mes con default al mes actual
    meses_disponibles = list(df_res[df_res['Año'] == anio_sel]['Mes'].unique())
    try:
        index_mes = meses_disponibles.index(nombre_mes_actual)
    except ValueError:
        index_mes = 0 # Si el mes actual no tiene gastos, elige el primero
        
    mes_sel = st.sidebar.selectbox("Mes", meses_disponibles, index=index_mes, key="sel_mes")

    # Filtrado final
    df_filtrado = df_res[(df_res['Año'] == anio_sel) & (df_res['Mes'] == mes_sel)].copy()

    # --- MÉTRICAS ---
    total_mes = df_filtrado['Monto'].sum()
    col_a, col_b = st.columns(2)
    col_a.metric(f"Total {mes_sel}", f"${total_mes:,.2f}")
    col_b.metric("Movimientos", len(df_filtrado))

    # --- CÁLCULO DE DEUDAS ---
    total_agus = df_filtrado[df_filtrado['Quien'] == 'Agustín']['Monto'].sum()
    total_jorge = df_filtrado[df_filtrado['Quien'] == 'Jorge']['Monto'].sum()
    diferencia = abs(total_agus - total_jorge) / 2

    if total_agus > total_jorge:
        st.info(f"💸 **Jorge le debe a Agustín:** ${diferencia:,.2f}")
    elif total_jorge > total_agus:
        st.warning(f"💸 **Agustín le debe a Jorge:** ${diferencia:,.2f}")
    else:
        st.success("✨ **¡Están empatados! Nadie le debe a nadie este mes.**")

    st.write("---")
    
    # --- TABLA Y GRÁFICO ---
    col_izq, col_der = st.columns([0.6, 0.4])

    with col_izq:
        st.markdown("**Detalle de Gastos** *(Clic en una fila para ver el comprobante)*")
        df_tabla = df_filtrado.copy().reset_index(drop=True)
        df_tabla['Comprobante'] = df_tabla['Comprobante'].apply(lambda x: "📎 Adjunto" if str(x).startswith('http') else None)

        evento_tabla = st.dataframe(
            df_tabla[['Fecha', 'Quien', 'Concepto', 'Monto', 'Categoria', 'Comprobante']],
            hide_index=True,
            width='stretch',
            selection_mode="single-row",
            on_select="rerun"
        )

        if len(evento_tabla.selection.rows) > 0:
            fila_seleccionada = evento_tabla.selection.rows[0]
            url_img = df_filtrado.iloc[fila_seleccionada]['Comprobante']
            
            if pd.notna(url_img) and str(url_img).startswith('http'):
                concepto_limpio = str(df_filtrado.iloc[fila_seleccionada]['Concepto']).replace(' ', '_')
                abrir_visor_imagen(url_img, f"ticket_{concepto_limpio}.jpg")
            else:
                st.toast("Este gasto no tiene un comprobante adjunto.", icon="⚠️")

    with col_der:
        st.markdown("**Gastos por Categoria**")
        df_cat = df_filtrado.groupby('Categoria')['Monto'].sum()
        if not df_cat.empty:
            fig, ax = plt.subplots(figsize=(5, 5))
            df_cat.plot(kind='pie', autopct='%1.1f%%', ax=ax, startangle=90, cmap='Pastel1')
            ax.set_ylabel('')
            st.pyplot(fig)