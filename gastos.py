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
    
    usuario_elegido = st.selectbox("Usuario:", ["Agustin", "Jorge"])
    clave_ingresada = st.text_input("Contraseña:", type="password")
    
    if st.button("Entrar"):
        clave_real = st.secrets["passwords"].get(usuario_elegido)
        
        if clave_ingresada == clave_real:
            st.session_state["autenticado"] = True
            st.session_state["usuario_actual"] = usuario_elegido
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

# --- INTERFAZ MODERNA ---
st.title("🏠 Gastos Compartidos — San Pedro")

# Configuración de la barra lateral (Limpia y enfocada en acciones)
st.sidebar.success(f"Hola, {st.session_state['usuario_actual']} 👋")

st.sidebar.markdown("### Acciones")
if st.sidebar.button("🔄 Sincronizar Planilla", width='stretch'):
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("🚪 Cerrar Sesión", width='stretch'):
    st.session_state["autenticado"] = False
    st.session_state["usuario_actual"] = ""
    st.rerun()

# --- NAVEGACIÓN POR PESTAÑAS CENTRALES ---
tab_cargar, tab_resumen = st.tabs(["📝 Cargar Nuevo Gasto", "📊 Ver Resumen Mensual"])

# PESTAÑA 1: CARGAR GASTO
with tab_cargar:
    st.markdown("### Registrar un gasto reciente")
    with st.form("carga", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        usuarios = ["Agustin", "Jorge"]
        user_sesion = st.session_state.get("usuario_actual", "Agustin")
        
        try:
            indice_usuario = usuarios.index(user_sesion)
        except ValueError:
            indice_usuario = 0
        
        quien = col1.selectbox("¿Quién pagó?", usuarios, index=indice_usuario)
        monto = col1.number_input("Monto ($)", min_value=0.0, step=100.0)
        cat = col2.selectbox("Categoría", ["Supermercado", "Servicios", "Internet", "Auto", "Salidas", "Casa", "Otros"])
        con = col2.text_input("Detalle (Concepto)")
        
        st.write("---")
        archivo_subido = st.file_uploader("Subir comprobante o ticket (Opcional)", type=['jpg', 'jpeg', 'png'])
        
        st.write("---")
        boton_guardar = st.form_submit_button("Guardar Gasto", type="primary")
        
        if boton_guardar:
            zona_ar = timezone(timedelta(hours=-3))
            fecha = datetime.now(zona_ar).strftime("%d/%m/%Y")
            
            link_comprobante = "Sin comprobante"
            if archivo_subido is not None:
                with st.spinner("Subiendo imagen a la nube..."):
                    link_comprobante = subir_a_imgbb(archivo_subido)
            
            with st.spinner("Guardando en Google Sheets..."):
                client = get_gsheets_client()
                sheet = client.open_by_url(st.secrets["sheet_url_gastos"]).worksheet("Gastos")
                sheet.append_row([fecha, quien, con, monto, cat, link_comprobante])
                st.cache_data.clear()
            
            st.success("¡Gasto guardado correctamente!")

# PESTAÑA 2: RESUMEN
with tab_resumen:
    with st.spinner("Leyendo planilla actualizada de Google Sheets..."):
        df = cargar_datos()
    mostrar_vista_resumen(df)