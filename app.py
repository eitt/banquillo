import sys
import os
import io
import calendar
import datetime
import tempfile

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Path setup ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import db_manager
import scheduler_opt

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Banquillo · Agenda La Cumbre",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Premium CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
/* === Base === */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #0D1117; color: #E6EDF3; }

/* === Sidebar === */
[data-testid="stSidebar"] {
    background: #161B22;
    border-right: 1px solid #30363D;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] p { color: #8B949E; font-size: 13px; }

/* === Tabs === */
.stTabs [data-baseweb="tab-list"] {
    background: #161B22;
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
    border: 1px solid #30363D;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #8B949E;
    border-radius: 8px;
    font-weight: 500;
    font-size: 14px;
    padding: 8px 18px;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #1F6FEB, #6E40C9) !important;
    color: #FFFFFF !important;
}

/* === Metric cards === */
[data-testid="stMetric"] {
    background: #161B22;
    border: 1px solid #30363D;
    border-left: 4px solid #1F6FEB;
    border-radius: 12px;
    padding: 16px 20px;
}
[data-testid="stMetricValue"] { color: #58A6FF; font-size: 2rem; font-weight: 700; }
[data-testid="stMetricLabel"] { color: #8B949E; font-size: 13px; }

/* === Buttons === */
.stButton > button {
    background: linear-gradient(135deg, #1F6FEB, #6E40C9);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 22px;
    transition: opacity 0.2s;
}
.stButton > button:hover { opacity: 0.85; }

/* === Download button === */
.stDownloadButton > button {
    background: #238636;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
}

/* === Inputs === */
.stTextInput input, .stNumberInput input, .stSelectbox div,
.stDateInput input, .stTimeInput input {
    background: #21262D !important;
    color: #E6EDF3 !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
}

/* === DataFrames / Tables === */
[data-testid="stDataFrame"] {
    border: 1px solid #30363D;
    border-radius: 10px;
    overflow: hidden;
}

/* === Section headers === */
.section-header {
    font-size: 18px; font-weight: 600; color: #58A6FF;
    border-bottom: 1px solid #30363D;
    padding-bottom: 8px; margin-bottom: 16px; margin-top: 24px;
}

/* === Info / Warning boxes === */
.stAlert { border-radius: 10px; }

/* === Spinner === */
.stSpinner > div { border-top-color: #1F6FEB !important; }

/* === Expander === */
.streamlit-expanderHeader {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    color: #E6EDF3 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
BARRIOS = ["La Cumbre", "Barrio 2", "Barrio 3"]
ESTADOS_CITA = ["libre", "reservada", "asistió", "no asistió"]
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_month_range(year: int, month: int):
    first = datetime.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = datetime.date(year, month, last_day)
    return str(first), str(last)

def fmt_time(t):
    """Return HH:MM from HH:MM:SS or HH:MM string."""
    if not t:
        return ""
    return str(t)[:5]

# ── Session state defaults ────────────────────────────────────────────────────
if "barrio" not in st.session_state:
    st.session_state.barrio = BARRIOS[0]
if "sel_year" not in st.session_state:
    st.session_state.sel_year = datetime.date.today().year
if "sel_month" not in st.session_state:
    st.session_state.sel_month = datetime.date.today().month

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏘️ Banquillo")
    st.markdown("---")
    st.session_state.barrio = st.selectbox(
        "Comunidad / Barrio", BARRIOS,
        index=BARRIOS.index(st.session_state.barrio), key="sb_barrio"
    )
    st.markdown("---")
    meses_es = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    sel_mes = st.selectbox("Mes", meses_es, index=st.session_state.sel_month - 1)
    st.session_state.sel_month = meses_es.index(sel_mes) + 1
    years = list(range(2024, 2028))
    st.session_state.sel_year = st.selectbox("Año", years, index=years.index(st.session_state.sel_year))

barrio   = st.session_state.barrio
sel_year = st.session_state.sel_year
sel_month = st.session_state.sel_month
fecha_ini, fecha_fin = get_month_range(sel_year, sel_month)
db_path  = db_manager.DEFAULT_DB_PATH

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard",
    "👥 Orientadores",
    "📅 Agenda y Citas",
    "⚙️ Optimización",
    "📁 Importar / Exportar",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown(f"<div class='section-header'>Panel de Control · {barrio} · {sel_mes} {sel_year}</div>",
                unsafe_allow_html=True)

    # ── Data loading ─────────────────────────────────────────────────────────
    orientadores = db_manager.get_orientadores(db_path)
    all_citas    = db_manager.get_citas(db_path)
    asignaciones = db_manager.get_asignaciones(db_path)

    # Filter by barrio + month
    def in_range(fecha_str):
        return fecha_ini <= str(fecha_str)[:10] <= fecha_fin

    asig_mes = [a for a in asignaciones if in_range(a.get("fecha",""))]
    citas_mes = [c for c in all_citas if in_range(c.get("fecha",""))]
    citas_ocup = [c for c in citas_mes if c.get("estado","libre") not in ("libre",)]

    # ── KPI metrics ──────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("👥 Orientadores", len(orientadores))
    k2.metric("🕐 Turnos del mes", len(asig_mes))
    k3.metric("✅ Citas ocupadas", len(citas_ocup))
    libre_count = len(citas_mes) - len(citas_ocup)
    k4.metric("🔓 Citas libres", libre_count)

    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns([1, 1])

    # ── Chart 1: Hours per orientador ────────────────────────────────────────
    with col_a:
        st.markdown("<div class='section-header'>Horas asignadas por orientador</div>", unsafe_allow_html=True)
        if asig_mes:
            horas = {}
            for a in asig_mes:
                name = a.get("orientador_nombre", "?")
                hi = fmt_time(a.get("hora_inicio", "00:00"))
                hf = fmt_time(a.get("hora_fin",   "00:00"))
                try:
                    h1 = int(hi[:2]) * 60 + int(hi[3:5])
                    h2 = int(hf[:2]) * 60 + int(hf[3:5])
                    horas[name] = horas.get(name, 0) + (h2 - h1) / 60
                except Exception:
                    pass
            df_h = pd.DataFrame(sorted(horas.items(), key=lambda x: -x[1]),
                                columns=["Orientador", "Horas"])
            fig = px.bar(df_h, x="Horas", y="Orientador", orientation="h",
                         color="Horas", color_continuous_scale="Blues",
                         template="plotly_dark")
            fig.update_layout(paper_bgcolor="#161B22", plot_bgcolor="#161B22",
                              coloraxis_showscale=False, margin=dict(l=0,r=0,t=10,b=0))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Sin asignaciones en este periodo.")

    # ── Chart 2: Daily appointment occupation ────────────────────────────────
    with col_b:
        st.markdown("<div class='section-header'>Ocupación de citas por día</div>", unsafe_allow_html=True)
        if citas_mes:
            df_c = pd.DataFrame(citas_mes)
            df_c["fecha_dt"] = pd.to_datetime(df_c["fecha"])
            df_c["dia"] = df_c["fecha_dt"].dt.strftime("%d %b")
            ocup = df_c[df_c["estado"] != "libre"].groupby("dia").size().reset_index(name="Ocupadas")
            total = df_c.groupby("dia").size().reset_index(name="Total")
            merged = total.merge(ocup, on="dia", how="left").fillna(0)
            merged["Libres"] = merged["Total"] - merged["Ocupadas"]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(name="Ocupadas", x=merged["dia"], y=merged["Ocupadas"],
                                  marker_color="#1F6FEB"))
            fig2.add_trace(go.Bar(name="Libres", x=merged["dia"], y=merged["Libres"],
                                  marker_color="#30363D"))
            fig2.update_layout(barmode="stack", template="plotly_dark",
                               paper_bgcolor="#161B22", plot_bgcolor="#161B22",
                               legend=dict(orientation="h", y=1.1),
                               margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, width='stretch')
        else:
            st.info("Sin citas registradas en este periodo.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ORIENTADORES CRUD
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("<div class='section-header'>👥 Gestión de Orientadores</div>", unsafe_allow_html=True)

    orientadores = db_manager.get_orientadores(db_path)
    df_o = pd.DataFrame(orientadores) if orientadores else pd.DataFrame(
        columns=["id","nombre","contacto","max_horas_semanales"])

    # ── Agregar nuevo orientador ──────────────────────────────────────────────
    with st.expander("➕ Agregar nuevo orientador"):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_nombre   = c1.text_input("Nombre", key="new_o_nombre")
        new_contacto = c2.text_input("Contacto", key="new_o_contacto")
        new_max_h    = c3.number_input("Máx. horas/semana", value=40, min_value=1, max_value=80, key="new_o_max")
        if st.button("Guardar orientador", key="btn_add_o"):
            if new_nombre.strip():
                db_manager.create_orientador(new_nombre.strip(), new_contacto.strip() or None, int(new_max_h), db_path)
                st.success(f"✅ Orientador '{new_nombre}' creado.")
                st.rerun()
            else:
                st.error("El nombre no puede estar vacío.")

    # ── Tabla editable ────────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>Lista de orientadores</div>", unsafe_allow_html=True)
    if not df_o.empty:
        edit_df = st.data_editor(
            df_o[["id","nombre","contacto","max_horas_semanales"]].rename(columns={
                "id":"ID","nombre":"Nombre","contacto":"Contacto","max_horas_semanales":"Máx. horas/sem"
            }),
            width='stretch', num_rows="fixed",
            disabled=["ID"], key="o_editor", hide_index=True
        )
        col_save, col_del = st.columns([2, 1])
        with col_save:
            if st.button("💾 Guardar cambios de orientadores", key="btn_save_o"):
                for _, row in edit_df.iterrows():
                    oid = int(row["ID"])
                    db_manager.update_orientador(oid,
                        nombre=str(row["Nombre"]).strip(),
                        contacto=str(row["Contacto"]).strip() if row["Contacto"] else None,
                        max_horas_semanales=int(row["Máx. horas/sem"]),
                        db_path=db_path)
                st.success("✅ Cambios guardados.")
                st.rerun()
        with col_del:
            del_id = st.number_input("ID a eliminar", min_value=1, step=1, key="del_o_id")
            if st.button("🗑️ Eliminar orientador", key="btn_del_o"):
                db_manager.delete_orientador(int(del_id), db_path)
                st.warning(f"Orientador ID {del_id} eliminado.")
                st.rerun()

    # ── Disponibilidades ──────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📆 Disponibilidades por orientador</div>", unsafe_allow_html=True)
    orientadores_fresh = db_manager.get_orientadores(db_path)
    nombres_map = {o["nombre"]: o["id"] for o in orientadores_fresh}
    sel_o_nombre = st.selectbox("Seleccionar orientador", list(nombres_map.keys()), key="sel_dispo_o")
    if sel_o_nombre:
        sel_o_id = nombres_map[sel_o_nombre]
        dispos = db_manager.get_disponibilidad_by_orientador(sel_o_id, db_path)
        if dispos:
            df_d = pd.DataFrame(dispos)
            st.dataframe(df_d[["id","dia_semana","fecha","hora_inicio","hora_fin","barrio"]].rename(columns={
                "id":"ID","dia_semana":"Día","fecha":"Fecha",
                "hora_inicio":"Desde","hora_fin":"Hasta","barrio":"Barrio"
            }), width='stretch', hide_index=True)
        else:
            st.info("Este orientador no tiene disponibilidades registradas.")

        with st.expander("➕ Agregar disponibilidad"):
            dc1, dc2, dc3, dc4, dc5 = st.columns([2, 2, 2, 2, 2])
            d_dia   = dc1.selectbox("Día semana", DIAS_SEMANA, key="d_dia")
            d_fecha = dc2.date_input("Fecha", value=datetime.date.today(), key="d_fecha")
            d_hi    = dc3.time_input("Hora inicio", value=datetime.time(8, 0), key="d_hi")
            d_hf    = dc4.time_input("Hora fin",   value=datetime.time(9, 0), key="d_hf")
            d_bar   = dc5.selectbox("Barrio", BARRIOS, index=BARRIOS.index(barrio), key="d_bar")
            if st.button("Agregar disponibilidad", key="btn_add_dispo"):
                db_manager.create_disponibilidad(
                    sel_o_id, d_dia, str(d_fecha),
                    d_hi.strftime("%H:%M:%S"), d_hf.strftime("%H:%M:%S"),
                    d_bar, db_path
                )
                st.success("✅ Disponibilidad agregada.")
                st.rerun()

        if dispos:
            del_dispo_id = st.number_input("ID de disponibilidad a eliminar", min_value=1, step=1, key="del_dispo_id")
            if st.button("🗑️ Eliminar disponibilidad", key="btn_del_dispo"):
                db_manager.delete_disponibilidad(int(del_dispo_id), db_path)
                st.warning("Disponibilidad eliminada.")
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AGENDA Y CITAS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown(f"<div class='section-header'>📅 Agenda · {barrio} · {sel_mes} {sel_year}</div>",
                unsafe_allow_html=True)

    all_citas_raw = db_manager.get_citas(db_path)
    citas_periodo = [c for c in all_citas_raw if in_range(c.get("fecha",""))]

    # Sidebar filters
    with st.sidebar:
        st.markdown("---")
        st.markdown("**Filtros de Agenda**")
        filter_estado = st.multiselect("Estado cita", ESTADOS_CITA,
                                       default=ESTADOS_CITA, key="filter_estado")
        orientadores_list = [o["nombre"] for o in db_manager.get_orientadores(db_path)]
        filter_orientador = st.multiselect("Orientador", orientadores_list,
                                           default=orientadores_list, key="filter_ori")

    citas_filtradas = [
        c for c in citas_periodo
        if c.get("estado","libre") in filter_estado
        and c.get("orientador_nombre","") in filter_orientador
    ]

    if not citas_filtradas:
        st.info("No hay citas para los filtros seleccionados en este periodo.")
    else:
        df_citas = pd.DataFrame(citas_filtradas)
        cols_show = ["id","fecha","hora_inicio","hora_fin","orientador_nombre",
                     "nombre_usuario","contacto_usuario","estado"]
        df_edit = df_citas[cols_show].rename(columns={
            "id":"ID Cita","fecha":"Fecha","hora_inicio":"Inicio","hora_fin":"Fin",
            "orientador_nombre":"Orientador","nombre_usuario":"Usuario",
            "contacto_usuario":"Contacto","estado":"Estado"
        }).copy()
        df_edit["Inicio"] = df_edit["Inicio"].apply(fmt_time)
        df_edit["Fin"]    = df_edit["Fin"].apply(fmt_time)

        edited = st.data_editor(
            df_edit,
            width='stretch',
            num_rows="fixed",
            disabled=["ID Cita","Fecha","Inicio","Fin","Orientador"],
            column_config={
                "Estado": st.column_config.SelectboxColumn("Estado", options=ESTADOS_CITA, required=True),
            },
            key="citas_editor",
            hide_index=True,
        )

        if st.button("💾 Guardar cambios en citas", key="btn_save_citas"):
            for _, row in edited.iterrows():
                cita_id = int(row["ID Cita"])
                db_manager.update_cita(
                    cita_id,
                    nombre_usuario=str(row["Usuario"]).strip() if row["Usuario"] else None,
                    contacto_usuario=str(row["Contacto"]).strip() if row["Contacto"] else None,
                    estado=row["Estado"],
                    db_path=db_path,
                )
            st.success("✅ Citas actualizadas correctamente.")
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — OPTIMIZACIÓN
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("<div class='section-header'>⚙️ Optimización Automática de Horarios</div>",
                unsafe_allow_html=True)
    st.info(
        "El algoritmo genético asigna automáticamente los orientadores disponibles "
        "a los turnos requeridos del barrio y periodo seleccionados, respetando "
        "disponibilidades, límites semanales y evitando traslapes de horario."
    )

    oc1, oc2 = st.columns(2)
    opt_barrio = oc1.selectbox("Barrio a optimizar", BARRIOS,
                               index=BARRIOS.index(barrio), key="opt_barrio")
    opt_fi = oc1.date_input("Fecha inicio", value=datetime.date(sel_year, sel_month, 1), key="opt_fi")
    opt_ff = oc2.date_input("Fecha fin",
                             value=datetime.date(sel_year, sel_month,
                                                  calendar.monthrange(sel_year, sel_month)[1]),
                             key="opt_ff")

    oc3, oc4, oc5 = st.columns(3)
    pop_size    = oc3.slider("Tamaño de población", 30, 300, 100, 10, key="opt_pop")
    generations = oc4.slider("Generaciones",        50, 500, 200, 10, key="opt_gen")
    mut_rate    = oc5.slider("Tasa de mutación",    0.05, 0.40, 0.15, 0.01,
                             format="%.2f", key="opt_mut")

    if st.button("🚀 Ejecutar Optimización", key="btn_opt"):
        with st.spinner(f"Optimizando horarios para '{opt_barrio}'... esto puede tardar unos segundos."):
            result = scheduler_opt.optimizar_horarios(
                barrio=opt_barrio,
                fecha_inicio=str(opt_fi),
                fecha_fin=str(opt_ff),
                db_path=db_path,
                pop_size=pop_size,
                generations=generations,
                mutation_rate=mut_rate,
            )

        if result:
            an = result["analysis"]
            st.success("✅ Optimización completada y guardada en la base de datos.")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Slots totales",   an["total_slots"])
            m2.metric("Asignados",       an["assigned_slots"])
            m3.metric("Cobertura",       f"{an['cobertura_pct']:.1f}%")
            m4.metric("Fitness (penalización)", f"{result['fitness']:.0f}")

            m5, m6, m7 = st.columns(3)
            m5.metric("Traslapes",     an["overlaps"])
            m6.metric("Inválidos",     an["invalid_availabilities"])
            m7.metric("σ Horas",       f"{an['std_dev_horas']:.2f} h")

            # Horas por orientador
            st.markdown("<div class='section-header'>Horas asignadas en la optimización</div>",
                        unsafe_allow_html=True)
            nombres_dict = {o["id"]: o["nombre"] for o in result["orientadores"]}
            horas_items = [
                {"Orientador": nombres_dict.get(oid, f"ID {oid}"), "Horas": h}
                for oid, h in sorted(an["horas_totales_orientador"].items())
                if h > 0
            ]
            if horas_items:
                df_hr = pd.DataFrame(horas_items)
                fig_hr = px.bar(df_hr, x="Orientador", y="Horas",
                                color="Horas", color_continuous_scale="Purples",
                                template="plotly_dark")
                fig_hr.update_layout(paper_bgcolor="#161B22", plot_bgcolor="#161B22",
                                     coloraxis_showscale=False,
                                     margin=dict(l=0,r=0,t=10,b=0))
                st.plotly_chart(fig_hr, width='stretch')
        else:
            st.error("No se encontraron turnos para optimizar en el rango especificado.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — IMPORTAR / EXPORTAR
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("<div class='section-header'>📁 Importar / Exportar Datos</div>",
                unsafe_allow_html=True)

    ic1, ic2 = st.columns(2)

    # ── Import ────────────────────────────────────────────────────────────────
    with ic1:
        st.markdown("#### ⬆️ Importar desde Excel")
        st.caption("Carga un archivo Excel con el formato de AGENDAS LA CUMBRE. "
                   "Puedes reiniciar la base de datos o añadir a los datos existentes.")
        uploaded = st.file_uploader("Selecciona el archivo Excel (.xlsx)", type=["xlsx"], key="uploader")
        reset_db = st.checkbox("Reiniciar base de datos antes de importar", value=False, key="chk_reset")
        if uploaded and st.button("📥 Importar", key="btn_import"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name
            with st.spinner("Importando datos..."):
                db_manager.import_from_excel(tmp_path, db_path=db_path, reset=reset_db)
            os.unlink(tmp_path)
            st.success("✅ Datos importados correctamente.")
            st.rerun()

    # ── Export ────────────────────────────────────────────────────────────────
    with ic2:
        st.markdown("#### ⬇️ Descargar agenda en Excel")
        st.caption("Genera un archivo Excel con la agenda actual, organizada por mes y "
                   "con formato similar al archivo original.")
        if st.button("📤 Generar Excel", key="btn_export"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp_export = tmp.name
            with st.spinner("Generando archivo Excel..."):
                db_manager.export_to_excel(tmp_export, db_path=db_path)
            with open(tmp_export, "rb") as f:
                export_bytes = f.read()
            os.unlink(tmp_export)
            st.download_button(
                label="💾 Descargar AGENDAS_BANQUILLO.xlsx",
                data=export_bytes,
                file_name="AGENDAS_BANQUILLO.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_btn"
            )

    # ── Current DB stats ──────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📊 Estado actual de la base de datos</div>",
                unsafe_allow_html=True)
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric("Orientadores",    len(db_manager.get_orientadores(db_path)))
    sc2.metric("Disponibilidades", len(db_manager.get_disponibilidades(db_path)))
    sc3.metric("Turnos requeridos", len(db_manager.get_turnos_requeridos(db_path)))
    sc4.metric("Asignaciones",    len(db_manager.get_asignaciones(db_path)))
    sc5.metric("Citas",           len(db_manager.get_citas(db_path)))
