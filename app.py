import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from html import escape
import folium
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from supabase import ClientOptions, create_client

st.set_page_config(
    page_title="AviData · Gestión avícola",
    page_icon="🐓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --avi-forest: #174EA6;
      --avi-green: #0B57D0;
      --avi-mint: #DDEAFF;
      --avi-ink: #1F2937;
      --avi-muted: #46566C;
      --avi-line: #D8E2F0;
      --avi-paper: #FFFFFF;
      --avi-bg: #F8FAFD;
    }
    .stApp { background: var(--avi-bg); color: var(--avi-ink); }
    [data-testid="stHeader"] { background: var(--avi-bg); }
    [data-testid="stSidebar"] { background: #EDF3FC; border-right: 1px solid var(--avi-line); }
    [data-testid="stSidebar"] .stButton > button { border-radius: 20px; background: #F8FAFD; }
    [data-testid="stSidebar"] .stButton > button:hover { background: #DDEAFF; }
    [data-testid="stAppViewContainer"] [data-baseweb="input"],
    [data-testid="stAppViewContainer"] [data-baseweb="select"] > div {
      background-color: #EDF3FC; color: #1F2937;
    }
    [data-testid="stAppViewContainer"] input { color: #1F2937; -webkit-text-fill-color: #1F2937; }
    .avi-scroll-table {
      height: 320px; overflow: auto; border: 1px solid var(--avi-line);
      border-radius: 16px; background: var(--avi-paper);
    }
    .avi-scroll-table table { margin: 0; width: 100%; border-collapse: separate; border-spacing: 0; }
    .avi-scroll-table th, .avi-scroll-table td {
      padding: .65rem .85rem; border: 0; border-bottom: 1px solid var(--avi-line); text-align: left;
    }
    .avi-scroll-table thead th { position: sticky; top: 0; background: #EDF3FC; z-index: 1; }
    .avi-scroll-table tbody tr:nth-child(even) { background: #F8FAFD; }
    .block-container { padding-top: 2.1rem; padding-bottom: 3rem; max-width: 1500px; }
    h1, h2, h3 { color: var(--avi-ink); letter-spacing: -.025em; }
    h1 { font-size: clamp(1.8rem, 3vw, 2.5rem) !important; font-weight: 700 !important; }
    h2 { font-size: 1.45rem !important; font-weight: 650 !important; }
    .avi-brand { font-size: 1.18rem; font-weight: 750; letter-spacing: .02em; color: var(--avi-ink); }
    .avi-brand small { display:block; margin-top:.15rem; color:var(--avi-muted); font-size:.72rem; font-weight:500; letter-spacing:.08em; text-transform:uppercase; }
    .avi-side-card {
      margin:.6rem 0 .8rem; padding:.85rem .9rem; border:1px solid var(--avi-line);
      border-radius:14px; background:var(--avi-paper);
    }
    .avi-side-card .label { color:var(--avi-muted); font-size:.68rem; text-transform:uppercase; letter-spacing:.09em; }
    .avi-side-card .value { color:var(--avi-ink); font-size:.94rem; font-weight:650; margin-top:.2rem; }
    .avi-side-card .subvalue { color:var(--avi-muted); font-size:.78rem; margin-top:.14rem; }
    .avi-hero {
      display:flex; justify-content:space-between; align-items:flex-end; gap:1rem;
      margin:0 0 1.5rem; padding:1.35rem 1.55rem; border:1px solid var(--avi-line);
      border-radius:20px; background:linear-gradient(115deg,#fff 0%,#F4F8FF 65%,#E3EEFF 100%);
      box-shadow:0 8px 28px rgba(30,55,41,.045);
    }
    .avi-hero .eyebrow { margin:0 0 .35rem; color:var(--avi-green); font-size:.72rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }
    .avi-hero h1 { margin:0; color:var(--avi-ink); }
    .avi-hero .description { margin:.35rem 0 0; color:var(--avi-muted); font-size:.94rem; }
    .avi-role-pill { padding:.42rem .72rem; border-radius:999px; background:var(--avi-mint); color:var(--avi-forest); font-size:.78rem; font-weight:700; white-space:nowrap; }
    [data-testid="stMetric"] {
      padding:1rem 1.15rem; border:1px solid var(--avi-line); border-radius:16px;
      background:var(--avi-paper); box-shadow:0 5px 18px rgba(30,55,41,.035);
    }
    [data-testid="stMetricLabel"] { color:var(--avi-muted); font-weight:600; }
    [data-testid="stMetricValue"] { color:var(--avi-forest); font-weight:750; }
    .stButton > button, [data-testid="stFormSubmitButton"] > button {
      border-radius:10px; font-weight:650; transition:all .16s ease;
    }
    .stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"] {
      background:var(--avi-green); border-color:var(--avi-green); color:white;
    }
    .stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover { transform:translateY(-1px); }
    [data-testid="stDataFrame"], [data-testid="stTable"] { border:1px solid var(--avi-line); border-radius:14px; overflow:hidden; }
    [data-testid="stForm"] { padding:1.1rem; border:1px solid var(--avi-line); border-radius:16px; background:#fff; }
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stDateInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div { border-radius:10px; }
    .avi-section-label { margin:.6rem 0 .25rem; color:var(--avi-muted); font-size:.67rem; font-weight:700; letter-spacing:.11em; text-transform:uppercase; }
    @media (max-width: 760px) {
      .block-container { padding:1.1rem .9rem 2rem; }
      .avi-hero { align-items:flex-start; flex-direction:column; padding:1.1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

URL = os.getenv("SUPABASE_URL", "https://zmpqrcqadrxevqyshvak.supabase.co")
KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_--thXNjoDX0MmxrcOBFCLg_Lo5hHeCG")
supabase = create_client(
    URL, KEY, options=ClientOptions(auto_refresh_token=False, persist_session=False)
)

# Only a random identifier goes to the browser. Supabase tokens stay on the server.
@st.cache_resource
def browser_sessions():
    return {}, Lock()


sessions, sessions_lock = browser_sessions()
session_lifetime = 12 * 60 * 60
remember_session = st.components.v2.component(
    "avidata_browser_session",
    html="<span hidden></span>",
    js="""
    export default ({ data, setStateValue }) => {
        const key = "avidata.browser-session.v1";
        let handle = "";
        try {
            if (data.clear && localStorage.getItem(key) === data.clear) {
                localStorage.removeItem(key);
            }
            if (data.save) localStorage.setItem(key, data.save);
            handle = localStorage.getItem(key) || "";
        } catch (_) {
            // Storage may be disabled. The current Streamlit connection can still sign in.
        }
        setStateValue("handle", handle);
    };
    """,
)

session_handle = st.session_state.get("avi_session_handle")
browser = remember_session(
    key="avi_browser_session",
    data={
        "save": st.session_state.pop("avi_save_handle", None),
        "clear": st.session_state.pop("avi_clear_handle", None),
    },
    on_handle_change=lambda: None,
)
if session_handle is None and isinstance(browser.handle, str) and len(browser.handle) == 43:
    session_handle = browser.handle
    with sessions_lock:
        if session_handle in sessions:
            st.session_state["avi_session_handle"] = session_handle


def clear_browser_session():
    with sessions_lock:
        sessions.pop(st.session_state.get("avi_session_handle"), None)
    st.session_state["avi_clear_handle"] = st.session_state.get("avi_session_handle")
    st.session_state["avi_session_handle"] = ""


def sign_out():
    clear_browser_session()
    try:
        supabase.auth.sign_out()
    finally:
        st.rerun()


active_session = None
with sessions_lock:
    now = monotonic()
    for handle, (deadline, _) in list(sessions.items()):
        if deadline <= now:
            del sessions[handle]
    saved = sessions.get(session_handle)
    if saved:
        deadline, saved_session = saved
        try:
            active_session = supabase.auth.set_session(
                saved_session.access_token, saved_session.refresh_token
            ).session
            if active_session:
                sessions[session_handle] = (deadline, active_session)
        except Exception:
            # A temporary Auth error should not discard the browser's session.
            st.error("No se pudo comprobar la sesión. Intenta de nuevo.")
            if st.button("Volver a iniciar sesión"):
                del sessions[session_handle]
                st.session_state["avi_clear_handle"] = session_handle
                st.session_state["avi_session_handle"] = ""
                st.rerun()
            st.stop()


# La base aplica RLS por usuario autenticado y organización.
if active_session is None:
    st.markdown(
        '<div class="avi-hero"><div><p class="eyebrow">Gestión avícola</p><h1>AviData</h1>'
        '<p class="description">Datos claros para decisiones más precisas en tu producción.</p></div>'
        '<span class="avi-role-pill">Acceso seguro</span></div>',
        unsafe_allow_html=True,
    )
    with st.form("avi_login"):
        email = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        login = st.form_submit_button("Iniciar sesión", type="primary")
    if login:
        try:
            auth = supabase.auth.sign_in_with_password({"email": email, "password": password})
            handle = token_urlsafe(32)
            with sessions_lock:
                sessions[handle] = (monotonic() + session_lifetime, auth.session)
            st.session_state["avi_session_handle"] = handle
            st.session_state["avi_save_handle"] = handle
            st.rerun()
        except Exception:
            st.error("No se pudo iniciar sesión. Verifica tus credenciales o solicita acceso al administrador.")
    st.stop()

membership_result = supabase.table("organization_memberships").select(
    "organization_id, role, organizations(name)"
).execute()
memberships = membership_result.data or []
if not memberships:
    st.markdown('<div class="avi-hero"><div><p class="eyebrow">AviData</p><h1>Conecta tu organización</h1></div></div>', unsafe_allow_html=True)
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
        sign_out()
    st.stop()

active_user_result = supabase.auth.get_user()
current_user = active_user_result.user
organization = (memberships[0].get("organizations") or {}).get("name", "Organización")
organization_id = memberships[0]["organization_id"]
current_role = memberships[0].get("role", "operator")
profile_result = supabase.table("user_profiles").select(
    "full_name, username, job_title"
).eq("user_id", current_user.id).maybe_single().execute()
profile = profile_result.data or {}
if not profile:
    guessed_name = (current_user.user_metadata or {}).get("full_name") or (current_user.email or "Usuario").split("@")[0]
    guessed_username = (current_user.email or "usuario").split("@")[0]
    profile = {"full_name": guessed_name, "username": guessed_username, "job_title": ""}

def call_user_admin(payload):
    body = json.dumps({"organization_id": organization_id, **payload}).encode("utf-8")
    req = urllib_request.Request(
        f"{URL}/functions/v1/manage-organization-users",
        data=body,
        headers={
            "Authorization": "Bearer " + active_session.access_token,
            "apikey": KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"error": f"El servidor devolvió el código {exc.code}."}
    except (URLError, TimeoutError):
        return {"error": "No se pudo conectar con el servicio de administración."}

# ---------------------------------------------------------
# NAVEGACIÓN
# ---------------------------------------------------------
st.sidebar.markdown('<div class="avi-brand">AviData<small>Gestión avícola</small></div>', unsafe_allow_html=True)
st.sidebar.markdown(
    '<div class="avi-side-card"><div class="label">Organización</div><div class="value">'
    + escape(organization) + '</div></div>', unsafe_allow_html=True
)
st.sidebar.markdown(
    '<div class="avi-side-card"><div class="label">Cuenta</div><div class="value">'
    + escape(profile.get("full_name") or "Usuario") + '</div><div class="subvalue">@'
    + escape(profile.get("username") or "usuario") + " · "
    + escape(profile.get("job_title") or "Cargo no definido") + " · Rol "
    + escape(current_role.title()) + "</div></div>", unsafe_allow_html=True
)
plan_result = supabase.table("organization_subscriptions").select("plan_code").eq(
    "organization_id", organization_id
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
    sign_out()


if "opcion_nav" not in st.session_state:
    st.session_state["opcion_nav"] = "📊 Overview General"

if st.sidebar.button("Inicio", use_container_width=True):
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

if current_role in ("owner", "admin", "analyst") and st.sidebar.button("Análisis gerencial", use_container_width=True):
    st.session_state["opcion_nav"] = "📈 Análisis Gerencial"

with st.sidebar.expander("Cuenta y organización", expanded=False):
    if st.button("Mi perfil", use_container_width=True):
        st.session_state["opcion_nav"] = "Mi perfil"
    if current_role in ("owner", "admin") and st.button("Usuarios y permisos", use_container_width=True):
        st.session_state["opcion_nav"] = "Usuarios y permisos"

opcion = st.session_state["opcion_nav"]

page_meta = {
    "📊 Overview General": ("Inicio", "Vista general", "Producción en curso, registros recientes y próximos lotes a revisar."),
    "1. Granjas": ("Operación", "Granjas", "Ubicaciones y datos principales de tus granjas."),
    "2. Galpones": ("Operación", "Galpones", "Capacidad e infraestructura de producción."),
    "3. Lotes": ("Producción", "Lotes", "Alojamiento, genética y distribución de aves."),
    "4. Ingreso Diario": ("Producción", "Registro diario", "Captura de indicadores por box y lote."),
    "📈 Análisis Gerencial": ("Inteligencia productiva", "Análisis gerencial", "Indicadores para entender la evolución de tu producción."),
}
if opcion in page_meta:
    eyebrow, page_title, page_description = page_meta[opcion]
    st.markdown(
        '<div class="avi-hero"><div><p class="eyebrow">' + escape(eyebrow) + '</p><h1>'
        + escape(page_title) + '</h1><p class="description">' + escape(page_description)
        + '</p></div><span class="avi-role-pill">' + escape(organization)
        + '</span></div>', unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# HELPER: SALDOS DE AVES Y BOXES POR LOTE
# ---------------------------------------------------------
def consulta_lotes_organizacion():
    return supabase.table("lotes").select(
        "*,galpones!inner(id,nombre,capacidad,granjas!inner(id,nombre,organization_id))"
    ).eq("galpones.granjas.organization_id", organization_id)


def listar_filas(crear_consulta):
    """Read all matching rows despite the API's per-request row limit."""
    filas = []
    pagina = 500
    while True:
        inicio = len(filas)
        lote = crear_consulta().order("id").range(inicio, inicio + pagina - 1).execute().data or []
        filas.extend(lote)
        if len(lote) < pagina:
            return filas


CAMPOS_DIARIOS = (
    "mortalidad_hembra", "mortalidad_macho", "descarte_hembra", "descarte_macho",
    "consumo_alimento_kg", "consumo_agua_litros",
)
CAMPOS_PESO = ("peso_promedio_hembra_g", "peso_promedio_macho_g")


def obtener_diarios(lotes_ids, desde=None):
    if not lotes_ids:
        return []
    diarios = []
    # Keep the URL size bounded when an organization has many lots.
    for inicio in range(0, len(lotes_ids), 100):
        ids = lotes_ids[inicio:inicio + 100]

        def consulta():
            query = supabase.table("registros_diarios").select(
                "id,lote_id,fecha,dia_vida,descartes,peso_promedio_mixto_g,"
                + ",".join(CAMPOS_DIARIOS + CAMPOS_PESO)
                + ",registros_diarios_box(" + ",".join(CAMPOS_DIARIOS + CAMPOS_PESO) + ")"
            ).in_("lote_id", ids)
            return query.gte("fecha", str(desde)) if desde else query

        diarios.extend(listar_filas(consulta))

    for fila in diarios:
        boxes = fila.pop("registros_diarios_box", None)
        if boxes:
            for campo in CAMPOS_DIARIOS:
                fila[campo] = sum(box.get(campo) or 0 for box in boxes)
            for campo in CAMPOS_PESO:
                pesos = [box[campo] for box in boxes if (box.get(campo) or 0) > 0]
                fila[campo] = sum(pesos) / len(pesos) if pesos else None
        pesos = [fila[campo] for campo in CAMPOS_PESO if (fila.get(campo) or 0) > 0]
        if boxes or not fila.get("peso_promedio_mixto_g"):
            fila["peso_promedio_mixto_g"] = sum(pesos) / len(pesos) if pesos else None
        fila["mortalidad"] = sum(fila.get(campo) or 0 for campo in CAMPOS_DIARIOS[:2])
        descartes = sum(fila.get(campo) or 0 for campo in CAMPOS_DIARIOS[2:4])
        fila["bajas"] = fila["mortalidad"] + (descartes if boxes else descartes or fila.get("descartes") or 0)
    return diarios


def obtener_saldos_lotes(lotes=None, diarios=None):
    if lotes is None:
        lotes = listar_filas(lambda: consulta_lotes_organizacion().eq("activo", True))
    if diarios is None:
        diarios = obtener_diarios([lote["id"] for lote in lotes])

    bajas_por_lote = {}
    for fila in diarios:
        bajas = bajas_por_lote.setdefault(fila["lote_id"], [0, 0, 0])
        bajas[0] += (fila.get("mortalidad_hembra") or 0) + (fila.get("descarte_hembra") or 0)
        bajas[1] += (fila.get("mortalidad_macho") or 0) + (fila.get("descarte_macho") or 0)
        bajas[2] += fila["bajas"]

    saldos = {}
    for lote in lotes:
        bajas_h, bajas_m, bajas_totales = bajas_por_lote.get(lote["id"], (0, 0, 0))
        saldos[lote["id"]] = {
            "lote": lote,
            "saldo_h": max(0, (lote.get("aves_hembra") or 0) - bajas_h),
            "saldo_m": max(0, (lote.get("aves_macho") or 0) - bajas_m),
            "saldo_total": max(0, (lote.get("aves_totales") or 0) - bajas_totales),
        }
    return saldos


def mostrar_tabla(filas, etiqueta):
    tabla = pd.DataFrame(filas).to_html(index=False, escape=True, border=0)
    st.markdown(
        '<div class="avi-scroll-table" tabindex="0" role="region" aria-label="'
        + escape(etiqueta) + '">' + tabla + '</div>',
        unsafe_allow_html=True,
    )


def mostrar_lineas(series, metricas, eje_x, etiqueta_x):
    """Render the chart inside its own frame, with no external chart scripts."""
    from plotly import graph_objects as go
    from plotly.subplots import make_subplots

    columnas = 2
    filas = (len(metricas) + columnas - 1) // columnas
    fig = make_subplots(rows=filas, cols=columnas, subplot_titles=[titulo for _, titulo in metricas])
    colores = ["#0B57D0", "#087F5B", "#A83A78", "#986100", "#6842C2", "#007D88"]
    for i, (nombre, datos, referencia) in enumerate(series):
        color = "#526274" if referencia else colores[i % len(colores)]
        for j, (campo, _) in enumerate(metricas):
            fila, columna = divmod(j, columnas)
            y = datos[campo].astype(object).where(datos[campo].notna(), None).tolist()
            fig.add_trace(go.Scatter(
                x=datos[eje_x].tolist(), y=y, name=escape(nombre),
                legendgroup=str(i), showlegend=j == 0,
                mode="lines+markers", marker={"size": 4},
                line={"color": color, "dash": "dash" if referencia else "solid", "width": 2.5},
                hovertemplate="%{x}<br>%{y:,.2f}",
            ), row=fila + 1, col=columna + 1)
    alto = filas * 315 + 85
    fig.update_xaxes(title_text=etiqueta_x, gridcolor="#E3EAF4")
    fig.update_yaxes(gridcolor="#E3EAF4", rangemode="tozero")
    fig.update_layout(
        height=alto, template="plotly_white", margin={"l": 56, "r": 20, "t": 48, "b": 20},
        legend={"orientation": "h", "y": -0.18}, font={"color": "#1F2937"},
    )
    components.html(fig.to_html(
        full_html=False, include_plotlyjs=True, config={"displaylogo": False, "responsive": True},
    ), height=alto + 12)


def series_productivas(diarios, lotes):
    df = pd.DataFrame(diarios)
    if df.empty:
        return df
    df = df.dropna(subset=["dia_vida"]).sort_values(["lote_id", "dia_vida"])
    aves = df["lote_id"].map({lote["id"]: lote.get("aves_totales") for lote in lotes}).astype(float)
    aves = aves.where(aves > 0)
    df["peso_promedio_mixto_g"] = df["peso_promedio_mixto_g"].where(df["peso_promedio_mixto_g"] > 0)
    df["alimento_g_ave"] = df["consumo_alimento_kg"] * 1000 / aves
    df["agua_ml_ave"] = df["consumo_agua_litros"] * 1000 / aves
    df["mortalidad_pct"] = df.groupby("lote_id")["mortalidad"].cumsum() * 100 / aves
    return df


def mostrar_mapa_granjas(granjas):
    puntos = []
    for granja in granjas or []:
        try:
            latitud = float(granja.get("latitud"))
            longitud = float(granja.get("longitud"))
        except (TypeError, ValueError):
            continue
        if -90 <= latitud <= 90 and -180 <= longitud <= 180:
            puntos.append(([latitud, longitud], escape(str(granja["nombre"])).replace(chr(92), "&#92;").replace("`", "&#96;").replace("$", "&#36;")))

    if not puntos:
        st.info("Aún no hay coordenadas de granjas para mostrar en el mapa.")
        return

    mapa = folium.Map(location=puntos[0][0], zoom_start=12, tiles="OpenStreetMap",
                      control_scale=True, scrollWheelZoom=False)
    for coordenadas, nombre in puntos:
        folium.CircleMarker(coordenadas, radius=8, color="#ffffff", weight=2,
                            fill=True, fill_color="#176447", fill_opacity=1,
                            tooltip=nombre).add_to(mapa)
    if len(puntos) > 1:
        mapa.fit_bounds([coordenadas for coordenadas, _ in puntos], padding=(30, 30), max_zoom=12)
    components.html(mapa.get_root().render(), height=460)


# ---------------------------------------------------------
# PERFIL Y ADMINISTRACIÓN DE ORGANIZACIÓN
# ---------------------------------------------------------
if opcion == "Mi perfil":
    st.markdown(
        '<div class="avi-hero"><div><p class="eyebrow">Cuenta de usuario</p><h1>Mi perfil</h1>'
        '<p class="description">Tu identidad y cargo dentro de la organización.</p></div>'
        '<span class="avi-role-pill">' + escape(current_role.title()) + '</span></div>',
        unsafe_allow_html=True,
    )
    st.info(f"Organización: **{organization}** · Correo: **{current_user.email or '—'}**")
    with st.form("profile_form"):
        full_name = st.text_input("Nombre completo", value=profile.get("full_name", ""))
        col_user, col_job = st.columns(2)
        with col_user:
            username = st.text_input("Nombre de usuario", value=profile.get("username", ""))
        with col_job:
            job_title = st.text_input("Cargo", value=profile.get("job_title", ""))
        if st.form_submit_button("Guardar perfil", type="primary"):
            if not full_name.strip() or not username.strip():
                st.error("El nombre y el usuario son obligatorios.")
            else:
                try:
                    supabase.table("user_profiles").upsert({
                        "user_id": current_user.id, "full_name": full_name.strip(),
                        "username": username.strip(), "job_title": job_title.strip(),
                        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    }).execute()
                    st.success("Perfil actualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar el perfil: {exc}")

elif opcion == "Usuarios y permisos" and current_role in ("owner", "admin"):
    st.markdown(
        '<div class="avi-hero"><div><p class="eyebrow">Administración de acceso</p><h1>Usuarios y permisos</h1>'
        '<p class="description">Invita a tu equipo y define qué puede hacer cada persona.</p></div>'
        '<span class="avi-role-pill">' + escape(organization) + '</span></div>',
        unsafe_allow_html=True,
    )
    st.caption("Administrador: configura usuarios y accesos · Analista: consulta análisis · Operador: registra y gestiona la operación diaria.")
    with st.expander("Invitar usuario a la organización", expanded=True):
        with st.form("invite_org_user"):
            invite_name = st.text_input("Nombre completo")
            invite_email = st.text_input("Correo electrónico")
            c_user, c_job = st.columns(2)
            with c_user:
                invite_username = st.text_input("Nombre de usuario")
            with c_job:
                invite_job = st.text_input("Cargo")
            invite_role = st.selectbox("Permiso", ["operator", "analyst", "admin"], format_func={
                "operator": "Operador · captura diaria y operación",
                "analyst": "Analista · lectura y análisis",
                "admin": "Administrador · usuarios, permisos y operación",
            }.get)
            if st.form_submit_button("Enviar invitación", type="primary"):
                result = call_user_admin({
                    "action": "invite", "email": invite_email, "full_name": invite_name,
                    "username": invite_username, "job_title": invite_job, "role": invite_role,
                })
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.success(f"Acceso asignado a {invite_email}. La persona recibirá la invitación de Supabase si aún no tiene cuenta.")
                    st.rerun()

    members_result = call_user_admin({"action": "list"})
    if members_result.get("error"):
        st.error(members_result["error"])
        st.caption("Si acabas de desplegar la función, espera unos segundos y vuelve a cargar la página.")
    else:
        members = members_result.get("members", [])
        st.subheader(f"Miembros de {members_result.get('organization', organization)} · {len(members)}")
        if members:
            st.dataframe(pd.DataFrame([{
                "Nombre": m.get("full_name") or "—", "Usuario": "@" + (m.get("username") or "—"),
                "Correo": m.get("email") or "—", "Cargo": m.get("job_title") or "—",
                "Permiso": m.get("role", "—").title(),
            } for m in members]), use_container_width=True, hide_index=True)
            editable = [m for m in members if m.get("role") != "owner" and m.get("user_id") != current_user.id]
            if editable:
                member_options = {f"{m.get('full_name') or m.get('email')} · {m.get('email')}": m for m in editable}
                selected_label = st.selectbox("Editar miembro", list(member_options))
                selected_member = member_options[selected_label]
                with st.form("edit_org_user"):
                    edit_name = st.text_input("Nombre completo", value=selected_member.get("full_name") or "")
                    edit_username = st.text_input("Nombre de usuario", value=selected_member.get("username") or "")
                    edit_job = st.text_input("Cargo", value=selected_member.get("job_title") or "")
                    role_options = ["operator", "analyst", "admin"]
                    default_role_index = role_options.index(selected_member["role"]) if selected_member.get("role") in role_options else 0
                    edit_role = st.selectbox("Permiso", role_options, index=default_role_index, format_func={
                        "operator": "Operador", "analyst": "Analista", "admin": "Administrador",
                    }.get)
                    save_member = st.form_submit_button("Guardar cambios", type="primary")
                if save_member:
                    result = call_user_admin({
                        "action": "update", "user_id": selected_member["user_id"],
                        "full_name": edit_name, "username": edit_username,
                        "job_title": edit_job, "role": edit_role,
                    })
                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        st.success("Perfil y permisos actualizados.")
                        st.rerun()
                if st.button("Retirar acceso a esta organización", type="secondary"):
                    result = call_user_admin({"action": "remove", "user_id": selected_member["user_id"]})
                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        st.success("Se retiró la membresía. La cuenta de Supabase se mantiene intacta.")
                        st.rerun()

# ---------------------------------------------------------
# OVERVIEW GENERAL
# ---------------------------------------------------------
elif opcion == "📊 Overview General":
    hoy = datetime.now(ZoneInfo("America/Bogota")).date()
    inicio_semana = hoy - timedelta(days=6)
    lotes = listar_filas(consulta_lotes_organizacion)
    activos = [lote for lote in lotes if lote["activo"]]
    cerrados = [lote for lote in lotes if lote["activo"] is False]
    diarios = obtener_diarios([lote["id"] for lote in activos])
    saldos = obtener_saldos_lotes(activos, diarios)
    aves_vivas = sum(item["saldo_total"] for item in saldos.values())
    granjas = {lote["galpones"]["granjas"]["id"] for lote in activos}
    galpones = {lote["galpones"]["id"] for lote in activos}

    st.subheader("Producción en curso")
    columnas = st.columns(4)
    columnas[0].metric("Lotes activos", len(activos))
    columnas[1].metric("Aves vivas estimadas", f"{aves_vivas:,}")
    columnas[2].metric("Galpones en producción", len(galpones))
    columnas[3].metric("Granjas en producción", len(granjas))
    st.caption("Aves vivas estimadas = aves alojadas menos bajas registradas.")

    st.subheader("Seguimiento de los últimos 7 días")
    semana = [fila for fila in diarios if str(inicio_semana) <= fila["fecha"] <= str(hoy)]
    columnas = st.columns(4)
    columnas[0].metric("Mortalidad registrada", f"{sum(fila['mortalidad'] for fila in semana):,}" if semana else "—")
    columnas[1].metric("Alimento registrado", f"{sum(fila.get('consumo_alimento_kg') or 0 for fila in semana):,.0f} kg" if semana else "—")
    columnas[2].metric("Lotes con registros", f"{len({fila['lote_id'] for fila in semana})} / {len(activos)}")
    columnas[3].metric("Lotes cerrados en el histórico", len(cerrados))

    if semana:
        tendencia = pd.DataFrame(semana).groupby("fecha", as_index=False)[
            ["mortalidad", "consumo_alimento_kg"]
        ].sum(min_count=1)
        mostrar_lineas([("Lotes activos", tendencia, False)], [
            ("consumo_alimento_kg", "Alimento diario registrado (kg)"),
            ("mortalidad", "Mortalidad diaria registrada (aves)"),
        ], "fecha", "Fecha")
    else:
        st.info("Aún no hay registros de lotes activos en este período.")

    st.subheader("Lotes de engorde a partir de 40 días")
    maduros = []
    for lote in sorted(activos, key=lambda item: item["fecha_encaste"]):
        edad = (hoy - datetime.fromisoformat(lote["fecha_encaste"]).date()).days + 1
        if lote["tipo_produccion"] == "engorde" and edad >= 40:
            maduros.append({
                "Lote": lote["codigo_lote"], "Granja": lote["galpones"]["granjas"]["nombre"],
                "Alojamiento": lote["fecha_encaste"], "Edad (días)": edad,
                "Aves vivas estimadas": saldos[lote["id"]]["saldo_total"],
            })
    if maduros:
        mostrar_tabla(maduros, "Lotes de engorde a partir de 40 días")
        st.caption("Revisa estos lotes para planear la salida. El cierre se confirma en Lotes cuando termina el ciclo.")
    else:
        st.caption("Ningún lote de engorde activo ha llegado a 40 días.")

# ---------------------------------------------------------
# 1. GESTIÓN DE GRANJAS
# ---------------------------------------------------------
elif opcion == "1. Granjas":
    if "ver_formulario_granja" not in st.session_state:
        st.session_state["ver_formulario_granja"] = False

    col_tit, col_btn = st.columns([4, 1])
    with col_tit:
        st.subheader("Gestión de granjas")
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
        granjas_registradas = listar_filas(lambda: supabase.table("granjas").select("*").eq("organization_id", organization_id))
        galpones_registrados = listar_filas(lambda: supabase.table("galpones").select(
            "*,granjas!inner(organization_id)"
        ).eq("granjas.organization_id", organization_id))
        saldos_dict = obtener_saldos_lotes()
        
        if granjas_registradas:
            df_galpones = pd.DataFrame(galpones_registrados) if galpones_registrados else pd.DataFrame()
            filas_granjas = []
            for g in granjas_registradas:
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
                
            mostrar_tabla(filas_granjas, "Listado de granjas")
            
            st.subheader("Mapa de Granjas Registradas")
            mostrar_mapa_granjas(granjas_registradas)
        else:
            st.info("No hay granjas registradas.")
    else:
        st.subheader("Registrar Nueva Granja")
        with st.form("form_granja", clear_on_submit=True):
            nombre = st.text_input("Nombre de la Granja", value="")
            col_lat, col_lng = st.columns(2)
            with col_lat:
                lat = st.number_input("Latitud", min_value=-90.0, max_value=90.0, value=4.4065, format="%.6f")
            with col_lng:
                lng = st.number_input("Longitud", min_value=-180.0, max_value=180.0, value=-75.2265, format="%.6f")
            submitted = st.form_submit_button("Guardar Granja")
            if submitted:
                if nombre.strip():
                    supabase.table("granjas").insert({"organization_id": memberships[0]["organization_id"], "nombre": nombre, "latitud": lat, "longitud": lng}).execute()
                    st.success("¡Granja guardada con éxito!")
                    st.session_state["ver_formulario_granja"] = False
                    st.rerun()
                else:
                    st.error("Ingresa el nombre de la granja.")

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
        st.subheader("Gestión de galpones")
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
        st.subheader("Gestión de lotes")
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
        estado = st.radio("Estado del lote", ["Activos", "Cerrados"], horizontal=True)
        mostrar_activos = estado == "Activos"
        lotes_lista = sorted(
            listar_filas(lambda: consulta_lotes_organizacion().eq("activo", mostrar_activos)),
            key=lambda lote: (lote["fecha_encaste"], lote["id"]), reverse=True,
        )
        if not lotes_lista:
            st.info(f"No hay lotes {estado.lower()}.")
        else:
            saldos = obtener_saldos_lotes(lotes_lista) if mostrar_activos else {}
            filas_lotes = []
            for lote in lotes_lista:
                galpon = lote["galpones"]
                fila = {
                    "Lote": lote["codigo_lote"], "Línea genética": lote["linea_genetica"],
                    "Alojamiento": lote["fecha_encaste"], "Aves alojadas": lote["aves_totales"],
                    "Galpón": galpon["nombre"], "Granja": galpon["granjas"]["nombre"],
                }
                if mostrar_activos:
                    fila["Aves vivas estimadas"] = saldos[lote["id"]]["saldo_total"]
                filas_lotes.append(fila)
            mostrar_tabla(filas_lotes, f"Lotes {estado.lower()}")

            if mostrar_activos:
                por_id = {lote["id"]: lote for lote in lotes_lista}
                lote_id = st.selectbox(
                    "Seleccionar lote para gestionar", list(por_id), index=None,
                    format_func=lambda i: f"{por_id[i]['codigo_lote']} · {por_id[i]['galpones']['granjas']['nombre']}",
                )
                if lote_id is not None:
                    editar, cerrar = st.columns(2)
                    if editar.button("Editar lote y boxes"):
                        st.session_state["lote_a_editar"] = por_id[lote_id]
                        st.rerun()
                    if current_role in ("owner", "admin"):
                        confirmado = cerrar.checkbox("Confirmo que terminó el ciclo", key=f"cerrar_{lote_id}")
                        if cerrar.button("Cerrar lote", disabled=not confirmado):
                            resultado = consulta_lotes_organizacion().eq("id", lote_id).eq("activo", True).execute()
                            if resultado.data:
                                supabase.table("lotes").update({"activo": False}).eq("id", lote_id).eq("activo", True).execute()
                            st.rerun()

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
                        vigente = consulta_lotes_organizacion().eq("id", lote_id_act).eq("activo", True).execute()
                        if not vigente.data:
                            st.error("Este lote ya está cerrado.")
                            st.stop()
                        cambios = {campo: valor for campo, valor in datos_lote.items() if campo != "activo"}
                        actualizado = supabase.table("lotes").update(cambios).eq("id", lote_id_act).eq("activo", True).execute()
                        if not actualizado.data:
                            st.error("No se pudo guardar el lote activo.")
                            st.stop()
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
    st.subheader("Registro diario por boxes y consolidado de lote")
    hoy = datetime.now(ZoneInfo("America/Bogota")).date()
    lotes_activos = listar_filas(lambda: consulta_lotes_organizacion().eq("activo", True).lte("fecha_encaste", str(hoy)))

    if lotes_activos:
        lotes_dict = {
            f"{l['codigo_lote']} · {l['galpones']['granjas']['nombre']} · {l['galpones']['nombre']}": l
            for l in lotes_activos
        }
        lote_info = lotes_dict[st.selectbox("Seleccionar Lote Activo", list(lotes_dict.keys()))]
        fecha_encaste = pd.to_datetime(lote_info["fecha_encaste"]).date()
        fecha_registro = st.date_input("Fecha del registro", value=hoy, min_value=fecha_encaste, max_value=hoy)
        captura_key = f"{lote_info['id']}_{fecha_registro}"
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
                            mh = st.number_input("Mort. Hembra", min_value=0, value=int(prev_b.get("mortalidad_hembra", 0)), key=f"mh_{captura_key}_{box_id}")
                        with c2:
                            mm = st.number_input("Mort. Macho", min_value=0, value=int(prev_b.get("mortalidad_macho", 0)), key=f"mm_{captura_key}_{box_id}")
                        with c3:
                            dh = st.number_input("Desc. Hembra", min_value=0, value=int(prev_b.get("descarte_hembra", 0)), key=f"dh_{captura_key}_{box_id}")
                        with c4:
                            dm = st.number_input("Desc. Macho", min_value=0, value=int(prev_b.get("descarte_macho", 0)), key=f"dm_{captura_key}_{box_id}")
                        with c5:
                            ali = st.number_input("Alimento (kg)", min_value=0.0, value=float(prev_b.get("consumo_alimento_kg", 0.0)), step=5.0, key=f"ali_{captura_key}_{box_id}")
                        with c6:
                            agu = st.number_input("Agua (L)", min_value=0.0, value=float(prev_b.get("consumo_agua_litros", 0.0)), step=10.0, key=f"agu_{captura_key}_{box_id}")
                        c7, c8 = st.columns(2)
                        with c7:
                            ph = st.number_input("Peso Prom. Hembra (g)", min_value=0.0, value=float(prev_b.get("peso_promedio_hembra_g", 0.0)), key=f"ph_{captura_key}_{box_id}")
                        with c8:
                            pm = st.number_input("Peso Prom. Macho (g)", min_value=0.0, value=float(prev_b.get("peso_promedio_macho_g", 0.0)), key=f"pm_{captura_key}_{box_id}")

                        valores_metricas = []
                        for metric in metricas:
                            value = st.number_input(
                                f"{metric['nombre']} ({metric['unidad']})",
                                min_value=0.0,
                                value=float(mediciones_previas.get((box_id, metric["codigo"]), 0)),
                                key=f"metric_{captura_key}_{metric['codigo']}_{box_id}",
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
                    vigente = consulta_lotes_organizacion().eq("id", lote_info["id"]).eq("activo", True).execute()
                    if not vigente.data:
                        st.error("Este lote ya está cerrado. Selecciona otro lote activo.")
                        st.stop()
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
elif opcion == "📈 Análisis Gerencial" and current_role in ("owner", "admin", "analyst"):
    lotes = listar_filas(consulta_lotes_organizacion)
    if not lotes:
        st.info("Aún no hay lotes en esta organización.")
        st.stop()

    filtros = st.columns(2)
    tipos = sorted({lote["tipo_produccion"] for lote in lotes})
    tipo = filtros[0].selectbox("Tipo de producción", tipos, format_func=str.capitalize)
    del_tipo = [lote for lote in lotes if lote["tipo_produccion"] == tipo]
    lineas = sorted({lote.get("linea_genetica") or "Sin línea registrada" for lote in del_tipo})
    linea = filtros[1].selectbox("Línea genética", lineas)
    cohorte = sorted(
        [lote for lote in del_tipo if (lote.get("linea_genetica") or "Sin línea registrada") == linea],
        key=lambda lote: (lote["fecha_encaste"], lote["id"]), reverse=True,
    )
    activos = [lote for lote in cohorte if lote["activo"]]
    historicos = [lote for lote in cohorte if lote["activo"] is False]
    por_id = {lote["id"]: lote for lote in cohorte}

    def etiqueta_lote(lote_id):
        lote = por_id[lote_id]
        return f"{lote['codigo_lote']} · {lote['galpones']['granjas']['nombre']} · {lote['fecha_encaste']}"

    st.subheader("Lotes en producción")
    ids_activos = [lote["id"] for lote in activos]
    seleccion_activos = st.multiselect(
        "Selecciona los lotes activos que quieres comparar", ids_activos,
        default=ids_activos[:1], format_func=etiqueta_lote,
        max_selections=6, disabled=not ids_activos, key=f"avi_compare_active_{tipo}_{linea}",
    )
    if not ids_activos:
        st.caption("No hay lotes activos para esta línea genética.")

    st.subheader("Referencia de ciclos cerrados")
    ids_historicos = [lote["id"] for lote in historicos]
    usar_referencia = st.checkbox("Mostrar la mediana histórica por día de vida", value=True, disabled=not ids_historicos)
    seleccion_cerrados = st.multiselect(
        "Añade lotes cerrados individuales para comparar", ids_historicos,
        format_func=etiqueta_lote, max_selections=6, disabled=not ids_historicos,
        key=f"avi_compare_closed_{tipo}_{linea}",
    )
    if not ids_historicos:
        st.caption("No hay ciclos cerrados para construir una referencia de esta línea.")

    seleccion = seleccion_activos + seleccion_cerrados
    incluir_referencia = usar_referencia and bool(ids_historicos)
    consulta_ids = sorted(set(seleccion + (ids_historicos if incluir_referencia else [])))
    datos = series_productivas(obtener_diarios(consulta_ids), cohorte)
    if datos.empty:
        st.info("Selecciona lotes con registros diarios para ver la comparación.")
        st.stop()

    metricas = [
        ("peso_promedio_mixto_g", "Peso promedio (g)"),
        ("alimento_g_ave", "Alimento diario (g/ave alojada)"),
        ("agua_ml_ave", "Agua diaria (ml/ave alojada)"),
        ("mortalidad_pct", "Mortalidad acumulada registrada (%)"),
    ]
    curvas = []
    if incluir_referencia:
        hist = datos[datos["lote_id"].isin(ids_historicos)]
        if not hist.empty:
            campos = [campo for campo, _ in metricas]
            guia = hist.groupby("dia_vida", as_index=False)[campos].median()
            n = hist["lote_id"].nunique()
            curvas.append((f"Mediana histórica · {n} lotes", guia, True))
            cobertura = hist.groupby("dia_vida")["lote_id"].nunique()
            st.caption(
                f"Referencia interna calculada con {n} lotes cerrados con registros. "
                f"Hay entre {cobertura.min()} y {cobertura.max()} lotes por día de vida."
            )
        else:
            st.caption("Los lotes cerrados de esta línea aún no tienen registros para calcular la referencia.")

    for lote_id in seleccion:
        serie = datos[datos["lote_id"] == lote_id]
        codigo = por_id[lote_id]["codigo_lote"]
        if serie.empty:
            st.caption(f"{codigo} aún no tiene registros diarios.")
        else:
            estado = "Activo" if por_id[lote_id]["activo"] else "Cerrado"
            curvas.append((f"{codigo} · {estado}", serie, False))

    if curvas:
        mostrar_lineas(curvas, metricas, "dia_vida", "Día de vida")
        st.caption("Los consumos se normalizan por aves alojadas. La mortalidad acumulada suma los registros disponibles.")
