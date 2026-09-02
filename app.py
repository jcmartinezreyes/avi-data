import streamlit as st
import pandas as pd
from supabase import create_client
from streamlit_folium import st_folium
import folium

st.set_page_config(page_title="Sistema Avícola", layout="wide")

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
    if st.button("1. Granjas", use_container_width=True):
        st.session_state["opcion_nav"] = "1. Granjas"
        st.session_state["ver_formulario_granja"] = False
    if st.button("2. Galpones", use_container_width=True):
        st.session_state["opcion_nav"] = "2. Galpones"
        st.session_state["ver_formulario_galpon"] = False
        st.session_state["galpon_a_editar"] = None
    if st.button("3. Lotes", use_container_width=True):
        st.session_state["opcion_nav"] = "3. Lotes"
        st.session_state["ver_formulario_lote"] = False
        st.session_state["lote_a_editar"] = None
    if st.button("4. Ingreso Diario", use_container_width=True):
        st.session_state["opcion_nav"] = "4. Ingreso Diario"

if st.sidebar.button("📈 Análisis Gerencial", use_container_width=True):
    st.session_state["opcion_nav"] = "📈 Análisis Gerencial"

opcion = st.session_state["opcion_nav"]

# ---------------------------------------------------------
# HELPER: SALDOS DE AVES Y BOXES POR LOTE
# ---------------------------------------------------------
def obtener_saldos_lotes():
    res_lotes = supabase.table("lotes").select("*, galpones(id, nombre, capacidad, granjas(id, nombre))").eq("activo", True).execute()
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
            
    saldos = {}
    if res_lotes.data:
        for l in res_lotes.data:
            lote_id = l["id"]
            inicial_h = l.get("aves_hembra", 0) or 0
            inicial_m = l.get("aves_macho", 0) or 0
            bajas = bajas_por_lote.get(lote_id, {"bajas_h": 0, "bajas_m": 0})
            
            saldo_h = max(0, int(inicial_h - bajas["bajas_h"]))
            saldo_m = max(0, int(inicial_m - bajas["bajas_m"]))
            saldo_total = saldo_h + saldo_m
            
            saldos[lote_id] = {
                "lote": l,
                "saldo_h": saldo_h,
                "saldo_m": saldo_m,
                "saldo_total": saldo_total
            }
    return saldos

# ---------------------------------------------------------
# OVERVIEW GENERAL
# ---------------------------------------------------------
if opcion == "📊 Overview General":
    st.header("📊 Vista General del Sistema")
    res_granjas = supabase.table("granjas").select("*").execute()
    saldos_dict = obtener_saldos_lotes()
    
    cant_granjas = len(res_granjas.data) if res_granjas.data else 0
    cant_lotes = len(saldos_dict)
    total_saldo_aves = sum(item["saldo_total"] for item in saldos_dict.values())

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
# 1. GESTIÓN DE GRANJAS
# ---------------------------------------------------------
elif opcion == "1. Granjas":
    if "ver_formulario_granja" not in st.session_state:
        st.session_state["ver_formulario_granja"] = False

    col_tit, col_btn = st.columns([4, 1])
    with col_tit:
        st.header("1. Gestión de Granjas")
    with col_btn:
        if not st.session_state["ver_formulario_granja"]:
            if st.button("➕ Registrar Granja", type="primary", use_container_width=True):
                st.session_state["ver_formulario_granja"] = True
                st.rerun()
        else:
            if st.button("⬅️ Volver a Granjas", use_container_width=True):
                st.session_state["ver_formulario_granja"] = False
                st.rerun()

    if not st.session_state["ver_formulario_granja"]:
        res_granjas = supabase.table("granjas").select("*").execute()
        res_galpones = supabase.table("galpones").select("*").execute()
        saldos_dict = obtener_saldos_lotes()
        
        if res_granjas.data:
            df_galpones = pd.DataFrame(res_galpones.data) if res_galpones.data else pd.DataFrame()
            filas_granjas = []
            for g in res_granjas.data:
                g_id = g["id"]
                if not df_galpones.empty and "granja_id" in df_galpones.columns:
                    galpones_g = df_galpones[df_galpones["granja_id"] == g_id]
                    cant_galpones = len(galpones_g)
                    cap_total = galpones_g["capacidad"].sum() if "capacidad" in galpones_g.columns else 0
                else:
                    cant_galpones = 0
                    cap_total = 0
                    
                aves_alojadas = sum(
                    item["saldo_total"] for item in saldos_dict.values()
                    if item["lote"].get("galpones") and item["lote"]["galpones"].get("granjas") and item["lote"]["galpones"]["granjas"]["id"] == g_id
                )
                porcentaje_ocupacion = (aves_alojadas / cap_total * 100) if cap_total > 0 else 0.0
                
                filas_granjas.append({
                    "Nombre Granja": g["nombre"],
                    "Galpones Totales": cant_galpones,
                    "Capacidad Total (Aves)": f"{cap_total:,}",
                    "Aves Alojadas Actuales": f"{aves_alojadas:,}",
                    "% Ocupación": f"{porcentaje_ocupacion:.1f}%",
                    "Coordenadas": f"{g.get('latitud', 'N/A')}, {g.get('longitud', 'N/A')}"
                })
                
            st.dataframe(pd.DataFrame(filas_granjas), use_container_width=True)
            
            st.subheader("Mapa de Granjas Registradas")
            m_granjas = folium.Map(location=[4.4065, -75.2265], zoom_start=6)
            for g in res_granjas.data:
                if g.get("latitud") and g.get("longitud"):
                    folium.Marker(
                        location=[g["latitud"], g["longitud"]],
                        popup=g["nombre"],
                        tooltip=g["nombre"],
                        icon=folium.Icon(color="blue", icon="home")
                    ).add_to(m_granjas)
            st_folium(m_granjas, height=350, width=800)
        else:
            st.info("No hay granjas registradas.")
    else:
        st.subheader("Registrar Nueva Granja")
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
                    st.session_state["ver_formulario_granja"] = False
                    st.rerun()

# ---------------------------------------------------------
# 2. GESTIÓN DE GALPONES (SELECCIÓN Y EDICIÓN)
# ---------------------------------------------------------
elif opcion == "2. Galpones":
    if "ver_formulario_galpon" not in st.session_state:
        st.session_state["ver_formulario_galpon"] = False
    if "galpon_a_editar" not in st.session_state:
        st.session_state["galpon_a_editar"] = None

    col_tit, col_btn = st.columns([4, 1])
    with col_tit:
        st.header("2. Gestión de Galpones")
    with col_btn:
        if not st.session_state["ver_formulario_galpon"] and st.session_state["galpon_a_editar"] is None:
            if st.button("➕ Crear Galpón", type="primary", use_container_width=True):
                st.session_state["ver_formulario_galpon"] = True
                st.session_state["galpon_a_editar"] = None
                st.rerun()
        else:
            if st.button("⬅️ Volver a Galpones", use_container_width=True):
                st.session_state["ver_formulario_galpon"] = False
                st.session_state["galpon_a_editar"] = None
                st.rerun()

    # VISTA 1: TABLA Y SELECCIÓN DE GALPONES
    if not st.session_state["ver_formulario_galpon"] and st.session_state["galpon_a_editar"] is None:
        res_granjas = supabase.table("granjas").select("id, nombre").execute()
        
        if res_granjas.data:
            dict_granjas = {g["nombre"]: g["id"] for g in res_granjas.data}
            opciones_granjas = ["Todas las Granjas"] + list(dict_granjas.keys())
            granja_filtro = st.selectbox("Filtrar por Granja:", opciones_granjas)
            
            if granja_filtro == "Todas las Granjas":
                res_galp = supabase.table("galpones").select("*, granjas(id, nombre)").execute()
            else:
                g_id = dict_granjas[granja_filtro]
                res_galp = supabase.table("galpones").select("*, granjas(id, nombre)").eq("granja_id", g_id).execute()
                
            saldos_dict = obtener_saldos_lotes()
            
            if res_galp.data:
                galpones_lista = res_galp.data
                filas_galp = []
                for galp in galpones_lista:
                    galp_id = galp["id"]
                    capacidad = galp.get("capacidad", 0) or 0
                    
                    lote_codigo = "Vacío / Sin Lote"
                    saldo_aves = 0
                    proposito_lote = "N/A"
                    linea_genetica = "N/A"
                    
                    for item in saldos_dict.values():
                        l_info = item["lote"]
                        if l_info.get("galpon_id") == galp_id:
                            lote_codigo = l_info["codigo_lote"]
                            saldo_aves = item["saldo_total"]
                            proposito_lote = l_info.get("proposito") or "Sin Asignar"
                            linea_genetica = l_info.get("linea_genetica", "N/A")
                            break
                            
                    ocupacion = (saldo_aves / capacidad * 100) if capacidad > 0 else 0.0
                    
                    filas_galp.append({
                        "ID Internal": galp["id"],
                        "Granja": galp["granjas"]["nombre"] if galp.get("granjas") else "N/A",
                        "Galpón": galp["nombre"],
                        "Capacidad Máxima": f"{capacidad:,}",
                        "Lote Alojado": lote_codigo,
                        "Propósito": proposito_lote,
                        "Línea Genética": linea_genetica,
                        "Aves Vivas Actuales": f"{saldo_aves:,}",
                        "% Ocupación": f"{ocupacion:.1f}%"
                    })
                
                df_galpones_view = pd.DataFrame(filas_galp)
                st.write("💡 Selecciona una fila para **editar las propiedades del galpón**:")
                
                event = st.dataframe(
                    df_galpones_view.drop(columns=["ID Internal"]),
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )
                
                selected_rows = event.selection.get("rows", [])
                if selected_rows:
                    idx = selected_rows[0]
                    galp_id_sel = df_galpones_view.iloc[idx]["ID Internal"]
                    galp_obj = next((item for item in galpones_lista if item["id"] == galp_id_sel), None)
                    if galp_obj:
                        st.session_state["galpon_a_editar"] = galp_obj
                        st.rerun()
            else:
                st.info("No hay galpones registrados.")
        else:
            st.info("Crea una granja primero.")

    # VISTA 2: FORMULARIO CREAR / EDITAR GALPÓN
    else:
        galp_edit = st.session_state["galpon_a_editar"]
        es_edicion = galp_edit is not None
        
        st.subheader("✏️ Editar Galpón" if es_edicion else "Crear Galpón en Granja")
        res_granjas = supabase.table("granjas").select("id, nombre").execute()
        
        if res_granjas.data:
            dict_granjas = {g["nombre"]: g["id"] for g in res_granjas.data}
            lista_granjas = list(dict_granjas.keys())
            
            idx_g = 0
            if es_edicion and galp_edit.get("granjas"):
                nombre_g = galp_edit["granjas"]["nombre"]
                if nombre_g in lista_granjas:
                    idx_g = lista_granjas.index(nombre_g)
                    
            granja_sel = st.selectbox("Seleccionar Granja", lista_granjas, index=idx_g)
            
            val_nombre = galp_edit["nombre"] if es_edicion else ""
            val_cap = int(galp_edit.get("capacidad", 0)) if es_edicion else 0
            
            with st.form("form_galpon", clear_on_submit=False):
                nombre_galpon = st.text_input("Nombre / Número del Galpón", value=val_nombre)
                capacidad = st.number_input("Capacidad Máxima (Aves)", min_value=0, value=val_cap, step=1000)
                submitted = st.form_submit_button("Actualizar Galpón" if es_edicion else "Crear Galpón")
                
                if submitted:
                    if nombre_galpon and capacidad > 0:
                        datos = {"granja_id": dict_granjas[granja_sel], "nombre": nombre_galpon, "capacidad": capacidad}
                        if es_edicion:
                            supabase.table("galpones").update(datos).eq("id", galp_edit["id"]).execute()
                            st.success("¡Galpón actualizado!")
                        else:
                            supabase.table("galpones").insert(datos).execute()
                            st.success("¡Galpón creado!")
                        st.session_state["ver_formulario_galpon"] = False
                        st.session_state["galpon_a_editar"] = None
                        st.rerun()
                    else:
                        st.error("Ingresa un nombre y capacidad válida.")

# ---------------------------------------------------------
# 3. MÓDULO DE LOTES Y CONFIGURACIÓN DE BOXES
# ---------------------------------------------------------
elif opcion == "3. Lotes":
    if "ver_formulario_lote" not in st.session_state:
        st.session_state["ver_formulario_lote"] = False
    if "lote_a_editar" not in st.session_state:
        st.session_state["lote_a_editar"] = None

    col_tit, col_btn = st.columns([4, 1])
    with col_tit:
        st.header("3. Gestión de Lotes")
    with col_btn:
        if not st.session_state["ver_formulario_lote"] and st.session_state["lote_a_editar"] is None:
            if st.button("➕ Crear Nuevo Lote", type="primary", use_container_width=True):
                st.session_state["ver_formulario_lote"] = True
                st.session_state["lote_a_editar"] = None
                st.rerun()
        else:
            if st.button("⬅️ Volver a Lotes", use_container_width=True):
                st.session_state["ver_formulario_lote"] = False
                st.session_state["lote_a_editar"] = None
                st.rerun()

    if not st.session_state["ver_formulario_lote"] and st.session_state["lote_a_editar"] is None:
        res_lotes = supabase.table("lotes").select("*, galpones(id, nombre, granjas(id, nombre))").eq("activo", True).execute()
        saldos_dict = obtener_saldos_lotes()

        if res_lotes.data:
            lotes_lista = res_lotes.data
            filas_lotes = []
            
            for l in lotes_lista:
                lote_id = l["id"]
                s_info = saldos_dict.get(lote_id, {"saldo_h": 0, "saldo_m": 0, "saldo_total": 0})
                
                nombre_galpon = l["galpones"]["nombre"] if isinstance(l.get("galpones"), dict) else ""
                nombre_granja = l["galpones"]["granjas"]["nombre"] if isinstance(l.get("galpones"), dict) and "granjas" in l["galpones"] else ""
                
                # Consultar boxes creados
                res_boxes = supabase.table("galpon_boxes").select("id").eq("lote_id", lote_id).execute()
                cant_boxes = len(res_boxes.data) if res_boxes.data else 0
                
                filas_lotes.append({
                    "ID Internal": l["id"],
                    "Código Lote": l["codigo_lote"],
                    "Boxes Creados": cant_boxes,
                    "Propósito": l.get("proposito") or "Sin Asignar",
                    "Línea Genética": l["linea_genetica"],
                    "Fecha Encaste": l["fecha_encaste"],
                    "Inicial Hembras": l.get("aves_hembra", 0) or 0,
                    "Inicial Machos": l.get("aves_macho", 0) or 0,
                    "Saldo Actual Aves": s_info["saldo_total"],
                    "Galpón": nombre_galpon,
                    "Granja": nombre_granja
                })
                
            df_lotes = pd.DataFrame(filas_lotes)
            st.write("💡 Selecciona una fila para **editar los datos o reconfigurar los boxes del lote**:")
            
            event = st.dataframe(
                df_lotes.drop(columns=["ID Internal"]),
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row"
            )
            
            selected_rows = event.selection.get("rows", [])
            if selected_rows:
                idx = selected_rows[0]
                lote_id_sel = df_lotes.iloc[idx]["ID Internal"]
                lote_obj = next((item for item in lotes_lista if item["id"] == lote_id_sel), None)
                if lote_obj:
                    st.session_state["lote_a_editar"] = lote_obj
                    st.rerun()
        else:
            st.info("No hay lotes creados actualmente.")

    else:
        lote_edit = st.session_state["lote_a_editar"]
        es_edicion = lote_edit is not None
        
        st.subheader("✏️ Editar Lote / Boxes" if es_edicion else "🐔 Alojar Lote en Galpón")
        res_galpones = supabase.table("galpones").select("id, nombre, granjas(nombre)").execute()
        
        if res_galpones.data:
            dict_galpones = {f"{g['granjas']['nombre']} - {g['nombre']}": g["id"] for g in res_galpones.data}
            lista_galpones = list(dict_galpones.keys())
            
            idx_galpon = 0
            if es_edicion and lote_edit.get("galpones"):
                g_nombre = f"{lote_edit['galpones']['granjas']['nombre']} - {lote_edit['galpones']['nombre']}"
                if g_nombre in lista_galpones:
                    idx_galpon = lista_galpones.index(g_nombre)
            
            galpon_sel = st.selectbox("Seleccionar Galpón", lista_galpones, index=idx_galpon)
            col_p1, col_p2 = st.columns(2)
            
            opciones_proposito = ["Engorde", "Postura (Comercial)", "Reproductoras"]
            idx_prop = 0
            if es_edicion and lote_edit.get("proposito") in opciones_proposito:
                idx_prop = opciones_proposito.index(lote_edit.get("proposito"))
                
            with col_p1:
                proposito = st.selectbox("Propósito del Lote", opciones_proposito, index=idx_prop)
            
            with col_p2:
                if proposito == "Engorde":
                    modalidad_sexo = st.selectbox("Modalidad de Crianza", ["Sexado (Hembras / Machos)", "Mixto (As Sexed)"])
                    lineas_opt = ["Cobb 500", "Ross 308", "Hubbard", "Otra"]
                elif proposito == "Postura (Comercial)":
                    modalidad_sexo = "Solo Hembras"
                    lineas_opt = ["Hy-Line Brown", "Lohmann Brown", "ISA Brown", "Dekalb", "Otra"]
                else:
                    modalidad_sexo = "Sexado (Hembras / Machos)"
                    lineas_opt = ["Cobb 500 Breeders", "Ross 308 AP", "Hubbard Efficiency", "Otra"]
            
            idx_linea = 0
            if es_edicion and lote_edit.get("linea_genetica") in lineas_opt:
                idx_linea = lineas_opt.index(lote_edit.get("linea_genetica"))
                
            linea = st.selectbox("Línea Genética / Estirpe", lineas_opt, index=idx_linea)
            
            val_codigo = lote_edit["codigo_lote"] if es_edicion else ""
            val_fecha = pd.to_datetime(lote_edit["fecha_encaste"]).date() if es_edicion else pd.to_datetime("today").date()
            
            codigo_lote = st.text_input("Código del Lote (Ej: LOTE-2026-01)", value=val_codigo)
            fecha_encaste = st.date_input("Fecha de Encaste", value=val_fecha)
            
            st.markdown("---")
            st.subheader("📦 Configuración y Distribución por Boxes (Corrales)")
            
            # Cargar boxes guardados si es edición
            boxes_existentes = []
            if es_edicion:
                res_b = supabase.table("galpon_boxes").select("*").eq("lote_id", lote_edit["id"]).execute()
                boxes_existentes = res_b.data if res_b.data else []
                
            num_boxes = st.number_input(
                "Número de Boxes en el Galpón:", 
                min_value=1, 
                max_value=30, 
                value=len(boxes_existentes) if len(boxes_existentes) > 0 else 5, 
                step=1
            )
            
            datos_boxes_inputs = []
            cols_box = st.columns(min(num_boxes, 4))
            
            for i in range(int(num_boxes)):
                col_idx = i % 4
                with cols_box[col_idx]:
                    st.markdown(f"**Box #{i+1}**")
                    def_h_b = int(boxes_existentes[i]["aves_hembra_inicial"]) if i < len(boxes_existentes) else 0
                    def_m_b = int(boxes_existentes[i]["aves_macho_inicial"]) if i < len(boxes_existentes) else 0
                    
                    if modalidad_sexo in ["Sexado (Hembras / Machos)", "Mixto (As Sexed)"]:
                        b_h = st.number_input(f"Hembras Box {i+1}", min_value=0, value=def_h_b, step=100, key=f"bh_{i}")
                        b_m = st.number_input(f"Machos Box {i+1}", min_value=0, value=def_m_b, step=50, key=f"bm_{i}")
                    else:
                        b_h = st.number_input(f"Hembras Box {i+1}", min_value=0, value=def_h_b, step=100, key=f"bh_{i}")
                        b_m = 0
                        
                    datos_boxes_inputs.append({"box_num": i+1, "hembras": b_h, "machos": b_m})

            # Suma de aves de todos los boxes
            tot_h_calculado = sum(b["hembras"] for b in datos_boxes_inputs)
            tot_m_calculado = sum(b["machos"] for b in datos_boxes_inputs)
            tot_general = tot_h_calculado + tot_m_calculado
            
            st.info(f"📊 **Población Total Calculada del Lote:** {tot_h_calculado:,} Hembras | {tot_m_calculado:,} Machos | **Total: {tot_general:,} Aves**")

            if st.button("Guardar Configuración del Lote y Boxes", type="primary"):
                if codigo_lote and tot_general > 0:
                    datos_lote = {
                        "galpon_id": dict_galpones[galpon_sel],
                        "codigo_lote": codigo_lote,
                        "proposito": proposito,
                        "linea_genetica": linea,
                        "fecha_encaste": str(fecha_encaste),
                        "aves_hembra": tot_h_calculado,
                        "aves_macho": tot_m_calculado,
                        "aves_totales": tot_general,
                        "activo": True
                    }
                    
                    if es_edicion:
                        lote_id_act = lote_edit["id"]
                        supabase.table("lotes").update(datos_lote).eq("id", lote_id_act).execute()
                        supabase.table("galpon_boxes").delete().eq("lote_id", lote_id_act).execute()
                    else:
                        res_ins = supabase.table("lotes").insert(datos_lote).execute()
                        lote_id_act = res_ins.data[0]["id"]
                        
                    # Insertar nuevos boxes
                    filas_boxes = [
                        {
                            "lote_id": lote_id_act,
                            "nombre_box": f"Box {b['box_num']}",
                            "aves_hembra_inicial": b["hembras"],
                            "aves_macho_inicial": b["machos"]
                        }
                        for b in datos_boxes_inputs
                    ]
                    supabase.table("galpon_boxes").insert(filas_boxes).execute()
                    
                    st.success("¡Lote y distribución por boxes guardados exitosamente!")
                    st.session_state["ver_formulario_lote"] = False
                    st.session_state["lote_a_editar"] = None
                    st.rerun()
                else:
                    st.error("Ingresa un código de lote válido y asegúrate de asignar aves en los boxes.")
        else:
            st.warning("Primero debes crear un galpón.")

# ---------------------------------------------------------
# 4. INGRESO DIARIO POR BOX Y CÁLCULO DE LOTE
# ---------------------------------------------------------
elif opcion == "4. Ingreso Diario":
    st.header("4. Registro Diario por Boxes y Consolidado de Lote")
    res_lotes = supabase.table("lotes").select("id, codigo_lote, linea_genetica, fecha_encaste, galpones(nombre)").eq("activo", True).execute()
    
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
            st.error(f"La fecha de registro no puede ser anterior al encaste ({fecha_encaste}).")
        else:
            st.info(f"📅 **Día de Vida (Edad):** Día {dia_vida_calculado}")
            
            # Consultar boxes asignados
            res_boxes = supabase.table("galpon_boxes").select("*").eq("lote_id", lote_info["id"]).order("nombre_box").execute()
            list_boxes = res_boxes.data if res_boxes.data else []
            
            if not list_boxes:
                st.warning("Este lote no tiene boxes configurados. Ve al menú 'Lotes' y edita el lote para agregar boxes.")
            else:
                # Comprobar si existe un registro general del día
                res_existente = supabase.table("registros_diarios").select("*").eq("lote_id", lote_info["id"]).eq("fecha", str(fecha_registro)).execute()
                registro_previo = res_existente.data[0] if res_existente.data else None
                
                # Cargar registros por box previos si existen
                dict_reg_box_previo = {}
                if registro_previo:
                    res_reg_b = supabase.table("registros_diarios_box").select("*").eq("registro_diario_id", registro_previo["id"]).execute()
                    if res_reg_b.data:
                        dict_reg_box_previo = {rb["box_id"]: rb for rb in res_reg_b.data}

                st.subheader("📌 Captura de Datos Diarios por Box")
                
                datos_ingresados_boxes = []
                
                for b in list_boxes:
                    box_id = b["id"]
                    box_nombre = b["nombre_box"]
                    prev_b = dict_reg_box_previo.get(box_id, {})
                    
                    with st.expander(f"📦 {box_nombre}", expanded=True):
                        c1, c2, c3, c4, c5, c6 = st.columns(6)
                        with c1:
                            mh = st.number_input(f"Mort. Hembra", min_value=0, value=int(prev_b.get("mortalidad_hembra", 0)), key=f"mh_{box_id}")
                        with c2:
                            mm = st.number_input(f"Mort. Macho", min_value=0, value=int(prev_b.get("mortalidad_macho", 0)), key=f"mm_{box_id}")
                        with c3:
                            dh = st.number_input(f"Desc. Hembra", min_value=0, value=int(prev_b.get("descarte_hembra", 0)), key=f"dh_{box_id}")
                        with c4:
                            dm = st.number_input(f"Desc. Macho", min_value=0, value=int(prev_b.get("descarte_macho", 0)), key=f"dm_{box_id}")
                        with c5:
                            ali = st.number_input(f"Alimento (kg)", min_value=0.0, value=float(prev_b.get("consumo_alimento_kg", 0.0)), step=5.0, key=f"ali_{box_id}")
                        with c6:
                            agu = st.number_input(f"Agua (L)", min_value=0.0, value=float(prev_b.get("consumo_agua_litros", 0.0)), step=10.0, key=f"agu_{box_id}")
                            
                        c7, c8 = st.columns(2)
                        with c7:
                            ph = st.number_input(f"Peso Prom. Hembra (g)", min_value=0.0, value=float(prev_b.get("peso_promedio_hembra_g", 0.0)), key=f"ph_{box_id}")
                        with c8:
                            pm = st.number_input(f"Peso Prom. Macho (g)", min_value=0.0, value=float(prev_b.get("peso_promedio_macho_g", 0.0)), key=f"pm_{box_id}")
                            
                        datos_ingresados_boxes.append({
                            "box_id": box_id,
                            "mh": mh, "mm": mm, "dh": dh, "dm": dm,
                            "ali": ali, "agu": agu, "ph": ph, "pm": pm
                        })

                # CÁLCULOS TOTALIZADOS Y PROMEDIOS PARA EL LOTE
                tot_mh = sum(item["mh"] for item in datos_ingresados_boxes)
                tot_mm = sum(item["mm"] for item in datos_ingresados_boxes)
                tot_dh = sum(item["dh"] for item in datos_ingresados_boxes)
                tot_dm = sum(item["dm"] for item in datos_ingresados_boxes)
                tot_ali = sum(item["ali"] for item in datos_ingresados_boxes)
                tot_agu = sum(item["agu"] for item in datos_ingresados_boxes)
                
                # Promedios ponderados sencillos para peso de lote
                pesos_h = [item["ph"] for item in datos_ingresados_boxes if item["ph"] > 0]
                pesos_m = [item["pm"] for item in datos_ingresados_boxes if item["pm"] > 0]
                
                prom_ph = (sum(pesos_h) / len(pesos_h)) if pesos_h else 0.0
                prom_pm = (sum(pesos_m) / len(pesos_m)) if pesos_m else 0.0
                prom_mix = (prom_ph + prom_pm) / 2 if (prom_ph > 0 and prom_pm > 0) else (prom_ph or prom_pm)

                st.markdown("---")
                st.subheader("📊 Consolidado Automático del Lote (Día Actual)")
                
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Mortalidad Total", f"{tot_mh + tot_mm} aves")
                k2.metric("Descarte Total", f"{tot_dh + tot_dm} aves")
                k3.metric("Alimento Consumido", f"{tot_ali:.1f} kg")
                k4.metric("Agua Consumida", f"{tot_agu:.1f} L")

                btn_label = "Actualizar Registro Diario" if registro_previo else "Guardar Registro Diario del Lote"
                if st.button(btn_label, type="primary"):
                    reg_general = {
                        "lote_id": lote_info["id"],
                        "fecha": str(fecha_registro),
                        "dia_vida": int(dia_vida_calculado),
                        "mortalidad_hembra": tot_mh,
                        "mortalidad_macho": tot_mm,
                        "descarte_hembra": tot_dh,
                        "descarte_macho": tot_dm,
                        "descartes": tot_dh + tot_dm,
                        "consumo_alimento_kg": tot_ali,
                        "consumo_agua_litros": tot_agu,
                        "peso_promedio_hembra_g": prom_ph,
                        "peso_promedio_macho_g": prom_pm,
                        "peso_promedio_mixto_g": prom_mix
                    }
                    
                    if registro_previo:
                        reg_id = registro_previo["id"]
                        supabase.table("registros_diarios").update(reg_general).eq("id", reg_id).execute()
                        supabase.table("registros_diarios_box").delete().eq("registro_diario_id", reg_id).execute()
                    else:
                        res_reg_ins = supabase.table("registros_diarios").insert(reg_general).execute()
                        reg_id = res_reg_ins.data[0]["id"]
                        
                    filas_reg_box = [
                        {
                            "registro_diario_id": reg_id,
                            "box_id": b["box_id"],
                            "mortalidad_hembra": b["mh"],
                            "mortalidad_macho": b["mm"],
                            "descarte_hembra": b["dh"],
                            "descarte_macho": b["dm"],
                            "consumo_alimento_kg": b["ali"],
                            "consumo_agua_litros": b["agu"],
                            "peso_promedio_hembra_g": b["ph"],
                            "peso_promedio_macho_g": b["pm"]
                        }
                        for b in datos_ingresados_boxes
                    ]
                    supabase.table("registros_diarios_box").insert(filas_reg_box).execute()
                    
                    st.success("¡Registro diario por box y consolidado de lote guardado exitosamente!")
                    st.rerun()
    else:
        st.info("No hay lotes activos actualmente.")

# ---------------------------------------------------------
# 5. ANÁLISIS GERENCIAL
# ---------------------------------------------------------
elif opcion == "📈 Análisis Gerencial":
    st.header("📈 Análisis Gerencial de Lotes")
    res = supabase.table("registros_diarios").select("*, lotes(codigo_lote, linea_genetica)").execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        st.subheader("Tabla Consolidada de Registros General")
        st.dataframe(df, use_container_width=True)
        
        st.subheader("Evolución de Pesos Promedio")
        st.line_chart(df, x="dia_vida", y=["peso_promedio_mixto_g", "peso_promedio_hembra_g", "peso_promedio_macho_g"])
        
        st.subheader("Consumo Diario de Alimento (kg)")
        st.bar_chart(df, x="dia_vida", y="consumo_alimento_kg")
    else:
        st.info("Aún no hay datos cargados.")
