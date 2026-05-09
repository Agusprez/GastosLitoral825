import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import requests
import base64
from resumen import mostrar_vista_resumen

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Gastos Casa - San Pedro", layout="wide")

# ==========================================
# 🔒 SISTEMA DE LOGIN PERSONALIZADO
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_actual"] = ""

if not st.session_state["autenticado"]:
    st.title("🔒 Acceso a Gastos")
    st.write("Identificate para entrar.")
    
    # Ahora elegís quién sos antes de poner la clave
    usuario_elegido = st.selectbox("Usuario:", ["Agustin", "Jorge"])
    clave_ingresada = st.text_input("Contraseña:", type="password")
    
    if st.button("Entrar"):
        # Buscamos la clave correspondiente a ese usuario en los secretos
        clave_real = st.secrets["passwords"].get(usuario_elegido)
        
        if clave_ingresada == clave_real:
            st.session_state["autenticado"] = True
            st.session_state["usuario_actual"] = usuario_elegido # Guardamos quién entró
            st.rerun()
        else:
            st.error("Contraseña incorrecta. Intentá de nuevo.")
            
    st.stop() 

# ==========================================
# 🚀 APLICACIÓN PRINCIPAL
# ==========================================

def get_gsheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def cargar_datos():
    client = get_gsheets_client()
    sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Gastos")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df.columns = ['Fecha', 'Quien', 'Concepto', 'Monto', 'Categoria', 'Comprobante']
    df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce').fillna(0)
    return df

def subir_a_imgbb(archivo):
    url = "https://api.imgbb.com/1/upload"
    payload = {
        "key": st.secrets["imgbb_api_key"],
        "image": base64.b64encode(archivo.getvalue()).decode("utf-8")
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        return response.json()["data"]["url"]
    return "Error al subir imagen"

# --- INTERFAZ ---
st.title("🏠 Gastos Compartidos")

# Agregamos un saludo personalizado en la barra lateral
st.sidebar.success(f"Hola, {st.session_state['usuario_actual']} 👋")

if st.sidebar.button("🔄 Sincronizar con Google Sheets"):
    st.cache_data.clear()
    st.rerun()

# Botón para cerrar sesión si quieren cambiar de usuario en la misma compu
if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state["autenticado"] = False
    st.session_state["usuario_actual"] = ""
    st.rerun()

menu = st.sidebar.selectbox("Navegación", ["📝 Cargar Gasto", "📊 Ver Resumen"])

if menu == "📝 Cargar Gasto":
    with st.form("carga", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        # --- LÓGICA DE PRESELECCIÓN ---
        usuarios = ["Agustín", "Jorge"]
        # Buscamos en qué posición está el usuario que inició sesión (0 o 1)
        indice_usuario = usuarios.index(st.session_state["usuario_actual"])
        
        # Le pasamos ese índice al selectbox para que arranque en su nombre
        quien = col1.selectbox("¿Quién pagó?", usuarios, index=indice_usuario)
        
        monto = col1.number_input("Monto ($)", min_value=0.0, step=100.0)
        cat = col2.selectbox("Categoria", ["Supermercado", "Servicios", "Internet", "Auto", "Salidas", "Casa", "Otros"])
        con = col2.text_input("Detalle")
        
        st.write("---")
        archivo_subido = st.file_uploader("Subir comprobante o ticket (Opcional)", type=['jpg', 'jpeg', 'png'])
        
        st.write("---")
        if st.form_submit_button("Guardar"):
            
            zona_ar = timezone(timedelta(hours=-3))
            fecha = datetime.now(zona_ar).strftime("%d/%m/%Y")
            
            link_comprobante = "Sin comprobante"
            if archivo_subido is not None:
                with st.spinner("Subiendo imagen..."):
                    link_comprobante = subir_a_imgbb(archivo_subido)
            
            with st.spinner("Guardando en Google..."):
                client = get_gsheets_client()
                sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Gastos")
                sheet.append_row([fecha, quien, con, monto, cat, link_comprobante])
                
                st.cache_data.clear()
            
            st.success("¡Gasto guardado! Podés verlo ahora en el resumen.")

else:
    with st.spinner("Leyendo planilla actualizada..."):
        df = cargar_datos()
    mostrar_vista_resumen(df)
