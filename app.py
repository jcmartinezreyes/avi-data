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

# ---------------------------------------------------------
# NAVEGACIÓN CON MENÚ INTERACTIVO EXPANDIBLE
# ---------------------------------------------------------
st.sidebar.title("Menú Principal")

# Inicializar estado de navegación
if "opcion_nav" not in st.session_state:
    st.session_state["opcion_nav"] = "📊 Overview General"

if st.sidebar.button("📊 Overview General", use_container_width=True):
    st.session_state["opcion_nav"] = "📊 Overview General"

# Menú interactivo desplegable para Registros
with st.sidebar.expander("📝 Registros / Operación", expanded=False):
    if st.button("1. Registrar Granja", use_container_width=True):
        st.session_state["opcion_nav"] = "1. Registrar Granja"
    if st.button("2. Crear Galpón", use_container_width=True):
        st.session_state["opcion_nav"] = "2. Crear Galpón"
    if st.button("3. Alojar Lote", use_container_width=True):
        st.session_state["opcion_nav"] = "3. Alojar Lote"
    if st.button("4. Ingreso Diario", use_container_width=True):
        st.session_state["opcion_nav"] = "4. Ingreso Diario"

if st.sidebar.button("📈 Análisis Gerencial", use_container_width=True):
    st.session_state["opcion_nav"] = "📈 Análisis Gerencial"

opcion = st.session_state["opcion_nav"]

# ---------------------------------------------------------
# 1. OVERVIEW GENERAL (Muestra Saldo Actualizado de Aves)
# ---------------------------------------------------------
if opcion == "📊 Overview General":
    st.header("📊 Vista General del Sistema")
    
    res_granjas = supabase.table("granjas").select("*").execute()
    res_lotes = supabase.table("lotes").select("*, galpones(nombre, granjas(nombre))").eq("activo", True).execute()
    res_reg = supabase.table("registros_diarios").select("lote_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho").execute()
    
    # Calcular bajas acumuladas por lote (mortalidad + descartes)
    df_reg = pd.DataFrame(res_reg.data) if res_reg.data else pd.DataFrame()
    bajas_por_lote = {}
    
    if not df_reg.empty:
        df_reg.fillna(0, inplace=True)
        grouped = df_reg.groupby("lote_id").sum()
        for lote_id, row in grouped.iterrows():
            bajas_por_lote[lote_id] = {
                "bajas_h": row.get("mortalidad_hembra", 0) + row.get("descarte_hembra", 0),
                "bajas_m": row.get("mortalidad_macho", 0) + row.get("descarte_macho", 0)
            }
            
    cant_granjas = len(res_granjas.data) if res_granjas.data else 0
    cant_lotes = len(res_lotes.data) if res_lotes.data else 0
    
    # Construcción de datos de lotes calculando el Saldo Actual
    filas_lotes = []
    total_saldo_aves = 0
    
    if res_lotes.data:
        for l in res_lotes.data:
            lote_id = l["id"]
            inicial_h = l.get("aves_hembra", 0) or 0
            inicial_m = l.get("aves_macho", 0) or 0
            
            bajas = bajas_por_lote.get(lote_id, {"bajas_h": 0, "bajas_m": 0})
            
            saldo_h = max(0, int(inicial_h - bajas["bajas_h"]))
            saldo_m = max(0, int(inicial_m - bajas["bajas_m"]))
            saldo_total = saldo_h + saldo_m
            
            total_saldo_aves += saldo_total
            
            nombre_galpon = l["galpones"]["nombre"] if isinstance(l.get("galpones"), dict) else ""
            nombre_granja = l["galpones"]["granjas"]["nombre"] if isinstance(l.get("galpones"), dict) and "granjas" in l["galpones"] else ""
            
            filas_lotes.append({
                "Código Lote": l["codigo_lote"],
                "Línea Genética": l["linea_genetica"],
                "Fecha Encaste": l["fecha_encaste"],
                "Saldo Hembras": f"{saldo_h:,}",
                "Saldo Machos": f"{saldo_m:,}",
                "Saldo Total Aves": f"{saldo_total:,}",
                "Galpón": nombre_galpon,
                "Granja": nombre_granja
            })

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    with col_kpi1:
        st.metric("Granjas Registradas", cant_granjas)
    with col_kpi2:
        st.metric("Lotes Activos", cant_lotes)
    with col_kpi3:
        st.metric("Saldo Total Aves Vivas", f"{total_saldo_aves:,}")
        
    st.markdown("---")
    
    st.subheader("Ubicación Geográfica de Granjas")
    if res_granjas.data:
        m_general = folium.Map(location=[4.4065, -75.2265], zoom_start=6)
        for g in res_granjas.data:
            if g.get("latitud") and g.get("longitud"):
                folium.Marker(
                    location=[g["latitud"], g["longitud"]],
                    popup=g["nombre"],
                    tooltip=g["nombre"],
                    icon=folium.Icon(color="green", icon="home")
                ).add_to(m_general)
        st_folium(m_general, height=350, width=800)
    else:
        st.info("Aún no hay granjas registradas.")
        
    st.subheader("Lotes Activos en Producción (Saldo Actual de Aves)")
    if filas_lotes:
        df_display = pd.DataFrame(filas_lotes)
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("No hay lotes activos actualmente.")

# ---------------------------------------------------------
# 2. REGISTROS / OPERACIÓN
# ---------------------------------------------------------
elif opcion == "1. Registrar Granja":
    st.header("1. Registrar Nueva Granja")
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
            hembras = st.number_input("Aves Hembras Iniciales", min_value=0, value=10000, step=500)
        with col2:
            machos = st.number_input("Aves Machos Iniciales", min_value=0, value=10000, step=500)
            
        totales = hembras + machos
        st.info(f"Total Aves Alojadas Inicialmente: {totales:,}")
        
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
        
        fecha_encaste = pd.to_datetime(lote_info["fecha_encaste"]).date()
        dias_diferencia = (fecha_registro - fecha_encaste).days
        dia_vida_calculado = dias_diferencia + 1
        
        if dia_vida_calculado < 1:
            st.error(f"La fecha de registro ({fecha_registro}) no puede ser anterior a la fecha de encaste del lote ({fecha_encaste}).")
        else:
            st.info(f"📅 **Día de Vida (Edad) calculado:** Día {dia_vida_calculado} (Encaste: {fecha_encaste})")
            
            res_existente = supabase.table("registros_diarios") \
                .select("*") \
                .eq("lote_id", lote_info["id"]) \
                .eq("fecha", str(fecha_registro)) \
                .execute()
            
            registro_previo = res_existente.data[0] if res_existente.data else None
            
            if registro_previo:
                st.warning(f"⚠️ Ya existe un registro para la fecha {fecha_registro}. Se cargaron los datos guardados para su modificación.")
            
            pob_h = lote_info.get("aves_hembra", 0) or 1
            pob_m = lote_info.get("aves_macho", 0) or 1
            key_prefix = f"{lote_info['id']}_{str(fecha_registro)}"

            def_mh = int(registro_previo.get("mortalidad_hembra", 0)) if registro_previo else 0
            def_mm = int(registro_previo.get("mortalidad_macho", 0)) if registro_previo else 0
            def_dh = int(registro_previo.get("descarte_hembra", 0)) if registro_previo else 0
            def_dm = int(registro_previo.get("descarte_macho", 0)) if registro_previo else 0
            def_ali = float(registro_previo.get("consumo_alimento_kg", 0.0)) if registro_previo else 0.0
            def_agu = float(registro_previo.get("consumo_agua_litros", 0.0)) if registro_previo else 0.0
            def_ph = float(registro_previo.get("peso_promedio_hembra_g", 0.0)) if registro_previo else 0.0
            def_pm = float(registro_previo.get("peso_promedio_macho_g", 0.0)) if registro_previo else 0.0
            def_pmix = float(registro_previo.get("peso_promedio_mixto_g", 0.0)) if registro_previo else 0.0

            st.subheader("Mortalidad y Descartes Sexados")
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                mort_h = st.number_input("Mortalidad Hembras", min_value=0, step=1, value=def_mh, key=f"mh_{key_prefix}")
                pct_mort_h = (mort_h / pob_h) * 100
                st.caption(f"**{pct_mort_h:.2f}%** del total hembras")
                if pct_mort_h > 1.0:
                    st.warning("⚠️ % Mortalidad alto.")
                    
            with c2:
                mort_m = st.number_input("Mortalidad Machos", min_value=0, step=1, value=def_mm, key=f"mm_{key_prefix}")
                pct_mort_m = (mort_m / pob_m) * 100
                st.caption(f"**{pct_mort_m:.2f}%** del total machos")
                if pct_mort_m > 1.0:
                    st.warning("⚠️ % Mortalidad alto.")
                    
            with c3:
                desc_h = st.number_input("Descarte Hembras", min_value=0, step=1, value=def_dh, key=f"dh_{key_prefix}")
                pct_desc_h = (desc_h / pob_h) * 100
                st.caption(f"**{pct_desc_h:.2f}%** del total hembras")
                if pct_desc_h > 1.0:
                    st.warning("⚠️ % Descarte alto.")
                    
            with c4:
                desc_m = st.number_input("Descarte Machos", min_value=0, step=1, value=def_dm, key=f"dm_{key_prefix}")
                pct_desc_m = (desc_m / pob_m) * 100
                st.caption(f"**{pct_desc_m:.2f}%** del total machos")
                if pct_desc_m > 1.0:
                    st.warning("⚠️ % Descarte alto.")
                
            st.subheader("Consumos")
            c5, c6 = st.columns(2)
            with c5:
                alimento = st.number_input("Consumo Alimento (kg)", min_value=0.0, step=10.0, value=def_ali, key=f"ali_{key_prefix}")
            with c6:
                agua = st.number_input("Consumo Agua (Litros)", min_value=0.0, step=50.0, value=def_agu, key=f"agu_{key_prefix}")
                
            st.subheader("Pesajes (Gramos)")
            c7, c8, c9 = st.columns(3)
            with c7:
                peso_h = st.number_input("Peso Promedio Hembras (g)", min_value=0.0, step=1.0, value=def_ph, key=f"ph_{key_prefix}")
            with c8:
                peso_m = st.number_input("Peso Promedio Machos (g)", min_value=0.0, step=1.0, value=def_pm, key=f"pm_{key_prefix}")
            with c9:
                peso_mix = st.number_input("Peso Promedio Mixto (g)", min_value=0.0, step=1.0, value=def_pmix, key=f"pmix_{key_prefix}")
                
            btn_label = "Actualizar Registro Diario" if registro_previo else "Guardar Registro Diario"
            
            if st.button(btn_label, key=f"btn_{key_prefix}"):
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
                
                if registro_previo:
                    supabase.table("registros_diarios").update(reg).eq("id", registro_previo["id"]).execute()
                    st.success(f"¡Registro del Día {dia_vida_calculado} actualizado con éxito!")
                else:
                    supabase.table("registros_diarios").insert(reg).execute()
                    st.success(f"¡Registro del Día {dia_vida_calculado} guardado exitosamente!")
    else:
        st.info("No hay lotes activos actualmente.")

# ---------------------------------------------------------
# 3. ANÁLISIS GERENCIAL
# ---------------------------------------------------------
elif opcion == "📈 Análisis Gerencial":
    st.header("📈 Análisis Gerencial de Lotes")
    res = supabase.table("registros_diarios").select("*, lotes(codigo_lote, linea_genetica)").execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        st.subheader("Tabla Consolidada de Registros")
        st.dataframe(df, use_container_width=True)
        
        st.subheader("Evolución de Pesos Promedio")
        st.line_chart(df, x="dia_vida", y=["peso_promedio_mixto_g", "peso_promedio_hembra_g", "peso_promedio_macho_g"])
        
        st.subheader("Consumo Diario de Alimento (kg)")
        st.bar_chart(df, x="dia_vida", y="consumo_alimento_kg")
    else:
        st.info("Aún no hay datos de consumo o pesajes cargados.")
