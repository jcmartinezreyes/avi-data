import os
import streamlit as st
import pandas as pd
from supabase import create_client
from streamlit_folium import st_folium
import folium

st.set_page_config(page_title="Sistema Avícola", layout="wide")

URL = os.getenv("SUPABASE_URL", "https://zmpqrcqadrxevqyshvak.supabase.co")
KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_--thXNjoDX0MmxrcOBFCLg_Lo5hHeCG")
supabase = create_client(URL, KEY)

# La base aplica RLS por usuario autenticado y organización.
if "avi_auth_tokens" not in st.session_state:
    st.title("Sistema de Control Avícola 🐔")
    with st.form("avi_login"):
        email = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        login = st.form_submit_button("Iniciar sesión", type="primary")
    if login:
        try:
            auth = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["avi_auth_tokens"] = {
                "access_token": auth.session.access_token,
                "refresh_token": auth.session.refresh_token,
            }
            st.rerun()
        except Exception:
            st.error("No se pudo iniciar sesión. Verifica tus credenciales o solicita acceso al administrador.")
    st.stop()

try:
    supabase.auth.set_session(
        st.session_state["avi_auth_tokens"]["access_token"],
        st.session_state["avi_auth_tokens"]["refresh_token"],
    )
    active_session = supabase.auth.get_session()
    if active_session and active_session.access_token:
        st.session_state["avi_auth_tokens"] = {
            "access_token": active_session.access_token,
            "refresh_token": active_session.refresh_token,
        }
except Exception:
    st.session_state.pop("avi_auth_tokens", None)
    st.warning("La sesión expiró. Inicia sesión de nuevo.")
    st.rerun()

membership_result = supabase.table("organization_memberships").select(
    "organization_id, role, organizations(name)"
).execute()
memberships = membership_result.data or []
if not memberships:
    st.title("Sistema de Control Avícola 🐔")
    st.info("Tu usuario aún no pertenece a una organización.")
    with st.form("avi_create_organization"):
        organization_name = st.text_input("Nombre de tu organización")
        create_org = st.form_submit_button("Crear organización", type="primary")
    if create_org:
        try:
            supabase.rpc("create_organization", {"p_name": organization_name}).execute()
            st.rerun()
        except Exception:
            st.error("No se pudo crear la organización. Si ya perteneces a otra, solicita al administrador que te agregue.")
    if st.button("Cerrar sesión"):
        supabase.auth.sign_out()
        st.session_state.pop("avi_auth_tokens", None)
        st.rerun()
    st.stop()

st.title("Sistema de Control Avícola 🐔")

# ---------------------------------------------------------
# NAVEGACIÓN
# ---------------------------------------------------------
st.sidebar.title("Menú Principal")
st.sidebar.caption("Organización: " + ", ".join((m.get("organizations") or {}).get("name", "Sin nombre") for m in memberships))
plan_result = supabase.table("organization_subscriptions").select("plan_code").eq(
    "organization_id", memberships[0]["organization_id"]
).execute()
if plan_result.data:
    plan_code = plan_result.data[0]["plan_code"]
    plan_data = supabase.table("subscription_plans").select(
        "name, max_galpones, incubadora_incluida, max_incubadoras"
    ).eq("code", plan_code).execute()
    if plan_data.data:
        plan = plan_data.data[0]
        limit = "sin límite" if plan["max_galpones"] is None else str(plan["max_galpones"])
        incubator = "incluida" if plan["incubadora_incluida"] else "no incluida"
        st.sidebar.caption(f"Plan {plan['name']} · {limit} galpones · incubadora {incubator}")
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    supabase.auth.sign_out()
    st.session_state.pop("avi_auth_tokens", None)
    st.rerun()


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
    res_diarios = supabase.table("registros_diarios").select(
        "id, lote_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho"
    ).execute()
    res_box = supabase.table("registros_diarios_box").select(
        "registro_diario_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho, registros_diarios(lote_id)"
    ).execute()

    bajas_por_lote = {}
    diarios_con_detalle = set()
    for registro in (res_box.data or []):
        lote_id = (registro.get("registros_diarios") or {}).get("lote_id")
        if lote_id is None:
            continue
        diario_id = registro.get("registro_diario_id")
        diarios_con_detalle.add(diario_id)
        bajas = bajas_por_lote.setdefault(lote_id, {"bajas_h": 0, "bajas_m": 0})
        bajas["bajas_h"] += (registro.get("mortalidad_hembra") or 0) + (registro.get("descarte_hembra") or 0)
        bajas["bajas_m"] += (registro.get("mortalidad_macho") or 0) + (registro.get("descarte_macho") or 0)

    # Compatibilidad con registros históricos que solo tenían totales del lote.
    for registro in (res_diarios.data or []):
        if registro["id"] in diarios_con_detalle:
            continue
        bajas = bajas_por_lote.setdefault(registro["lote_id"], {"bajas_h": 0, "bajas_m": 0})
        bajas["bajas_h"] += (registro.get("mortalidad_hembra") or 0) + (registro.get("descarte_hembra") or 0)
        bajas["bajas_m"] += (registro.get("mortalidad_macho") or 0) + (registro.get("descarte_macho") or 0)

    saldos = {}
    for lote in (res_lotes.data or []):
        lote_id = lote["id"]
        inicial_h = lote.get("aves_hembra", 0) or 0
        inicial_m = lote.get("aves_macho", 0) or 0
        bajas = bajas_por_lote.get(lote_id, {"bajas_h": 0, "bajas_m": 0})
        saldo_h = max(0, int(inicial_h - bajas["bajas_h"]))
        saldo_m = max(0, int(inicial_m - bajas["bajas_m"]))
        saldos[lote_id] = {
            "lote": lote,
            "saldo_h": saldo_h,
            "saldo_m": saldo_m,
            "saldo_total": saldo_h + saldo_m,
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
                    supabase.table("granjas").insert({"organization_id": memberships[0]["organization_id"], "nombre": nombre, "latitud": lat, "longitud": lng}).execute()
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
                        "tipo_produccion": {"Engorde": "engorde", "Postura (Comercial)": "postura", "Reproductoras": "reproductoras"}[proposito],
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
    res_lotes = supabase.table("lotes").select("id, codigo_lote, linea_genetica, tipo_produccion, fecha_encaste, galpones(nombre)").eq("activo", True).execute()

    if res_lotes.data:
        lotes_dict = {
            f"{l['codigo_lote']} ({l['galpones']['nombre']} - {l['linea_genetica']})": l
            for l in res_lotes.data
        }
        lote_info = lotes_dict[st.selectbox("Seleccionar Lote Activo", list(lotes_dict.keys()))]
        fecha_registro = st.date_input("Fecha del Registro")
        fecha_encaste = pd.to_datetime(lote_info["fecha_encaste"]).date()
        dia_vida_calculado = (fecha_registro - fecha_encaste).days + 1

        if dia_vida_calculado < 1:
            st.error(f"La fecha de registro no puede ser anterior al encaste ({fecha_encaste}).")
        else:
            st.info(f"📅 **Día de Vida (Edad):** Día {dia_vida_calculado}")
            res_boxes = supabase.table("galpon_boxes").select("*").eq("lote_id", lote_info["id"]).order("nombre_box").execute()
            list_boxes = res_boxes.data or []

            if not list_boxes:
                st.warning("Este lote no tiene boxes configurados. Ve al menú 'Lotes' y edita el lote para agregar boxes.")
            else:
                res_existente = supabase.table("registros_diarios").select(
                    "id, lote_id, fecha, dia_vida, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho, consumo_alimento_kg, consumo_agua_litros, peso_promedio_hembra_g, peso_promedio_macho_g"
                ).eq("lote_id", lote_info["id"]).eq("fecha", str(fecha_registro)).execute()
                registro_previo = res_existente.data[0] if res_existente.data else None
                dict_reg_box_previo, mediciones_previas = {}, {}
                if registro_previo:
                    res_reg_b = supabase.table("registros_diarios_box").select("*").eq("registro_diario_id", registro_previo["id"]).execute()
                    dict_reg_box_previo = {rb["box_id"]: rb for rb in (res_reg_b.data or [])}
                    res_med = supabase.table("mediciones_produccion").select("*").eq("registro_diario_id", registro_previo["id"]).execute()
                    mediciones_previas = {(m["box_id"], m["codigo_metrica"]): m["valor"] for m in (res_med.data or [])}

                tipo = lote_info.get("tipo_produccion") or "engorde"
                catalogo = supabase.table("metricas_produccion").select("*").eq("activa", True).execute()
                metricas = [m for m in (catalogo.data or []) if tipo in (m.get("tipos_produccion") or [])]
                st.subheader("📌 Captura de Datos Diarios por Box")
                datos_ingresados_boxes = []

                for b in list_boxes:
                    box_id = b["id"]
                    prev_b = dict_reg_box_previo.get(box_id, {})
                    with st.expander(f"📦 {b['nombre_box']}", expanded=True):
                        c1, c2, c3, c4, c5, c6 = st.columns(6)
                        with c1:
                            mh = st.number_input("Mort. Hembra", min_value=0, value=int(prev_b.get("mortalidad_hembra", 0)), key=f"mh_{box_id}")
                        with c2:
                            mm = st.number_input("Mort. Macho", min_value=0, value=int(prev_b.get("mortalidad_macho", 0)), key=f"mm_{box_id}")
                        with c3:
                            dh = st.number_input("Desc. Hembra", min_value=0, value=int(prev_b.get("descarte_hembra", 0)), key=f"dh_{box_id}")
                        with c4:
                            dm = st.number_input("Desc. Macho", min_value=0, value=int(prev_b.get("descarte_macho", 0)), key=f"dm_{box_id}")
                        with c5:
                            ali = st.number_input("Alimento (kg)", min_value=0.0, value=float(prev_b.get("consumo_alimento_kg", 0.0)), step=5.0, key=f"ali_{box_id}")
                        with c6:
                            agu = st.number_input("Agua (L)", min_value=0.0, value=float(prev_b.get("consumo_agua_litros", 0.0)), step=10.0, key=f"agu_{box_id}")
                        c7, c8 = st.columns(2)
                        with c7:
                            ph = st.number_input("Peso Prom. Hembra (g)", min_value=0.0, value=float(prev_b.get("peso_promedio_hembra_g", 0.0)), key=f"ph_{box_id}")
                        with c8:
                            pm = st.number_input("Peso Prom. Macho (g)", min_value=0.0, value=float(prev_b.get("peso_promedio_macho_g", 0.0)), key=f"pm_{box_id}")

                        valores_metricas = []
                        for metric in metricas:
                            value = st.number_input(
                                f"{metric['nombre']} ({metric['unidad']})",
                                min_value=0.0,
                                value=float(mediciones_previas.get((box_id, metric["codigo"]), 0)),
                                key=f"metric_{metric['codigo']}_{box_id}",
                            )
                            valores_metricas.append({"codigo_metrica": metric["codigo"], "valor": value})

                        datos_ingresados_boxes.append({
                            "box_id": box_id,
                            "mh": mh, "mm": mm, "dh": dh, "dm": dm,
                            "ali": ali, "agu": agu, "ph": ph, "pm": pm,
                            "metricas": valores_metricas,
                        })

                tot_mh = sum(x["mh"] for x in datos_ingresados_boxes)
                tot_mm = sum(x["mm"] for x in datos_ingresados_boxes)
                tot_dh = sum(x["dh"] for x in datos_ingresados_boxes)
                tot_dm = sum(x["dm"] for x in datos_ingresados_boxes)
                tot_ali = sum(x["ali"] for x in datos_ingresados_boxes)
                tot_agu = sum(x["agu"] for x in datos_ingresados_boxes)
                st.markdown("---")
                st.subheader("📊 Consolidado Automático (calculado desde el detalle por box)")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Mortalidad Total", f"{tot_mh + tot_mm} aves")
                k2.metric("Descarte Total", f"{tot_dh + tot_dm} aves")
                k3.metric("Alimento Consumido", f"{tot_ali:.1f} kg")
                k4.metric("Agua Consumida", f"{tot_agu:.1f} L")

                label = "Actualizar Registro Diario" if registro_previo else "Guardar Registro Diario del Lote"
                if st.button(label, type="primary"):
                    header = {"lote_id": lote_info["id"], "fecha": str(fecha_registro), "dia_vida": int(dia_vida_calculado)}
                    if registro_previo:
                        reg_id = registro_previo["id"]
                        supabase.table("registros_diarios").update(header).eq("id", reg_id).execute()
                    else:
                        reg_id = supabase.table("registros_diarios").insert(header).execute().data[0]["id"]

                    filas_box = [{
                        "registro_diario_id": reg_id,
                        "box_id": x["box_id"],
                        "mortalidad_hembra": x["mh"],
                        "mortalidad_macho": x["mm"],
                        "descarte_hembra": x["dh"],
                        "descarte_macho": x["dm"],
                        "consumo_alimento_kg": x["ali"],
                        "consumo_agua_litros": x["agu"],
                        "peso_promedio_hembra_g": x["ph"],
                        "peso_promedio_macho_g": x["pm"],
                    } for x in datos_ingresados_boxes]
                    supabase.table("registros_diarios_box").upsert(
                        filas_box, on_conflict="registro_diario_id,box_id"
                    ).execute()

                    for x in datos_ingresados_boxes:
                        supabase.table("mediciones_produccion").delete().eq(
                            "registro_diario_id", reg_id
                        ).eq("box_id", x["box_id"]).execute()
                        filas_metricas = [{
                            "registro_diario_id": reg_id,
                            "box_id": x["box_id"],
                            "codigo_metrica": m["codigo_metrica"],
                            "valor": m["valor"],
                        } for m in x["metricas"]]
                        if filas_metricas:
                            supabase.table("mediciones_produccion").insert(filas_metricas).execute()

                    st.success("Registro diario guardado. Los totales se calculan desde el detalle por box.")
                    st.rerun()
    else:
        st.info("No hay lotes activos actualmente.")

# ---------------------------------------------------------
# 5. ANÁLISIS GERENCIAL
# ---------------------------------------------------------
elif opcion == "📈 Análisis Gerencial":
    st.header("📈 Análisis Gerencial de Lotes")
    res_diarios = supabase.table("registros_diarios").select(
        "id, lote_id, fecha, dia_vida, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho, consumo_alimento_kg, consumo_agua_litros, peso_promedio_mixto_g, peso_promedio_hembra_g, peso_promedio_macho_g, lotes(codigo_lote, linea_genetica)"
    ).execute()
    res_detalle = supabase.table("registros_diarios_box").select(
        "registro_diario_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho, consumo_alimento_kg, consumo_agua_litros, peso_promedio_hembra_g, peso_promedio_macho_g"
    ).execute()

    detalle_por_registro = {}
    for dato in (res_detalle.data or []):
        resumen = detalle_por_registro.setdefault(dato["registro_diario_id"], {
            "mortalidad_hembra": 0, "mortalidad_macho": 0, "descarte_hembra": 0,
            "descarte_macho": 0, "consumo_alimento_kg": 0.0, "consumo_agua_litros": 0.0,
            "pesos_h": [], "pesos_m": [],
        })
        for campo in ("mortalidad_hembra", "mortalidad_macho", "descarte_hembra", "descarte_macho", "consumo_alimento_kg", "consumo_agua_litros"):
            resumen[campo] += dato.get(campo) or 0
        if dato.get("peso_promedio_hembra_g"):
            resumen["pesos_h"].append(float(dato["peso_promedio_hembra_g"]))
        if dato.get("peso_promedio_macho_g"):
            resumen["pesos_m"].append(float(dato["peso_promedio_macho_g"]))

    filas = []
    for registro in (res_diarios.data or []):
        detalle = detalle_por_registro.get(registro["id"])
        if detalle:
            peso_h = sum(detalle["pesos_h"]) / len(detalle["pesos_h"]) if detalle["pesos_h"] else 0
            peso_m = sum(detalle["pesos_m"]) / len(detalle["pesos_m"]) if detalle["pesos_m"] else 0
            peso_mix = (peso_h + peso_m) / 2 if peso_h and peso_m else (peso_h or peso_m)
            fila = {campo: detalle[campo] for campo in (
                "mortalidad_hembra", "mortalidad_macho", "descarte_hembra",
                "descarte_macho", "consumo_alimento_kg", "consumo_agua_litros"
            )}
            fila.update({
                "peso_promedio_hembra_g": peso_h,
                "peso_promedio_macho_g": peso_m,
                "peso_promedio_mixto_g": peso_mix,
            })
        else:
            fila = {campo: registro.get(campo) or 0 for campo in (
                "mortalidad_hembra", "mortalidad_macho", "descarte_hembra", "descarte_macho",
                "consumo_alimento_kg", "consumo_agua_litros", "peso_promedio_hembra_g",
                "peso_promedio_macho_g", "peso_promedio_mixto_g"
            )}
        fila.update({
            "fecha": registro["fecha"],
            "dia_vida": registro["dia_vida"],
            "lote_id": registro["lote_id"],
            "codigo_lote": (registro.get("lotes") or {}).get("codigo_lote", ""),
            "linea_genetica": (registro.get("lotes") or {}).get("linea_genetica", ""),
        })
        filas.append(fila)

    if filas:
        df = pd.DataFrame(filas).sort_values(["lote_id", "dia_vida"])
        st.subheader("Tabla Consolidada de Registros")
        st.dataframe(df, use_container_width=True)
        st.subheader("Evolución de Pesos Promedio")
        st.line_chart(df, x="dia_vida", y=["peso_promedio_mixto_g", "peso_promedio_hembra_g", "peso_promedio_macho_g"], color="codigo_lote")
        st.subheader("Consumo Diario de Alimento (kg)")
        st.bar_chart(df, x="dia_vida", y="consumo_alimento_kg", color="codigo_lote")
    else:
        st.info("Aún no hay datos cargados.")
