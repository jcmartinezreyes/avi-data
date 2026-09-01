import streamlit as st
import pandas as pd
from supabase import create_client
from streamlit_folium import st_folium
import folium

# Conexión a Supabase
URL = "TU_SUPABASE_URL"
KEY = "TU_SUPABASE_KEY"
supabase = create_client(URL, KEY)

st.title("Sistema de Control Avícola 🐔")

opcion = st.sidebar.selectbox("Menú", ["Registrar Granja", "Ingreso Diario", "Dashboard Gerencial"])

if opcion == "Registrar Granja":
    st.header("Ubicación de la Granja")
    nombre = st.text_input("Nombre de la Granja")
    
    # Mapa interactivo para marcar la ubicación
    m = folium.Map(location=[-15.7801, -47.9292], zoom_start=4)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=350, width=700)
    
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lng = map_data["last_clicked"]["lng"]
        st.success(f"Coordenadas seleccionadas: Lat {lat:.4f}, Lng {lng:.4f}")
        
        if st.button("Guardar Granja"):
            supabase.table("granjas").insert({"nombre": nombre, "latitud": lat, "longitud": lng}).execute()
            st.success("Granja guardada con éxito.")

elif opcion == "Ingreso Diario":
    st.header("Carga de Datos del Galpón")
    # Cargar lotes activos
    res = supabase.table("lotes").select("id, codigo_lote").eq("activo", True).execute()
    lotes = {item["codigo_lote"]: item["id"] for item in res.data}
    
    if lotes:
        lote_sel = st.selectbox("Seleccionar Lote", list(lotes.keys()))
        fecha = st.date_input("Fecha")
        mortalidad = st.number_input("Mortalidad (aves)", min_value=0, step=1)
        alimento = st.number_input("Consumo Alimento (kg)", min_value=0.0, step=0.5)
        peso = st.number_input("Peso Promedio (g)", min_value=0.0, step=1.0)
        
        if st.button("Registrar Día"):
            datos = {
                "lote_id": lotes[lote_sel],
                "fecha": str(fecha),
                "mortalidad": mortalidad,
                "consumo_alimento_kg": alimento,
                "peso_promedio_g": peso
            }
            supabase.table("registros_diarios").insert(datos).execute()
            st.success("Registro guardado.")
    else:
        st.info("No hay lotes activos disponibles.")

elif opcion == "Dashboard Gerencial":
    st.header("Análisis de Lotes")
    res = supabase.table("registros_diarios").select("*").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        st.dataframe(df)
        
        # Gráfico simple de peso vs fecha
        st.line_chart(df, x="fecha", y="peso_promedio_g")
