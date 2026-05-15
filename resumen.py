import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- CONEXIÓN DIRECTA A GSHEETS PARA EDICIÓN ---
def get_gsheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

# --- MODAL: VISOR, EDICIÓN Y ELIMINACIÓN ---
@st.dialog("📝 Gestionar Gasto")
def abrir_visor_y_editor(fila_idx, datos_gasto, df_original):
    """
    fila_idx: Índice real de la fila en el Google Sheet (considerando encabezado)
    datos_gasto: Serie de Pandas con los datos actuales de la fila seleccionada
    """
    # 1. Vista del comprobante si existe
    url_img = datos_gasto['Comprobante']
    if pd.notna(url_img) and str(url_img).startswith('http'):
        st.image(url_img, caption="Comprobante actual", width='stretch')
        try:
            img_data = requests.get(url_img).content
            st.download_button(
                label="⬇️ Descargar Ticket",
                data=img_data,
                file_name=f"ticket_{str(datos_gasto['Concepto']).replace(' ', '_')}.jpg",
                mime="image/jpeg",
                width='stretch'
            )
        except:
            st.caption("No se pudo procesar la descarga de la imagen.")
    else:
        st.info("Este gasto no tiene un comprobante adjunto.")

    st.write("---")
    st.markdown("### Editar Datos")

    # 2. Formulario de edición con los datos precargados
    nuevo_concepto = st.text_input("Concepto / Detalle:", value=str(datos_gasto['Concepto']))
    nuevo_monto = st.number_input("Monto ($):", value=float(datos_gasto['Monto']), min_value=0.0, step=50.0)
    
    categorias = ["Supermercado", "Servicios", "Internet", "Auto", "Salidas", "Casa", "Otros"]
    try:
        idx_cat = categorias.index(datos_gasto['Categoria'])
    except:
        idx_cat = 0
    nueva_cat = st.selectbox("Categoría:", categorias, index=idx_cat)

    col_guardar, col_eliminar = st.columns(2)

    # Botón de Guardar Cambios
    if col_guardar.button("💾 Guardar Cambios", type="primary", width='stretch'):
        with st.spinner("Actualizando planilla..."):
            client = get_gsheets_client()
            sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Gastos")
            
            # gspread usa índices base 1. Sumamos 2 (1 por el encabezado de Sheets y 1 porque Pandas es base 0)
            num_fila_sheet = int(fila_idx) + 2
            
            # Actualizamos las celdas específicas (C=Concepto, D=Monto, E=Categoría)
            sheet.update_cell(num_fila_sheet, 3, nuevo_concepto)
            sheet.update_cell(num_fila_sheet, 4, nuevo_monto)
            sheet.update_cell(num_fila_sheet, 5, nueva_cat)
            
            st.cache_data.clear() # Limpiamos caché para ver el cambio al instante
            st.success("¡Modificado con éxito!")
            st.rerun()

    # Botón de Eliminar Registro
    if col_eliminar.button("🗑️ Eliminar Gasto", type="secondary", width='stretch'):
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
    # Guardamos el índice original de la planilla para saber qué fila editar después
    df_res['sheet_idx'] = df_res.index
    
    df_res['Fecha_DT'] = pd.to_datetime(df_res['Fecha'], dayfirst=True, errors='coerce')
    df_res = df_res.dropna(subset=['Fecha_DT'])

    if df_res.empty:
        st.info("Todavía no hay gastos cargados para mostrar el resumen.")
        return

    df_res['Año'] = df_res['Fecha_DT'].dt.year
    df_res['Mes'] = df_res['Fecha_DT'].dt.month_name()

    # --- TRADUCCIÓN DE MESES AL ESPAÑOL ---
    traduccion_meses = {
        'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo', 'April': 'Abril',
        'May': 'Mayo', 'June': 'Junio', 'July': 'Julio', 'August': 'Agosto',
        'September': 'Septiembre', 'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
    }
    df_res['Mes'] = df_res['Mes'].map(traduccion_meses)

    # --- FILTROS ---
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    
    anios_disponibles = sorted(df_res['Año'].unique(), reverse=True)
    anio_sel = st.sidebar.selectbox("Año", anios_disponibles, key="sel_anio")
    
    meses_disponibles = df_res[df_res['Año'] == anio_sel]['Mes'].unique()
    mes_sel = st.sidebar.selectbox("Mes", meses_disponibles, key="sel_mes")

    df_filtrado = df_res[(df_res['Año'] == anio_sel) & (df_res['Mes'] == mes_sel)].copy()

    # --- MÉTRICAS ---
    total_mes = df_filtrado['Monto'].sum()
    col_a, col_b = st.columns(2)
    col_a.metric(f"Total {mes_sel}", f"${total_mes:,.2f}")
    col_b.metric("Movimientos", len(df_filtrado))

    # --- CÁLCULO DE DEUDAS ---
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
        
        # Resetear el índice para la visualización de la tabla de Streamlit
        df_tabla = df_filtrado.copy().reset_index(drop=True)
        df_tabla['Comprobante'] = df_tabla['Comprobante'].apply(lambda x: "📎 Adjunto" if str(x).startswith('http') else "❌ Sin foto")

        evento_tabla = st.dataframe(
            df_tabla[['Fecha', 'Quien', 'Concepto', 'Monto', 'Categoria', 'Comprobante']],
            hide_index=True,
            width='stretch',
            selection_mode="single-row",
            on_select="rerun"
        )

        # Si el usuario hace clic en una fila, disparamos el súper modal
        if len(evento_tabla.selection.rows) > 0:
            fila_seleccionada_tabla = evento_tabla.selection.rows[0]
            
            # Obtenemos los datos de esa fila específica
            datos_gasto = df_filtrado.iloc[fila_seleccionada_tabla]
            # Sacamos el ID real que tiene esa fila en la base de datos de Google Sheets
            real_sheet_idx = datos_gasto['sheet_idx']
            
            # Abrimos el visor/editor pasándole el ID real
            abrir_visor_y_editor(real_sheet_idx, datos_gasto, df_res)

    with col_der:
        st.markdown("**Gastos por Categoría**")
        df_cat = df_filtrado.groupby('Categoria')['Monto'].sum()
        if not df_cat.empty:
            fig, ax = plt.subplots(figsize=(5, 5))
            df_cat.plot(kind='pie', autopct='%1.1f%%', ax=ax, startangle=90, cmap='Pastel1')
            ax.set_ylabel('')
            st.pyplot(fig)