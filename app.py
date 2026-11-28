import os
from analytics import build_production_series
from operations_ui import render_operations
from ui_design import get_theme_css
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
    initial_sidebar_state="auto",
)

st.markdown(get_theme_css(), unsafe_allow_html=True)

def configuracion(nombre):
    valor = os.environ.get(nombre, "").strip()
    if valor:
        return valor
    try:
        return str(st.secrets.get(nombre, "")).strip()
    except FileNotFoundError:
        return ""


URL = configuracion("SUPABASE_URL")
KEY = configuracion("SUPABASE_PUBLISHABLE_KEY")
if not URL or not KEY:
    st.error("Configuración incompleta. Define SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY en los secretos de Streamlit o en el entorno.")
    st.stop()

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

if st.sidebar.button("Inicio", type="primary" if st.session_state["opcion_nav"] == "📊 Overview General" else "secondary", use_container_width=True):
    st.session_state["opcion_nav"] = "📊 Overview General"

with st.sidebar.container():
    st.markdown('<div class="avi-section-label">Producción</div>', unsafe_allow_html=True)
    if st.button("Granjas", type="primary" if st.session_state["opcion_nav"] == "1. Granjas" else "secondary", use_container_width=True):
        st.session_state["opcion_nav"] = "1. Granjas"
        st.session_state["ver_formulario_granja"] = False
    if st.button("Galpones", type="primary" if st.session_state["opcion_nav"] == "2. Galpones" else "secondary", use_container_width=True):
        st.session_state["opcion_nav"] = "2. Galpones"
        st.session_state["ver_formulario_galpon"] = False
        st.session_state["galpon_a_editar"] = None
    if st.button("Lotes", type="primary" if st.session_state["opcion_nav"] == "3. Lotes" else "secondary", use_container_width=True):
        st.session_state["opcion_nav"] = "3. Lotes"
        st.session_state["ver_formulario_lote"] = False
        st.session_state["lote_a_editar"] = None
    if st.button("Jornada", type="primary" if st.session_state["opcion_nav"] == "4. Ingreso Diario" else "secondary", use_container_width=True):
        st.session_state["opcion_nav"] = "4. Ingreso Diario"
    if st.button("Centro de operación", type="primary" if st.session_state["opcion_nav"] == "Centro de operación" else "secondary", use_container_width=True):
        st.session_state["opcion_nav"] = "Centro de operación"

if current_role in ("owner", "admin", "analyst") and st.sidebar.button("Análisis gerencial", type="primary" if st.session_state["opcion_nav"] == "📈 Análisis Gerencial" else "secondary", use_container_width=True):
    st.session_state["opcion_nav"] = "📈 Análisis Gerencial"

with st.sidebar.expander("Cuenta y organización", expanded=False):
    if st.button("Mi perfil", use_container_width=True):
        st.session_state["opcion_nav"] = "Mi perfil"
    if current_role in ("owner", "admin") and st.button("Usuarios y permisos", use_container_width=True):
        st.session_state["opcion_nav"] = "Usuarios y permisos"

trace_request = st.query_params.get("trace")
if trace_request and st.session_state.get("avi_last_trace") != trace_request:
    st.session_state["avi_last_trace"] = trace_request
    st.session_state["opcion_nav"] = "Centro de operación"
opcion = st.session_state["opcion_nav"]

page_meta = {
    "📊 Overview General": ("Inicio", "Vista general", "Producción en curso, registros recientes y próximos lotes a revisar."),
    "1. Granjas": ("Operación", "Granjas", "Ubicaciones y datos principales de tus granjas."),
    "2. Galpones": ("Operación", "Galpones", "Capacidad e infraestructura de producción."),
    "3. Lotes": ("Producción", "Lotes", "Alojamiento, genética y distribución de aves."),
    "4. Ingreso Diario": ("Producción", "Jornada", "Registra, revisa y envía los datos de cada lote."),
    "Centro de operación": ("Trabajo diario", "Centro de operación", "Eventos, agenda, inventarios y trazabilidad de cada producción."),
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
        "*,galpon_boxes(*),galpones!inner(id,nombre,capacidad,granjas!inner(id,nombre,organization_id))"
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
                + ",registros_diarios_box(registro_diario_id,box_id," + ",".join(CAMPOS_DIARIOS + CAMPOS_PESO) + ")"
                + ",daily_captures!inner(status,source,version)"
            ).in_("lote_id", ids).in_("daily_captures.status", ["submitted", "reviewed", "closed"])
            return query.gte("fecha", str(desde)) if desde else query

        diarios.extend(listar_filas(consulta))

    for fila in diarios:
        boxes = fila.get("registros_diarios_box") or []
        # Consolidated values are maintained atomically by database triggers.
        # Never replace population-weighted weights with means of box means.
        fila["mortalidad"] = sum(fila.get(campo) or 0 for campo in CAMPOS_DIARIOS[:2])
        descartes = sum(fila.get(campo) or 0 for campo in CAMPOS_DIARIOS[2:4])
        fila["bajas"] = fila["mortalidad"] + (descartes if boxes else descartes or fila.get("descartes") or 0)
    return diarios


def obtener_movimientos_aves(lotes):
    """Normalize paired transfers once; receipt acknowledgments do not add birds."""
    lotes_boxes = {
        str(box["id"]): (lote["id"], box["id"])
        for lote in lotes for box in lote.get("galpon_boxes", [])
    }
    # Include destinations outside the selected cohort so transfers retain identity.
    eventos = listar_filas(lambda: supabase.table("effective_operations_events").select(
        "id,lote_id,box_id,observed_at,quantity_female,quantity_male,data"
    ).eq("organization_id", organization_id).eq("kind", "bird_movement"))
    movimientos = []
    for evento in eventos:
        datos = evento.get("data") or {}
        clase = datos.get("movement")
        if clase not in ("arrival", "sale", "transfer"):
            continue
        fecha = datetime.fromisoformat(evento["observed_at"].replace("Z", "+00:00")).astimezone(
            ZoneInfo("America/Bogota")
        ).date().isoformat()
        destinos = [(evento["lote_id"], evento["box_id"], "transfer_out" if clase == "transfer" else clase)]
        if clase == "transfer":
            destino = lotes_boxes.get(str(datos.get("destination_box_id")))
            if destino:
                destinos.append((destino[0], destino[1], "transfer_in"))
        for lote_id, box_id, tipo in destinos:
            for sexo, campo in (("hembra", "quantity_female"), ("macho", "quantity_male")):
                cantidad = evento.get(campo) or 0
                if cantidad:
                    movimientos.append({"id": evento["id"] + tipo + sexo, "event_id": evento["id"], "lote_id": lote_id,
                        "box_id": box_id, "fecha": fecha, "sex": sexo, "kind": tipo, "count": cantidad})
    return movimientos


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

    movimientos = obtener_movimientos_aves(lotes)
    movimientos_por_lote = {}
    for movimiento in movimientos:
        if movimiento["fecha"] > datetime.now(ZoneInfo("America/Bogota")).date().isoformat():
            continue
        signo = -1 if movimiento["kind"] in ("sale", "transfer_out") else 1
        fila = movimientos_por_lote.setdefault(movimiento["lote_id"], [0, 0])
        fila[0 if movimiento["sex"] == "hembra" else 1] += signo * movimiento["count"]
    saldos = {}
    for lote in lotes:
        bajas_h, bajas_m, bajas_totales = bajas_por_lote.get(lote["id"], (0, 0, 0))
        entradas_h, entradas_m = movimientos_por_lote.get(lote["id"], [0, 0])
        saldos[lote["id"]] = {
            "lote": lote,
            "saldo_h": max(0, (lote.get("aves_hembra") or 0) + entradas_h - bajas_h),
            "saldo_m": max(0, (lote.get("aves_macho") or 0) + entradas_m - bajas_m),
            "saldo_total": max(0, (lote.get("aves_totales") or 0) + entradas_h + entradas_m - bajas_totales),
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
    boxes = [dict(box, lote_id=lote["id"]) for lote in lotes for box in lote.get("galpon_boxes", [])]
    detalles = [detalle for diario in diarios for detalle in diario.get("registros_diarios_box", [])]
    df = pd.DataFrame(build_production_series(diarios, lotes, boxes, detalles, movements=obtener_movimientos_aves(lotes)))
    if df.empty:
        return df
    etapas = listar_filas(lambda: supabase.table("effective_operations_events").select(
        "id,lote_id,observed_at,stage"
    ).eq("organization_id", organization_id).eq("kind", "stage"))
    por_lote_etapas = {}
    for evento in sorted(etapas, key=lambda evento: evento["observed_at"]):
        por_lote_etapas.setdefault(evento["lote_id"], []).append(evento)
    def etapa_observada(fila):
        aplicables = [evento for evento in por_lote_etapas.get(fila["lote_id"], [])
            if datetime.fromisoformat(evento["observed_at"].replace("Z", "+00:00")).astimezone(
                ZoneInfo("America/Bogota")
            ).date().isoformat() <= str(fila["fecha"])[:10]]
        return aplicables[-1]["stage"] if aplicables else "Sin etapa registrada"
    df["etapa"] = df.apply(etapa_observada, axis=1)
    return df.sort_values(["lote_id", "dia_vida"])


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

    st.subheader("¿Qué necesitas hacer hoy?")
    st.caption(f"{hoy.strftime('%d/%m/%Y')} · Elige una tarea para continuar con tu producción.")
    accesos = st.columns(3)
    if accesos[0].button("Registrar jornada" if current_role != "analyst" else "Consultar jornada",
                         type="primary", use_container_width=True, key="avi_home_daily"):
        st.session_state["opcion_nav"] = "4. Ingreso Diario"
        st.rerun()
    if accesos[1].button("Ver agenda", use_container_width=True, key="avi_home_agenda"):
        st.session_state["opcion_nav"] = "Centro de operación"
        st.session_state["op_workspace_section"] = "Agenda e incidencias"
        st.rerun()
    if current_role in ("owner", "admin", "analyst") and accesos[2].button(
        "Comparar lotes", use_container_width=True, key="avi_home_analysis"
    ):
        st.session_state["opcion_nav"] = "📈 Análisis Gerencial"
        st.rerun()
    en_fecha = [lote for lote in activos if str(lote["fecha_encaste"]) <= str(hoy)]
    enviados_hoy = {fila["lote_id"] for fila in diarios if str(fila["fecha"])[:10] == str(hoy)}
    con_envio_hoy = len(enviados_hoy.intersection(lote["id"] for lote in en_fecha))
    if en_fecha:
        st.progress(con_envio_hoy / len(en_fecha), text=f"{con_envio_hoy} de {len(en_fecha)} lotes con jornada enviada hoy")
        if con_envio_hoy < len(en_fecha):
            st.caption("Los lotes sin envío pueden estar pendientes o en borrador. Abre Jornada para ver su estado y continuar.")
    else:
        st.info("Todavía no hay lotes alojados disponibles para la jornada. Configura tu estructura en Granjas y Lotes.")

    st.subheader("Tu producción en cifras")
    columnas = st.columns(4)
    columnas[0].metric("Lotes activos", len(activos))
    columnas[1].metric("Aves vivas estimadas", f"{aves_vivas:,}")
    columnas[2].metric("Galpones en producción", len(galpones))
    columnas[3].metric("Granjas en producción", len(granjas))
    st.caption("Aves vivas estimadas = alojamiento + entradas − ventas, traslados y bajas registradas. Los borradores no son hechos confirmados.")

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
                        with st.form(f"cierre_lote_{lote_id}"):
                            alojamiento = datetime.fromisoformat(por_id[lote_id]["fecha_encaste"]).date()
                            hoy = datetime.now(ZoneInfo("America/Bogota")).date()
                            fecha_cierre = st.date_input("Fecha de salida", min_value=min(alojamiento, hoy), max_value=hoy)
                            motivo = st.selectbox("Motivo de cierre", ["Faena completa", "Venta en pie", "Traslado"])
                            peso = st.number_input("Peso final medido (g)", min_value=0.0, step=50.0)
                            confirmado = st.checkbox("Confirmo que terminó el ciclo de este lote")
                            guardar = st.form_submit_button("Confirmar cierre")
                        if guardar:
                            if not confirmado or peso <= 0:
                                st.error("Confirma el cierre e ingresa un peso final mayor que cero.")
                            else:
                                try:
                                    supabase.rpc("close_lote", {
                                        "p_lote_id": lote_id, "p_fecha_cierre": str(fecha_cierre),
                                        "p_motivo": motivo, "p_peso_cierre_g": peso,
                                    }).execute()
                                except Exception:
                                    st.error("No se pudo cerrar. Revisa permisos, fechas y registros posteriores a la salida.")
                                else:
                                    st.success("Lote cerrado. Su historial sigue disponible en Cerrados.")
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
                    box_existente = boxes_existentes[i] if i < len(boxes_existentes) else None
                    nombre_box = box_existente["nombre_box"] if box_existente else f"Box {i+1}"
                    box_key = f"{lote_edit['id'] if es_edicion else 'nuevo'}_{box_existente['id'] if box_existente else f'nuevo_{i}'}"
                    st.markdown(f"**{nombre_box}**")
                    def_h_b = int(boxes_existentes[i]["aves_hembra_inicial"]) if i < len(boxes_existentes) else 0
                    def_m_b = int(boxes_existentes[i]["aves_macho_inicial"]) if i < len(boxes_existentes) else 0
                    
                    if modalidad_sexo in ["Sexado (Hembras / Machos)", "Mixto (As Sexed)"]:
                        b_h = st.number_input(f"Hembras Box {i+1}", min_value=0, value=def_h_b, step=100, key=f"bh_{box_key}")
                        b_m = st.number_input(f"Machos Box {i+1}", min_value=0, value=def_m_b, step=50, key=f"bm_{box_key}")
                    else:
                        b_h = st.number_input(f"Hembras Box {i+1}", min_value=0, value=def_h_b, step=100, key=f"bh_{box_key}")
                        b_m = 0
                        
                    datos_boxes_inputs.append({
                        "id": box_existente["id"] if box_existente else None,
                        "nombre_box": nombre_box,
                        "hembras": b_h,
                        "machos": b_m,
                    })

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
                    
                    # One RPC transaction preserves box IDs and rolls back the entire save on failure.
                    filas_boxes = [{
                        "id": box["id"],
                        "nombre_box": box["nombre_box"],
                        "aves_hembra_inicial": box["hembras"],
                        "aves_macho_inicial": box["machos"],
                    } for box in datos_boxes_inputs]
                    try:
                        supabase.rpc("save_lote_with_boxes", {
                            "p_lote": datos_lote,
                            "p_boxes": filas_boxes,
                            "p_lote_id": lote_edit["id"] if es_edicion else None,
                        }).execute()
                    except Exception:
                        st.error(
                            "No se pudo guardar la configuración. Comprueba tus permisos y "
                            "que el lote siga activo. Los boxes con historial deben conservarse. "
                            "Si el problema continúa, contacta al administrador."
                        )
                        st.stop()

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
elif opcion in ("4. Ingreso Diario", "Centro de operación"):
    render_operations(
        supabase, organization_id, current_user.id, current_role,
        listar_filas(consulta_lotes_organizacion),
        datetime.now(ZoneInfo("America/Bogota")).date(),
        initial_section="Jornada" if opcion == "4. Ingreso Diario" else ("Trazabilidad y análisis" if trace_request else None),
    )

# ---------------------------------------------------------
# 5. ANÁLISIS GERENCIAL
# ---------------------------------------------------------
elif opcion == "📈 Análisis Gerencial" and current_role in ("owner", "admin", "analyst"):
    lotes = listar_filas(consulta_lotes_organizacion)
    if not lotes:
        st.info("Aún no hay lotes en esta organización.")
        st.stop()

    filtros = st.columns(3)
    tipos = sorted({lote["tipo_produccion"] for lote in lotes})
    tipo = filtros[0].selectbox("Tipo de producción", tipos, format_func=str.capitalize)
    del_tipo = [lote for lote in lotes if lote["tipo_produccion"] == tipo]
    lineas = sorted({lote.get("linea_genetica") or "Sin línea registrada" for lote in del_tipo})
    linea = filtros[1].selectbox("Línea genética", lineas)
    sexo_comparacion = filtros[2].selectbox("Población representada", ["Mixta", "Hembras", "Machos"])
    cohorte = sorted(
        [lote for lote in del_tipo if (lote.get("linea_genetica") or "Sin línea registrada") == linea],
        key=lambda lote: (lote["fecha_encaste"], lote["id"]), reverse=True,
    )
    granjas_comparables = {lote["galpones"]["granjas"]["id"]: lote["galpones"]["granjas"]["nombre"] for lote in cohorte}
    granjas_elegidas = st.multiselect("Granjas de la cohorte", list(granjas_comparables),
        format_func=granjas_comparables.get, placeholder="Todas las granjas")
    if granjas_elegidas:
        cohorte = [lote for lote in cohorte if lote["galpones"]["granjas"]["id"] in granjas_elegidas]
    activos = [lote for lote in cohorte if lote["activo"]]
    historicos = [lote for lote in cohorte if lote["activo"] is False]
    por_id = {lote["id"]: lote for lote in cohorte}

    def etiqueta_lote(lote_id):
        lote = por_id[lote_id]
        return f"{lote['codigo_lote']} · {lote['galpones']['granjas']['nombre']} · {lote['fecha_encaste']}"

    st.subheader("Selección y comparación de lotes")
    ids_activos = [lote["id"] for lote in activos]
    ids_historicos = [lote["id"] for lote in historicos]
    disponibles = ids_activos + ids_historicos
    seleccion = st.multiselect(
        "Selecciona hasta 3 lotes para comparar sus curvas", disponibles,
        default=disponibles[:2], max_selections=3,
        format_func=lambda i: etiqueta_lote(i) + (" · Activo" if por_id[i]["activo"] else " · Cerrado"),
        placeholder="Elige los lotes a comparar", key=f"avi_compare_{tipo}_{linea}_{sexo_comparacion}",
    )
    usar_referencia = st.checkbox(
        "Mostrar la mediana histórica de lotes cerrados por día de vida", value=True,
        disabled=not ids_historicos,
    )
    if not seleccion and not (usar_referencia and ids_historicos):
        st.info("Selecciona un lote o activa la referencia histórica para ver los gráficos.")
        st.stop()
    incluir_referencia = usar_referencia and bool(ids_historicos)
    consulta_ids = sorted(set(seleccion + (ids_historicos if incluir_referencia else [])))
    datos = series_productivas(obtener_diarios(consulta_ids), cohorte)
    if datos.empty:
        st.info("Selecciona lotes con registros diarios para ver la comparación.")
        st.stop()

    etapas_disponibles = sorted(datos["etapa"].unique())
    etapa = st.selectbox("Etapa productiva observada", ["Todas las etapas"] + etapas_disponibles)
    if etapa != "Todas las etapas":
        datos = datos[datos["etapa"] == etapa]
    st.caption("La etapa procede de eventos registrados; no se deduce de la edad ni de una guía comercial.")
    metricas = [
        ("peso_promedio_mixto_g", "Peso promedio (g)"),
        ("fcr_acumulado", "Conversión acumulada (kg/kg biomasa viva)"),
        ("consumo_g_ave", "Alimento diario (g/ave viva)"),
        ("ratio_agua_alimento", "Agua / alimento (L/kg)"),
        ("gmd_g", "Ganancia entre pesajes (g/día)"),
        ("epef", "Índice de eficiencia productiva"),
        ("mortalidad_pct", "Mortalidad acumulada registrada (%)"),
    ]
    if sexo_comparacion != "Mixta":
        sufijo = "hembra" if sexo_comparacion == "Hembras" else "macho"
        metricas = [(f"peso_promedio_{sufijo}_g", f"Peso de {sexo_comparacion.lower()} (g)"), (f"mortalidad_{sufijo}_pct", f"Mortalidad de {sexo_comparacion.lower()} (%)")]
        st.caption("La curva por sexo representa pesos observados. La conversión mixta no se reparte por sexo sin alimento medido en ese ámbito.")
    curvas = []
    if incluir_referencia:
        hist = datos[datos["lote_id"].isin(ids_historicos)]
        if not hist.empty:
            campos = [campo for campo, _ in metricas]
            guia = hist.groupby("dia_vida", as_index=False)[campos].median()
            n = hist["lote_id"].nunique()
            curvas.append((f"Mediana histórica · {n} lotes", guia, True))
            cobertura_filas = []
            for campo, etiqueta in metricas:
                validos = hist.dropna(subset=[campo])
                dias = sorted(hist["dia_vida"].unique())
                conteos = validos.groupby("dia_vida")["lote_id"].nunique().reindex(dias, fill_value=0)
                cobertura_filas.append({
                    "Indicador": etiqueta,
                    "Mínimo de lotes válidos por día": int(conteos.min()),
                    "Máximo de lotes válidos por día": int(conteos.max()),
                })
            st.caption(
                f"Referencia interna: {n} lotes cerrados. La mediana omite valores ausentes; "
                "cada indicador tiene su propia cobertura. No equivale a una guía genética."
            )
            with st.expander("Cobertura de la referencia por indicador y día"):
                st.dataframe(pd.DataFrame(cobertura_filas), hide_index=True, use_container_width=True)
                detalle = hist.groupby("dia_vida")[campos].count().rename(
                    columns={campo: etiqueta for campo, etiqueta in metricas}
                )
                st.dataframe(detalle, use_container_width=True)
                dispersion = hist.groupby("dia_vida")[campos].quantile([0.25, 0.5, 0.75])
                st.caption("Dispersión interna: percentiles 25, 50 y 75 de valores válidos, sin completar huecos.")
                st.dataframe(dispersion, use_container_width=True)
        else:
            st.caption("Los lotes cerrados de esta línea aún no tienen registros para calcular la referencia.")

    for lote_id in seleccion:
        serie = datos[datos["lote_id"] == lote_id]
        codigo = por_id[lote_id]["codigo_lote"]
        if serie.empty:
            st.caption(f"{codigo} aún no tiene registros diarios.")
        else:
            estado = "Activo" if por_id[lote_id]["activo"] else "Cerrado"
            curvas.append((f"{codigo} · ID {lote_id} · {estado}", serie, False))

    with st.expander("Comparar con un objetivo documentado"):
        st.caption("La referencia exige genética, producción, sexo, etapa, unidad y denominador compatibles. Registrar una guía no la activa automáticamente.")
        contexto_metricas = {
            "peso_promedio_mixto_g": ("g", "ave_viva", "mixto"),
            "peso_promedio_hembra_g": ("g", "ave_viva", "hembra"),
            "peso_promedio_macho_g": ("g", "ave_viva", "macho"),
            "mortalidad_pct": ("%", "aves_iniciales", "mixto"),
            "mortalidad_hembra_pct": ("%", "aves_iniciales", "hembra"),
            "mortalidad_macho_pct": ("%", "aves_iniciales", "macho"),
            "fcr_acumulado": ("kg/kg", "biomasa_viva_kg", "mixto"),
            "consumo_g_ave": ("g/ave", "ave_viva_dia", "mixto"),
            "ratio_agua_alimento": ("L/kg", "alimento_kg", "mixto"),
            "gmd_g": ("g/día", "dias_entre_pesajes", "mixto"),
            "epef": ("índice", "edad_fcr_viabilidad", "mixto"),
        }
        referencias = listar_filas(lambda: supabase.table("production_targets").select("*").eq("organization_id", organization_id))
        origenes_referencias = listar_filas(lambda: supabase.table("effective_operations_events").select(
            "id,lote_id"
        ).eq("organization_id", organization_id).eq("kind", "target"))
        tipo_por_lote = {lote["id"]: lote["tipo_produccion"] for lote in lotes}
        ids_compatibles = {evento["id"] for evento in origenes_referencias if tipo_por_lote.get(evento["lote_id"]) == tipo}
        campos_visibles = {campo for campo, _ in metricas}
        compatibles = []
        for ref in referencias:
            contrato = contexto_metricas.get(ref.get("metric"))
            if not contrato or ref["id"] not in ids_compatibles or ref.get("metric") not in campos_visibles:
                continue
            unidad, denominador, sexo = contrato
            if (ref.get("genetics"), ref.get("sex"), ref.get("stage"), ref.get("unit"), ref.get("denominator")) == (
                linea, sexo, etapa, unidad, denominador
            ) and ref.get("edition") and ref.get("source_url"):
                compatibles.append(ref)
        por_ref = {ref["id"]: ref for ref in compatibles}
        elegidas = st.multiselect("Objetivos compatibles que quieres superponer", list(por_ref),
            format_func=lambda rid: f"{por_ref[rid]['name']} · {por_ref[rid]['edition']} · {por_ref[rid]['metric']}")
        if not compatibles:
            st.info("No hay referencias compatibles con esta selección. Selecciona una etapa registrada o incorpora una guía verificada en Centro de operación.")
        for rid in elegidas:
            ref = por_ref[rid]
            puntos = [{"dia_vida": punto["age"], **{campo: None for campo, _ in metricas},
                       ref["metric"]: punto["value"]} for punto in ref["points"]]
            curvas.append((f"Objetivo · {ref['name']} · {ref['edition']}", pd.DataFrame(puntos), True))
            st.write({"Fuente": ref["source_url"], "Edición": ref["edition"], "Denominador": ref["denominator"], "ID de versión": rid})

    if curvas:
        mostrar_lineas(curvas, metricas, "dia_vida", "Día de vida")
        st.caption("Pesos ponderados por saldo vivo de box y sexo. FCR = alimento acumulado / biomasa viva. Indicadores acumulados vacíos cuando falta cobertura; la referencia es la mediana interna de ciclos cerrados de la misma genética y producción.")
