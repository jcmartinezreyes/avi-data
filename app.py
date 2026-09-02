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
# NAVEGACIÓN
# ---------------------------------------------------------
st.sidebar.title("Menú Principal")

if "opcion_nav" not in st.session_state:
    st.session_state["opcion_nav"] = "📊 Overview General"

if st.sidebar.button("📊 Overview General", use_container_width=True):
    st.session_state["opcion_nav"] = "📊 Overview General"

with st.sidebar.expander("📝 Registros / Operación", expanded=True):
    if st.button("1. Registrar Granja", use_container_width=True):
        st.session_state["opcion_nav"] = "1. Registrar Granja"
    if st.button("2. Crear Galpón", use_container_width=True):
        st.session_state["opcion_nav"] = "2. Crear Galpón"
    if st.button("3. Lotes", use_container_width=True):
        st.session_state["opcion_nav"] = "3. Lotes"
        st.session_state["ver_formulario_lote"] = False
    if st.button("4. Ingreso Diario", use_container_width=True):
        st.session_state["opcion_nav"] = "4. Ingreso Diario"

if st.sidebar.button("📈 Análisis Gerencial", use_container_width=True):
    st.session_state["opcion_nav"] = "📈 Análisis Gerencial"

opcion = st.session_state["opcion_nav"]

# ---------------------------------------------------------
# 1. OVERVIEW GENERAL
# ---------------------------------------------------------
if opcion == "📊 Overview General":
    st.header("📊 Vista General del Sistema")
    
    res_granjas = supabase.table("granjas").select("*").execute()
    res_lotes = supabase.table("lotes").select("*, galpones(nombre, granjas(nombre))").eq("activo", True).execute()
    res_reg = supabase.table("registros_diarios").select("lote_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho").execute()
    
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
                "Propósito": l.get("proposito", "N/A"),
                "Línea Genética": l["linea_genetica"],
                "Fecha Encaste": l["fecha_encaste"],
                "Saldo Hembras": f"{saldo_h:,}",
                "Saldo Machos": f"{saldo_m:,}",
                "Saldo Total": f"{saldo_total:,}",
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

# ---------------------------------------------------------
# 2. REGISTRAR GRANJA
# ---------------------------------------------------------
elif opcion == "1. Registrar Granja":
    st.header("1. Registrar Nueva Granja")
    
    st.write("Selecciona la ubicación en el mapa:")
    m = folium.Map(location=[4.4065, -75.2265], zoom_start=6)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=350, width=700)
    
    lat, lng = None, None
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lng = map_data["last_clicked"]["lng"]
        st.success(f"Coordenadas seleccionadas: Lat {lat:.4f}, Lng {lng:.4f}")

    with st.form("form_granja", clear_on_submit=True):
        nombre = st.text_input("Nombre de la Granja", value="")
        submitted = st.form_submit_button("Guardar Granja")
        
        if submitted:
            if nombre and lat is not None:
                supabase.table("granjas").insert({"nombre": nombre, "latitud": lat, "longitud": lng}).execute()
                st.success("¡Granja guardada con éxito!")
            elif not nombre:
                st.error("Por favor, ingresa el nombre de la granja.")
            else:
                st.error("Por favor, selecciona un punto en el mapa para capturar las coordenadas.")

# ---------------------------------------------------------
# 3. CREAR GALPÓN
# ---------------------------------------------------------
elif opcion == "2. Crear Galpón":
    st.header("2. Crear Galpón en Granja")
    res_granjas = supabase.table("granjas").select("id, nombre").execute()
    
    if res_granjas.data:
        dict_granjas = {g["nombre"]: g["id"] for g in res_granjas.data}
        granja_sel = st.selectbox("Seleccionar Granja", list(dict_granjas.keys()))
        
        with st.form("form_galpon", clear_on_submit=True):
            nombre_galpon = st.text_input("Nombre / Número del Galpón (Ej: Galpón 01)", value="")
            capacidad = st.number_input("Capacidad Máxima (Aves)", min_value=0, value=0, step=1000)
            submitted = st.form_submit_button("Crear Galpón")
            
            if submitted:
                if nombre_galpon and capacidad > 0:
                    datos = {"granja_id": dict_granjas[granja_sel], "nombre": nombre_galpon, "capacidad": capacidad}
                    supabase.table("galpones").insert(datos).execute()
                    st.success(f"¡Galpón '{nombre_galpon}' asignado correctamente!")
                else:
                    st.error("Por favor ingresa un nombre válido y una capacidad mayor a 0.")
    else:
        st.warning("Debes registrar al menos una granja primero.")

# ---------------------------------------------------------
# 4. MÓDULO DE LOTES (VISTA GENERAL + FORMULARIO DE CREACIÓN)
# ---------------------------------------------------------
elif opcion == "3. Lotes":
    if "ver_formulario_lote" not in st.session_state:
        st.session_state["ver_formulario_lote"] = False

    col_tit, col_btn = st.columns([4, 1])
    
    with col_tit:
        st.header("3. Gestión de Lotes")
        
    with col_btn:
        if not st.session_state["ver_formulario_lote"]:
            if st.button("➕ Crear Nuevo Lote", type="primary", use_container_width=True):
                st.session_state["ver_formulario_lote"] = True
                st.rerun()
        else:
            if st.button("⬅️ Volver a Lotes", use_container_width=True):
                st.session_state["ver_formulario_lote"] = False
                st.rerun()

    # VISTA 1: TABLA GENERAL DE LOTES
    if not st.session_state["ver_formulario_lote"]:
        res_lotes = supabase.table("lotes").select("*, galpones(nombre, granjas(nombre))").eq("activo", True).execute()
        res_reg = supabase.table("registros_diarios").select("lote_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho").execute()
        
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

        filas_lotes = []
        if res_lotes.data:
            for l in res_lotes.data:
                lote_id = l["id"]
                inicial_h = l.get("aves_hembra", 0) or 0
                inicial_m = l.get("aves_macho", 0) or 0
                bajas = bajas_por_lote.get(lote_id, {"bajas_h": 0, "bajas_m": 0})
                
                saldo_h = max(0, int(inicial_h - bajas["bajas_h"]))
                saldo_m = max(0, int(inicial_m - bajas["bajas_m"]))
                saldo_total = saldo_h + saldo_m
                
                nombre_galpon = l["galpones"]["nombre"] if isinstance(l.get("galpones"), dict) else ""
                nombre_granja = l["galpones"]["granjas"]["nombre"] if isinstance(l.get("galpones"), dict) and "granjas" in l["galpones"] else ""
                
                filas_lotes.append({
                    "Código Lote": l["codigo_lote"],
                    "Propósito": l.get("proposito", "N/A"),
                    "Línea Genética": l["linea_genetica"],
                    "Fecha Encaste": l["fecha_encaste"],
                    "Inicial Hembras": f"{inicial_h:,}",
                    "Inicial Machos": f"{inicial_m:,}",
                    "Saldo Actual Aves": f"{saldo_total:,}",
                    "Galpón": nombre_galpon,
                    "Granja": nombre_granja
                })
                
            st.dataframe(pd.DataFrame(filas_lotes), use_container_width=True)
        else:
            st.info("No hay lotes creados actualmente. Haz clic en '➕ Crear Nuevo Lote' para ingresar uno.")

    # VISTA 2: FORMULARIO CREAR / ALOJAR LOTE
    else:
        st.subheader("Alojar Lote en Galpón")
        res_galpones = supabase.table("galpones").select("id, nombre, granjas(nombre)").execute()
        
        if res_galpones.data:
            dict_galpones = {f"{g['granjas']['nombre']} - {g['nombre']}": g["id"] for g in res_galpones.data}
            galpon_sel = st.selectbox("Seleccionar Galpón", list(dict_galpones.keys()))
            
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                proposito = st.selectbox("Propósito del Lote", ["Engorde", "Postura (Comercial)", "Reproductoras"])
            
            with col_p2:
                if proposito == "Engorde":
                    modalidad_sexo = st.selectbox("Modalidad de Crianza", ["Sexado (Hembras / Machos)", "Mixto (As Sexed)"])
                    lineas_opt = ["Cobb 500", "Ross 308", "Hubbard", "Otra"]
                elif proposito == "Postura (Comercial)":
                    modalidad_sexo = "Solo Hembras"
                    st.info("💡 En Postura Comercial el lote se considera **100% Hembras**.")
                    lineas_opt = ["Hy-Line Brown", "Lohmann Brown", "ISA Brown", "Dekalb", "Otra"]
                else:  # Reproductoras
                    modalidad_sexo = "Sexado (Hembras / Machos)"
                    st.info("💡 En Reproductoras la crianza requiere control sexado de **Hembras y Machos**.")
                    lineas_opt = ["Cobb 500 Breeders", "Ross 308 AP", "Hubbard Efficiency", "Otra"]
                    
            linea = st.selectbox("Línea Genética / Estirpe", lineas_opt)
            
            with st.form("form_alojar_lote", clear_on_submit=True):
                codigo_lote = st.text_input("Código del Lote (Ej: LOTE-2026-01)", value="")
                fecha_encaste = st.date_input("Fecha de Encaste")
                
                st.subheader("Población a Alojar")
                hembras, machos = 0, 0
                
                if modalidad_sexo == "Sexado (Hembras / Machos)":
                    col_h, col_m = st.columns(2)
                    with col_h:
                        hembras = st.number_input("Aves Hembras Iniciales", min_value=0, value=0, step=500)
                    with col_m:
                        machos = st.number_input("Aves Machos Iniciales", min_value=0, value=0, step=100)
                elif modalidad_sexo == "Mixto (As Sexed)":
                    total_mixto = st.number_input("Cantidad de Aves Mixtas (Sin sexar)", min_value=0, value=0, step=500)
                    hembras = total_mixto // 2
                    machos = total_mixto - hembras
                elif modalidad_sexo == "Solo Hembras":
                    hembras = st.number_input("Cantidad de Aves Hembras", min_value=0, value=0, step=500)
                    machos = 0
                    
                submitted = st.form_submit_button("Alojar Lote")
                
                if submitted:
                    totales = hembras + machos
                    if codigo_lote and totales > 0:
                        datos_lote = {
                            "galpon_id": dict_galpones[galpon_sel],
                            "codigo_lote": codigo_lote,
                            "proposito": proposito,
                            "linea_genetica": linea,
                            "fecha_encaste": str(fecha_encaste),
                            "aves_hembra": hembras,
                            "aves_macho": machos,
                            "aves_totales": totales,
                            "activo": True
                        }
                        try:
                            supabase.table("lotes").insert(datos_lote).execute()
                        except Exception:
                            datos_lote.pop("proposito", None)
                            supabase.table("lotes").insert(datos_lote).execute()
                            
                        st.success(f"¡Lote '{codigo_lote}' alojado correctamente!")
                        st.session_state["ver_formulario_lote"] = False
                    else:
                        st.error("Ingresa un código de lote válido y una cantidad de aves mayor a 0.")
        else:
            st.warning("Primero debes crear un galpón.")

# ---------------------------------------------------------
# 5. INGRESO DIARIO
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
            
            def_mh = int(registro_previo.get("mortalidad_hembra", 0)) if registro_previo else 0
            def_mm = int(registro_previo.get("mortalidad_macho", 0)) if registro_previo else 0
            def_dh = int(registro_previo.get("descarte_hembra", 0)) if registro_previo else 0
            def_dm = int(registro_previo.get("descarte_macho", 0)) if registro_previo else 0
            def_ali = float(registro_previo.get("consumo_alimento_kg", 0.0)) if registro_previo else 0.0
            def_agu = float(registro_previo.get("consumo_agua_litros", 0.0)) if registro_previo else 0.0
            def_ph = float(registro_previo.get("peso_promedio_hembra_g", 0.0)) if registro_previo else 0.0
            def_pm = float(registro_previo.get("peso_promedio_macho_g", 0.0)) if registro_previo else 0.0
            def_pmix = float(registro_previo.get("peso_promedio_mixto_g", 0.0)) if registro_previo else 0.0

            with st.form("form_registro_diario", clear_on_submit=True):
                st.subheader("Mortalidad y Descartes Sexados")
                c1, c2, c3, c4 = st.columns(4)
                
                with c1:
                    mort_h = st.number_input("Mortalidad Hembras", min_value=0, step=1, value=def_mh)
                with c2:
                    mort_m = st.number_input("Mortalidad Machos", min_value=0, step=1, value=def_mm)
                with c3:
                    desc_h = st.number_input("Descarte Hembras", min_value=0, step=1, value=def_dh)
                with c4:
                    desc_m = st.number_input("Descarte Machos", min_value=0, step=1, value=def_dm)
                    
                st.subheader("Consumos")
                c5, c6 = st.columns(2)
                with c5:
                    alimento = st.number_input("Consumo Alimento (kg)", min_value=0.0, step=10.0, value=def_ali)
                with c6:
                    agua = st.number_input("Consumo Agua (Litros)", min_value=0.0, step=50.0, value=def_agu)
                    
                st.subheader("Pesajes (Gramos)")
                c7, c8, c9 = st.columns(3)
                with c7:
                    peso_h = st.number_input("Peso Promedio Hembras (g)", min_value=0.0, step=1.0, value=def_ph)
                with c8:
                    peso_m = st.number_input("Peso Promedio Machos (g)", min_value=0.0, step=1.0, value=def_pm)
                with c9:
                    peso_mix = st.number_input("Peso Promedio Mixto (g)", min_value=0.0, step=1.0, value=def_pmix)
                    
                btn_label = "Actualizar Registro Diario" if registro_previo else "Guardar Registro Diario"
                submitted = st.form_submit_button(btn_label)
                
                if submitted:
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
# 6. ANÁLISIS GERENCIAL
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
