import json
import os
import sqlite3
from datetime import datetime
import streamlit as st

# Intentar importar pyodbc para la conexión con ITVNet (SQL Server)
try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False

# Configuración de la página
st.set_page_config(
    page_title="CDA Ivesur - Inspección Móvil",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Estilo personalizado CDA Ivesur
st.markdown("""
    <style>
    .main { background-color: #f5f5f5; }
    .stButton>button {
        background-color: #ff6600;
        color: white;
        border-radius: 8px;
        font-weight: bold;
        width: 100%;
        height: 3em;
    }
    .stButton>button:hover { background-color: #e65c00; color: white; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 1. BASE DE DATOS LOCAL (Respaldo SQLite)
# ---------------------------------------------------------
DB_LOCAL = "ivesur_patio.db"

def init_db_local():
    conn = sqlite3.connect(DB_LOCAL)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inspecciones_patio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT,
            placa TEXT,
            tipo_vehiculo TEXT,
            linea_atencion TEXT,
            mediciones JSON,
            estado_patio TEXT,
            sincronizado_itvnet INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def guardar_local(placa, tipo_vehiculo, linea, mediciones, aprobado, sinc_itvnet=0):
    conn = sqlite3.connect(DB_LOCAL)
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estado = "APROBADO" if aprobado else "RECHAZADO"
    cursor.execute("""
        INSERT INTO inspecciones_patio (fecha_hora, placa, tipo_vehiculo, linea_atencion, mediciones, estado_patio, sincronizado_itvnet)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (fecha_actual, placa, tipo_vehiculo, linea, json.dumps(mediciones), estado, sinc_itvnet))
    conn.commit()
    conn.close()

init_db_local()

# ---------------------------------------------------------
# 2. CONECTOR DIRECTO A ITVNET (SQL Server Local CDA)
# ---------------------------------------------------------
def enviar_a_itvnet(placa, tipo_vehiculo, linea, mediciones, aprobado):
    """
    Intenta conectar a la Base de Datos de ITVNet en la red del CDA.
    Ajustar credenciales según el servidor de Ivesur.
    """
    if not HAS_PYODBC:
        return False, "Librería pyodbc no instalada en este entorno."

    # Configuración de red interna del CDA
    SERVER_ITVNET = '192.168.1.100'  # IP del servidor local de ITVNet
    DATABASE_ITVNET = 'ITVNet_DB'    # Nombre de la BD de ITVNet
    USER_ITVNET = 'cda_patio'
    PASSWORD_ITVNET = 'Ivesur2026*'

    connection_string = (
        f"DRIVER={{SQL Server}};SERVER={SERVER_ITVNET};"
        f"DATABASE={DATABASE_ITVNET};UID={USER_ITVNET};PWD={PASSWORD_ITVNET};Timeout=3;"
    )

    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        # Inserción en la tabla de capturas pre-línea de ITVNet
        query = """
            INSERT INTO CapturasPatio (Placa, TipoVehiculo, Linea, ProfundidadLabrado, EstadoPatio, FechaCaptura)
            VALUES (?, ?, ?, ?, ?, GETDATE())
        """
        estado_str = "APROBADO" if aprobado else "RECHAZADO"
        cursor.execute(query, (placa, tipo_vehiculo, linea, json.dumps(mediciones), estado_str))
        conn.commit()
        conn.close()
        return True, "Enviado exitosamente a ITVNet"
    except Exception as e:
        return False, f"Servidor ITVNet offline o no alcanzable: {str(e)}"

# ---------------------------------------------------------
# 3. INTERFAZ MÓVIL EN PATIO
# ---------------------------------------------------------
if os.path.exists("logo_ivesur.png"):
    st.image("logo_ivesur.png", width=200)

st.title("CDA Ivesur - Módulo Móvil de Patio")
st.caption("Conector Móvil de Inspección ↔ Servidor ITVNet")

st.header("📋 Pre-Inspección de Vehículo")

col1, col2 = st.columns(2)
with col1:
    placa = st.text_input("Placa del Vehículo:", max_chars=6).upper()
    tipo_vehiculo = st.selectbox("Tipo de Vehículo:", ["Motocicleta", "Liviano", "Pesado", "Ciclomotor"])

with col2:
    linea_atencion = st.selectbox("Línea de Atención:", ["Línea 1", "Línea 2", "Línea 3", "Línea Motos"])

st.subheader("Profundidad de Labrado (Llantas)")
col_e1, col_e2 = st.columns(2)
with col_e1:
    l1 = st.number_input("Eje 1 (mm):", min_value=0.0, max_value=25.0, value=3.0, step=0.1)
with col_e2:
    l2 = st.number_input("Eje 2 (mm):", min_value=0.0, max_value=25.0, value=3.0, step=0.1)

mediciones = {"Eje 1": l1, "Eje 2": l2}

# Determinar aprobación de labrado
limite_min = 1.0 if tipo_vehiculo == "Motocicleta" else (2.0 if tipo_vehiculo == "Pesado" else 1.6)
aprobado = (l1 >= limite_min) and (l2 >= limite_min)

if st.button("🚀 Guardar e Enviar a ITVNet"):
    if not placa:
        st.warning("⚠️ Ingrese la placa del vehículo.")
    else:
        # 1. Intentar envío directo a ITVNet
        exito_itvnet, msg_itvnet = enviar_a_itvnet(placa, tipo_vehiculo, linea_atencion, mediciones, aprobado)

        if exito_itvnet:
            guardar_local(placa, tipo_vehiculo, linea_atencion, mediciones, aprobado, sinc_itvnet=1)
            st.success(f"✅ **¡Inyectado en ITVNet!** La placa **{placa}** ya está disponible en el software del CDA.")
        else:
            # 2. Respaldo local si no hay conexión directa a ITVNet
            guardar_local(placa, tipo_vehiculo, linea_atencion, mediciones, aprobado, sinc_itvnet=0)
            st.info(f"💾 **Guardado en respaldo local.** {msg_itvnet}")
            if aprobado:
                st.success(f" Insprcción de **{placa}** APROBADA localmente.")
            else:
                st.error(f"❌ Inspección de **{placa}** RECHAZADA (Hallazgos en llantas).")

# ---------------------------------------------------------
# BARRA LATERAL: Estado de Conexión
# ---------------------------------------------------------
st.sidebar.header("📊 Estado del Sistema")
st.sidebar.markdown(f"**Conector ITVNet:** {'🟢 Activo (pyodbc)' if HAS_PYODBC else '🟡 Modo Local/Demo'}")
st.sidebar.markdown("**Servidor BD:** `192.168.1.100` (Red CDA)")