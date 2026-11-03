import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta

# --- CONEXIÓN DIRECTA A GSHEETS ---
def get_gsheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

def cargar_datos_compras():
    client = get_gsheets_client()
    sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Lista_Compras")
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# --- VISTA COMPONENTE LISTA DE COMPRAS ---
def mostrar_vista_compras():
    st.markdown("### 🛒 Cosas pendientes para comprar")
    
    # Formulario rápido para añadir elementos
    with st.form("nuevo_item_compras", clear_on_submit=True):
        col_item, col_btn = st.columns([0.7, 0.3])
        with col_item:
            item_texto = st.text_input("¿Qué hace falta?", placeholder="Ej: Detergente, Leche, Yerba...")
        with col_btn:
            st.write("##") 
            btn_agregar = st.form_submit_button("➕ Añadir a la lista", type="primary", use_container_width=True)
            
        if btn_agregar and item_texto.strip() != "":
            with st.spinner("Añadiendo..."):
                # --- CAPTURAMOS LA FECHA ACTUAL DE ARGENTINA ---
                zona_ar = timezone(timedelta(hours=-3))
                fecha_hoy = datetime.now(zona_ar).strftime("%d/%m/%Y")
                
                client = get_gsheets_client()
                sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Lista_Compras")
                
                # Insertamos: Elemento, Quién Anotó, Comprado, Fecha Anotado
                sheet.append_row([item_texto.strip(), st.session_state["usuario_actual"], "No", fecha_hoy])
                st.success(f"¡'{item_texto}' anotado!")
                st.rerun()

    st.write("---")
    
    # Mostrar la lista actual
    with st.spinner("Cargando lista de pendientes..."):
        df_compras = cargar_datos_compras()
    
    if df_compras.empty:
        st.success("✨ ¡No hay nada pendiente para comprar! La alacena está completa.")
    else:
        st.markdown("**Lista de pendientes actuales:**")
        
        # Iteramos los elementos de la lista
        for idx, fila in df_compras.iterrows():
            col_check, col_info = st.columns([0.2, 0.8])
            
            num_fila_sheet = idx + 2 
            
            if col_check.button("✅ Comprado", key=f"del_{idx}", use_container_width=True):
                with st.spinner("Removiendo de la lista..."):
                    client = get_gsheets_client()
                    sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Lista_Compras")
                    sheet.delete_rows(num_fila_sheet)
                    st.rerun()
            
            # Traemos la fecha de la columna nueva. Si está vacía por registros viejos, ponemos un texto por defecto
            fecha_str = fila.get('Fecha Anotado', '-') if pd.notna(fila.get('Fecha Anotado')) else '-'
            
            # Mostramos toda la info junta de forma prolija
            col_info.markdown(f"🛍️ **{fila['Elemento']}** \n*{fila['Quién Anotó']} — anotado el {fecha_str}*")
            st.write("---")