import streamlit as st
import pandas as pd
from supabase import create_client
from streamlit_folium import st_folium
import folium

# Configuración de página
st.set_page_config(page_title="Sistema Avícola", layout="wide")

# Conexión a Supabase
URL = "https://zmpqrcqadrxevqyshvak.supabase.co"
KEY = "sb_publishable_--thXNjoDX0MmxrcOBFCLg_Lo5hHeCG"
supabase = create_client(URL, KEY)

st.title("Sistema de Control Avícola 🐔")

# Menú principal ordenado por flujo lógico
menu = ["1. Registrar Granja", "2. Crear Galpón", "3. Alojar Lote", "4. Ingreso Diario", "5. Dashboard Gerencial"]
opcion = st.sidebar.selectbox("Navegación", menu)

# ---------------------------------------------------------
# 1. REGISTRAR GRANJA
# ---------------------------------------------------------
if opcion == "1. Registrar Granja":
    st.header("1. Registrar Granja")
    nombre = st.text_input("Nombre de la Granja")
    
    st.write("Selecciona la ubicación en el mapa:")
    m = folium.Map(location=[4.4065, -75.2265], zoom_start=6)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=350, width=700)
    
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lng = map_data["last_clicked"]["lng"]
        st.success(f"Coordenadas seleccionadas: Lat {lat:.4f}, Lng {lng:.4f}")
        
        if st.button("Guardar Granja") and nombre:
            supabase.table("granjas").insert({"nombre": nombre, "latitud": lat, "longitud": lng}).execute()
            st.success("¡Granja guardada con éxito!")

# ---------------------------------------------------------
# 2. CREAR GALPÓN
# ---------------------------------------------------------
elif opcion == "2. Crear Galpón":
    st.header("2. Crear Galpón en Granja")
    res_granjas = supabase.table("granjas").select("id, nombre").execute()
    
    if res_granjas.data:
        dict_granjas = {g["nombre"]: g["id"] for g in res_granjas.data}
        granja_sel = st.selectbox("Seleccionar Granja", list(dict_granjas.keys()))
        
        nombre_galpon = st.text_input("Nombre / Número del Galpón (Ej: Galpón 01)")
        capacidad = st.number_input("Capacidad Máxima (Aves)", min_value=1000, value=20000, step=1000)
        
        if st.button("Crear Galpón") and nombre_galpon:
            datos = {"granja_id": dict_granjas[granja_sel], "nombre": nombre_galpon, "capacidad": capacidad}
            supabase.table("galpones").insert(datos).execute()
            st.success(f"Galpón '{nombre_galpon}' asignado a {granja_sel}.")
    else:
        st.warning("Debes registrar al menos una granja primero.")

# ---------------------------------------------------------
# 3. ALOJAR LOTE
# ---------------------------------------------------------
elif opcion == "3. Alojar Lote":
    st.header("3. Alojar Lote en Galpón")
    res_galpones = supabase.table("galpones").select("id, nombre, granjas(nombre)").execute()
    
    if res_galpones.data:
        dict_galpones = {f"{g['granjas']['nombre']} - {g['nombre']}": g["id"] for g in res_galpones.data}
        galpon_sel = st.selectbox("Seleccionar Galpón", list(dict_galpones.keys()))
        
        codigo_lote = st.text_input("Código del Lote (Ej: LOTE-2026-01)")
        linea = st.selectbox("Línea Genética / Estirpe", ["Cobb 500", "Ross 308", "Hubbard", "Otra"])
        fecha_encaste = st.date_input("Fecha de Encaste")
        
        col1, col2 = st.columns(2)
        with col1:
            hembras = st.number_input("Aves Hembras", min_value=0, value=10000, step=500)
        with col2:
            machos = st.number_input("Aves Machos", min_value=0, value=10000, step=500)
            
        totales = hembras + machos
        st.info(f"Total Aves Alojadas: {totales:,}")
        
        if st.button("Alojar Lote") and codigo_lote:
            datos_lote = {
                "galpon_id": dict_galpones[galpon_sel],
                "codigo_lote": codigo_lote,
                "linea_genetica": linea,
                "fecha_encaste": str(fecha_encaste),
                "aves_hembra": hembras,
                "aves_macho": machos,
                "aves_totales": totales,
                "activo": True
            }
            supabase.table("lotes").insert(datos_lote).execute()
            st.success(f"Lote {codigo_lote} alojado correctamente.")
    else:
        st.warning("Primero debes crear un galpón.")

# ---------------------------------------------------------
# 4. INGRESO DIARIO
# ---------------------------------------------------------
elif opcion == "4. Ingreso Diario":
    st.header("4. Registro Diario del Galpón")
    res_lotes = supabase.table("lotes").select("id, codigo_lote, linea_genetica, fecha_encaste, aves_hembra, aves_macho, galpones(nombre)").eq("activo", True).execute()
    
    if res_lotes.data:
        lotes_dict = {
            f"{l['codigo_lote']} ({l['galpones']['nombre']} - {l['linea_genetica']})": l 
            for l in res_lotes.data
        }
        
        lote_sel_nombre = st.selectbox("Seleccionar Lote Activo", list(lotes_dict.keys()))
        lote_info = lotes_dict[lote_sel_nombre]
        
        fecha_registro = st.date_input("Fecha del Registro")
        
        # CÁLCULO AUTOMÁTICO DEL DÍA DE VIDA
        fecha_encaste = pd.to_datetime(lote_info["fecha_encaste"]).date()
        dias_diferencia = (fecha_registro - fecha_encaste).days
        dia_vida_calculado = dias_diferencia + 1
        
        if dia_vida_calculado < 1:
            st.error(f"La fecha de registro ({fecha_registro}) no puede ser anterior a la fecha de encaste del lote ({fecha_encaste}).")
        else:
            st.info(f"📅 **Día de Vida (Edad) calculado:** Día {dia_vida_calculado} (Encaste: {fecha_encaste})")
            
            # Recuperar población inicial sexada para cálculo de %
            pob_h = lote_info.get("aves_hembra", 0) or 1
            pob_m = lote_info.get("aves_macho", 0) or 1

            st.subheader("Mortalidad y Descartes Sexados")
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                mort_h = st.number_input("Mortalidad Hembras", min_value=0, step=1)
                pct_mort_h = (mort_h / pob_h) * 100
                st.caption(f"**{pct_mort_h:.2f}%** del total hembras")
                if pct_mort_h > 1.0:
                    st.warning("⚠️ % Mortalidad alto. Revisa el valor ingresado.")
                    
            with c2:
                mort_m = st.number_input("Mortalidad Machos", min_value=0, step=1)
                pct_mort_m = (mort_m / pob_m) * 100
                st.caption(f"**{pct_mort_m:.2f}%** del total machos")
                if pct_mort_m > 1.0:
                    st.warning("⚠️ % Mortalidad alto. Revisa el valor ingresado.")
                    
            with c3:
                desc_h = st.number_input("Descarte Hembras", min_value=0, step=1)
                pct_desc_h = (desc_h / pob_h) * 100
                st.caption(f"**{pct_desc_h:.2f}%** del total hembras")
                if pct_desc_h > 1.0:
                    st.warning("⚠️ % Descarte alto. Revisa el valor ingresado.")
                    
            with c4:
                desc_m = st.number_input("Descarte Machos", min_value=0, step=1)
                pct_desc_m = (desc_m / pob_m) * 100
                st.caption(f"**{pct_desc_m:.2f}%** del total machos")
                if pct_desc_m > 1.0:
                    st.warning("⚠️ % Descarte alto. Revisa el valor ingresado.")
                
            st.subheader("Consumos")
            c5, c6 = st.columns(2)
            with c5:
                alimento = st.number_input("Consumo Alimento (kg)", min_value=0.0, step=10.0)
            with c6:
                agua = st.number_input("Consumo Agua (Litros)", min_value=0.0, step=50.0)
                
            st.subheader("Pesajes (Gramos)")
            c7, c8, c9 = st.columns(3)
            with c7:
                peso_h = st.number_input("Peso Promedio Hembras (g)", min_value=0.0, step=1.0)
            with c8:
                peso_m = st.number_input("Peso Promedio Machos (g)", min_value=0.0, step=1.0)
            with c9:
                peso_mix = st.number_input("Peso Promedio Mixto (g)", min_value=0.0, step=1.0)
                
            if st.button("Guardar Registro Diario"):
                reg = {
                    "lote_id": lote_info["id"],
                    "fecha": str(fecha_registro),
                    "dia_vida": int(dia_vida_calculado),
                    "mortalidad_hembra": mort_h,
                    "mortalidad_macho": mort_m,
                    "descarte_hembra": desc_h,
                    "descarte_macho": desc_m,
                    "descartes": desc_h + desc_m,
                    "consumo_alimento_kg": alimento,
                    "consumo_agua_litros": agua,
                    "peso_promedio_hembra_g": peso_h,
                    "peso_promedio_macho_g": peso_m,
                    "peso_promedio_mixto_g": peso_mix
                }
                supabase.table("registros_diarios").insert(reg).execute()
                st.success(f"¡Registro del Día {dia_vida_calculado} guardado exitosamente!")
    else:
        st.info("No hay lotes activos. Ve a '3. Alojar Lote' para registrar uno.")

# ---------------------------------------------------------
# 5. DASHBOARD GERENCIAL
# ---------------------------------------------------------
elif opcion == "5. Dashboard Gerencial":
    st.header("5. Análisis Gerencial de Lotes")
    res = supabase.table("registros_diarios").select("*, lotes(codigo_lote, linea_genetica)").execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        st.subheader("Tabla de Registros")
        st.dataframe(df)
        
        st.subheader("Evolución de Pesos Promedio")
        st.line_chart(df, x="dia_vida", y=["peso_promedio_mixto_g", "peso_promedio_hembra_g", "peso_promedio_macho_g"])
    else:
        st.info("Aún no hay datos cargados en el sistema.")
