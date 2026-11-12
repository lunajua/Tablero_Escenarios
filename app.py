import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
import os
import io

st.set_page_config(page_title="Simulador Económico Obras TASA", layout="wide")


# --- SISTEMA DE AUTENTICACIÓN ---
def check_password():
    """Retorna True si el usuario ingresó la contraseña correcta."""

    def password_entered():
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state[
                "password"
            ]  # No guardar la clave en texto plano en sesión
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.title("Acceso Restringido - Tablero TASA")
    st.text_input(
        "Ingresá la contraseña de acceso:",
        type="password",
        on_change=password_entered,
        key="password",
    )
    if (
        "password_correct" in st.session_state
        and not st.session_state["password_correct"]
    ):
        st.error("Contraseña incorrecta. Intentá nuevamente.")
    return False


if not check_password():
    st.stop()

# ==============================================================================
# A PARTIR DE AQUÍ CORRE LA APLICACIÓN PRINCIPAL
# ==============================================================================

DB_FILE = "base_tasa.db"


# --- FUNCIONES DE CÁLCULO BASE (Hoja OBRAS) ---
def calcular_pnl(
    prod_hs,
    precio_promedio,
    sueldos_factor=1.0,
    subcontrato_factor=1.0,
    estructura_base=124258230,
):
    ventas_totales = sum(prod_hs.values()) * precio_promedio

    gto_admin = 14481706
    gto_obra = 144699003
    gto_financiero = 202861006
    gto_rodados = 99558495
    mo_directa = 317979843 * sueldos_factor
    mo_indirecta = 183898310 * sueldos_factor
    subcontrato = 383307373 * subcontrato_factor
    estructura = estructura_base

    costos_totales = (
        gto_admin
        + gto_obra
        + gto_financiero
        + gto_rodados
        + mo_directa
        + mo_indirecta
        + subcontrato
        + estructura
    )

    resultado = ventas_totales - costos_totales
    margen_pct = (resultado / ventas_totales * 100) if ventas_totales > 0 else 0

    return {
        "Ventas": ventas_totales,
        "MO Directa": -mo_directa,
        "MO Indirecta": -mo_indirecta,
        "Subcontrato": -subcontrato,
        "Gastos Rodados y Maq.": -gto_rodados,
        "Gastos de Obra": -gto_obra,
        "Gastos Financieros": -gto_financiero,
        "Gastos Administración": -gto_admin,
        "Estructura": -estructura,
        "Costos Totales": -costos_totales,
        "Resultado Operativo": resultado,
        "Margen %": margen_pct,
    }


# --- FUNCIONES DE ACCESO A SQLITE E IMPORTACIÓN ---
def get_db_connection():
    return sqlite3.connect(DB_FILE)


def importar_excel_a_sqlite(uploaded_file, sheet_name, modo="Reemplazar toda la base"):
    df = pd.read_excel(uploaded_file, sheet_name=sheet_name)

    if "dfecha" in df.columns:
        df["dfecha"] = pd.to_datetime(df["dfecha"], errors="coerce").dt.strftime(
            "%Y-%m-%d"
        )

    conn = get_db_connection()
    if_exists_mode = "replace" if modo == "Reemplazar toda la base" else "append"

    df.to_sql("movimientos", conn, if_exists=if_exists_mode, index=False)

    cursor = conn.cursor()
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_zona ON movimientos ("Zona Tasa");')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_cuenta ON movimientos ("Cuenta agrupada");'
    )
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tipo ON movimientos ("Tipo Tasa");')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fecha ON movimientos ("dfecha");')
    conn.commit()
    conn.close()
    return len(df)


def obtener_valores_unicos(columna):
    if not os.path.exists(DB_FILE):
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f'SELECT DISTINCT "{columna}" FROM movimientos WHERE "{columna}" IS NOT NULL ORDER BY "{columna}"'
        )
        items = [str(r[0]) for r in cursor.fetchall()]
    except Exception:
        items = []
    conn.close()
    return items


def consultar_base(zona="TODAS", cuenta="TODAS", tipo="TODOS", limite=300):
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(), 0
    conn = get_db_connection()

    where_clauses = ["1=1"]
    params = []

    if zona != "TODAS":
        where_clauses.append('"Zona Tasa" = ?')
        params.append(zona)
    if cuenta != "TODAS":
        where_clauses.append('"Cuenta agrupada" = ?')
        params.append(cuenta)
    if tipo != "TODOS":
        where_clauses.append('"Tipo Tasa" = ?')
        params.append(tipo)

    where_sql = " AND ".join(where_clauses)

    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM movimientos WHERE {where_sql}", params)
    total_filtrado = cur.fetchone()[0]

    query = f"""
        SELECT rowid, dfecha, [nombre de las cuentas], OT, cnomcgotra, [Zona Tasa], 
               [Tipo Tasa], [Cuenta agrupada], TOTAL, Indices, [ARS Ajustados] 
        FROM movimientos 
        WHERE {where_sql} 
        LIMIT {int(limite)}
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df, total_filtrado


def actualizar_registro(rowid, updates):
    conn = get_db_connection()
    cur = conn.cursor()
    set_clauses = []
    values = []
    for col, val in updates.items():
        set_clauses.append(f'"{col}" = ?')
        values.append(val)
    values.append(rowid)

    sql = f'UPDATE movimientos SET {", ".join(set_clauses)} WHERE rowid = ?'
    cur.execute(sql, values)
    conn.commit()
    conn.close()


# --- GESTIÓN DE SESIÓN ---
if "hs_esc1" not in st.session_state:
    st.session_state["hs_esc1"] = {"LA PLATA": 11000.0, "AMBA": 13000.0, "PBA": 33000.0}
if "hs_esc2" not in st.session_state:
    st.session_state["hs_esc2"] = {"LA PLATA": 7400.0, "AMBA": 7700.0, "PBA": 11500.0}

# --- BARRA LATERAL ---
st.sidebar.title("Configuración y Variables")
if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state["password_correct"] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("1. Tarifas y Precios")
precio_base = st.sidebar.number_input(
    "Precio Promedio Ponderado Hora ($)", value=19097.75, step=100.0
)
var_precio_pct = st.sidebar.slider(
    "Variación Tarifa (%)", min_value=-50, max_value=30, value=0, step=1
)
precio_ajustado = precio_base * (1 + var_precio_pct / 100.0)

st.sidebar.subheader("2. Ajuste de Costos y Salarios")
factor_sueldos = st.sidebar.slider(
    "Ajuste Paritaria/Sueldos (%)", min_value=-20, max_value=50, value=0, step=1
)
coef_sueldo = 1.0 + (factor_sueldos / 100.0)

factor_subcon = st.sidebar.slider(
    "Variación Costo Subcontrato (%)", min_value=-50, max_value=50, value=0, step=1
)
coef_subcon = 1.0 + (factor_subcon / 100.0)

st.sidebar.markdown("---")
st.sidebar.subheader("3. Importar Excel a SQLite")
archivo_excel = st.sidebar.file_uploader(
    "Seleccionar archivo Excel (.xlsx)", type=["xlsx", "xls"]
)

if archivo_excel is not None:
    try:
        xls = pd.ExcelFile(archivo_excel)
        hojas = xls.sheet_names
        default_idx = (
            hojas.index("BASE 2025 A 08,2026") if "BASE 2025 A 08,2026" in hojas else 0
        )
        hoja_sel = st.sidebar.selectbox("Hoja a importar", hojas, index=default_idx)
        modo_imp = st.sidebar.radio(
            "Modo de importación",
            ["Reemplazar toda la base", "Agregar filas al final (Append)"],
        )
        if st.sidebar.button("🚀 Procesar e Importar a SQLite"):
            with st.spinner("Importando datos e indexando base SQLite..."):
                filas_imp = importar_excel_a_sqlite(
                    archivo_excel, hoja_sel, modo=modo_imp
                )
            st.sidebar.success(
                f"¡Listo! Se procesaron {filas_imp:,} registros en `{DB_FILE}`."
            )
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error al leer el archivo: {e}")

# Cálculos de Escenarios
res_esc1 = calcular_pnl(
    st.session_state["hs_esc1"],
    precio_promedio=precio_ajustado,
    sueldos_factor=coef_sueldo,
    subcontrato_factor=coef_subcon,
)

res_esc2 = calcular_pnl(
    st.session_state["hs_esc2"],
    precio_promedio=precio_ajustado,
    sueldos_factor=coef_sueldo * 1.08,
    subcontrato_factor=0.0,
)

# --- PESTAÑAS PRINCIPALES ---
tab_dashboard, tab_editor, tab_base = st.tabs(
    [
        "Tablero Comparativo",
        "Editor de Volúmenes por Zona",
        "Explorador y Editor Base TASA (SQLite)",
    ]
)

# --- TAB 1: DASHBOARD COMPARATIVO ---
with tab_dashboard:
    st.title("Simulador Financiero de Obras (TASA)")

    modo_vista = st.radio(
        "Seleccionar Escenario a Analizar en Detalle:",
        options=[
            "Comparativa Lado a Lado",
            "Escenario 1 (Personal Propio + Subcontratos)",
            "Escenario 2 (Solo Personal Propio)",
        ],
        horizontal=True,
    )

    st.markdown("---")

    if modo_vista == "Escenario 1 (Personal Propio + Subcontratos)":
        st.info(
            "Mostrando **ESCENARIO 1**: Se absorbe personal del subcontrato y se sostiene el nivel de producción (~57.000 hs/mes). Mantiene costo de subcontratos activo."
        )
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Ventas Totales",
            f"${res_esc1['Ventas']:,.0f}",
            f"{int(sum(st.session_state['hs_esc1'].values())):,} hs",
        )
        col2.metric("Costos Totales", f"${abs(res_esc1['Costos Totales']):,.0f}")
        col3.metric("Resultado Operativo", f"${res_esc1['Resultado Operativo']:,.0f}")
        col4.metric("Margen Neto", f"{res_esc1['Margen %']:.2f}%")

    elif modo_vista == "Escenario 2 (Solo Personal Propio)":
        st.warning(
            "Mostrando **ESCENARIO 2**: Se mantiene exclusivamente personal propio con caída en el nivel de producción (~26.600 hs/mes). Subcontratos = $0 con absorción salarial del +8%."
        )
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Ventas Totales",
            f"${res_esc2['Ventas']:,.0f}",
            f"{int(sum(st.session_state['hs_esc2'].values())):,} hs",
        )
        col2.metric("Costos Totales", f"${abs(res_esc2['Costos Totales']):,.0f}")
        col3.metric("Resultado Operativo", f"${res_esc2['Resultado Operativo']:,.0f}")
        col4.metric("Margen Neto", f"{res_esc2['Margen %']:.2f}%")

    else:
        st.markdown("### Comparativa Ejecutiva entre Escenarios")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric(
            "Ventas Esc. 1 (Propio+Sub)",
            f"${res_esc1['Ventas']:,.0f}",
            f"{int(sum(st.session_state['hs_esc1'].values())):,} hs",
        )
        kpi2.metric(
            "Resultado Esc. 1",
            f"${res_esc1['Resultado Operativo']:,.0f}",
            f"{res_esc1['Margen %']:.1f}% margen",
        )
        kpi3.metric(
            "Ventas Esc. 2 (Solo Propio)",
            f"${res_esc2['Ventas']:,.0f}",
            f"{int(sum(st.session_state['hs_esc2'].values())):,} hs",
        )
        kpi4.metric(
            "Resultado Esc. 2",
            f"${res_esc2['Resultado Operativo']:,.0f}",
            f"{res_esc2['Margen %']:.1f}% margen",
        )

    st.markdown("---")

    col_g1, col_g2 = st.columns([1.2, 1])
    with col_g1:
        st.subheader("Ingresos vs Costos por Escenario")
        df_comp = pd.DataFrame(
            {
                "Métrica": ["Ventas", "Costos Operativos", "Resultado Operativo"],
                "Escenario 1 (Propio + Sub)": [
                    res_esc1["Ventas"],
                    abs(res_esc1["Costos Totales"]),
                    res_esc1["Resultado Operativo"],
                ],
                "Escenario 2 (Solo Propio)": [
                    res_esc2["Ventas"],
                    abs(res_esc2["Costos Totales"]),
                    res_esc2["Resultado Operativo"],
                ],
            }
        )

        fig_bar = go.Figure(
            data=[
                go.Bar(
                    name="Escenario 1 (Propio + Sub)",
                    x=df_comp["Métrica"],
                    y=df_comp["Escenario 1 (Propio + Sub)"],
                    marker_color="#1f77b4",
                ),
                go.Bar(
                    name="Escenario 2 (Solo Propio)",
                    x=df_comp["Métrica"],
                    y=df_comp["Escenario 2 (Solo Propio)"],
                    marker_color="#ff7f0e",
                ),
            ]
        )
        fig_bar.update_layout(
            barmode="group",
            template="plotly_white",
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
        res_torta = (
            res_esc1
            if "Escenario 1" in modo_vista or modo_vista == "Comparativa Lado a Lado"
            else res_esc2
        )
        esc_nombre = "Escenario 1" if res_torta == res_esc1 else "Escenario 2"
        st.subheader(f"Estructura de Costos ({esc_nombre})")
        costos_dict = {
            "MO Directa": abs(res_torta["MO Directa"]),
            "MO Indirecta": abs(res_torta["MO Indirecta"]),
            "Subcontrato": abs(res_torta["Subcontrato"]),
            "Financieros": abs(res_torta["Gastos Financieros"]),
            "Obra": abs(res_torta["Gastos de Obra"]),
            "Estructura/Admin": abs(
                res_torta["Estructura"] + res_torta["Gastos Administración"]
            ),
            "Rodados": abs(res_torta["Gastos Rodados y Maq."]),
        }
        fig_pie = px.pie(
            values=list(costos_dict.values()), names=list(costos_dict.keys()), hole=0.45
        )
        fig_pie.update_layout(margin=dict(l=10, r=10, t=20, b=20))
        st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Estado de Resultados Comparativo Detallado")
    lineas = [
        "Ventas",
        "Estructura",
        "Gastos Administración",
        "Gastos de Obra",
        "Gastos Financieros",
        "Gastos Rodados y Maq.",
        "MO Directa",
        "MO Indirecta",
        "Subcontrato",
        "Costos Totales",
        "Resultado Operativo",
    ]
    df_pnl = pd.DataFrame(
        {
            "Concepto": lineas,
            "Escenario 1 (Propio + Sub)": [f"${res_esc1[k]:,.2f}" for k in lineas],
            "Escenario 2 (Solo Propio)": [f"${res_esc2[k]:,.2f}" for k in lineas],
            "Diferencia (Esc 1 - Esc 2)": [
                f"${(res_esc1[k] - res_esc2[k]):,.2f}" for k in lineas
            ],
        }
    )
    st.dataframe(df_pnl, use_container_width=True, hide_index=True)

# --- TAB 2: EDITOR DE HORAS POR ZONA ---
with tab_editor:
    st.subheader("Modificar Horas Estimadas por Distrito")
    st.info(
        "Editá directamente los números en las celdas y presioná 'Guardar y Recalcular' para actualizar ambos escenarios."
    )

    df_hs = pd.DataFrame(
        [
            {
                "Zona": "LA PLATA",
                "Escenario 1 (Hs)": float(st.session_state["hs_esc1"]["LA PLATA"]),
                "Escenario 2 (Hs)": float(st.session_state["hs_esc2"]["LA PLATA"]),
            },
            {
                "Zona": "AMBA",
                "Escenario 1 (Hs)": float(st.session_state["hs_esc1"]["AMBA"]),
                "Escenario 2 (Hs)": float(st.session_state["hs_esc2"]["AMBA"]),
            },
            {
                "Zona": "PBA",
                "Escenario 1 (Hs)": float(st.session_state["hs_esc1"]["PBA"]),
                "Escenario 2 (Hs)": float(st.session_state["hs_esc2"]["PBA"]),
            },
        ]
    )

    edited_hs = st.data_editor(df_hs, num_rows="fixed", use_container_width=True)

    if st.button("Guardar y Recalcular Horas"):
        for _, row in edited_hs.iterrows():
            z = row["Zona"]
            st.session_state["hs_esc1"][z] = float(row["Escenario 1 (Hs)"])
            st.session_state["hs_esc2"][z] = float(row["Escenario 2 (Hs)"])
        st.success("¡Horas actualizadas y recalculadas con éxito!")
        st.rerun()

# --- TAB 3: EXPLORADOR Y EDITOR CON SQLITE ---
with tab_base:
    st.subheader("Explorador y Editor Directo sobre SQLite (`base_tasa.db`)")

    if not os.path.exists(DB_FILE):
        st.warning(
            f"No se encontró el archivo `{DB_FILE}`. Podés importar tu Excel directamente desde la sección **3. Importar Excel a SQLite** en la barra lateral."
        )
    else:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            zonas = ["TODAS"] + obtener_valores_unicos("Zona Tasa")
            sel_zona = st.selectbox("Zona Tasa", zonas)
        with col_f2:
            cuentas = ["TODAS"] + obtener_valores_unicos("Cuenta agrupada")
            sel_cuenta = st.selectbox("Cuenta Agrupada", cuentas)
        with col_f3:
            tipos = ["TODOS"] + obtener_valores_unicos("Tipo Tasa")
            sel_tipo = st.selectbox("Tipo Tasa", tipos)

        col_l1, col_l2 = st.columns([1, 3])
        with col_l1:
            limite_rows = st.number_input(
                "Filas a cargar", min_value=50, max_value=2000, value=250, step=50
            )

        df_sql, total_coincidencias = consultar_base(
            sel_zona, sel_cuenta, sel_tipo, limite=limite_rows
        )

        st.caption(
            f"Registros coincidentes encontrados: **{total_coincidencias:,}** (mostrando primeros {len(df_sql)})."
        )

        cols_editables = [
            "TOTAL",
            "Indices",
            "ARS Ajustados",
            "cnomcgotra",
            "Cuenta agrupada",
        ]

        st.info(
            "Editá las celdas en la grilla y presioná **'Guardar Cambios en SQLite'** para impactar directamente en el archivo `.db`."
        )

        datos_editados = st.data_editor(
            df_sql,
            disabled=[
                "rowid",
                "dfecha",
                "nombre de las cuentas",
                "OT",
                "Zona Tasa",
                "Tipo Tasa",
            ],
            use_container_width=True,
            num_rows="fixed",
            key="grilla_sqlite",
        )

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("💾 Guardar Cambios en SQLite"):
                cambios = 0
                for idx, row in datos_editados.iterrows():
                    orig_row = df_sql.loc[idx]
                    updates = {}
                    for c in cols_editables:
                        if row[c] != orig_row[c]:
                            updates[c] = row[c]

                    if updates:
                        actualizar_registro(int(row["rowid"]), updates)
                        cambios += 1

                if cambios > 0:
                    st.success(
                        f"¡Se actualizaron {cambios} registros directamente en `{DB_FILE}`!"
                    )
                    st.rerun()
                else:
                    st.info("No se detectaron modificaciones en las celdas editables.")

        with col_b2:
            csv_data = (
                df_sql.drop(columns=["rowid"]).to_csv(index=False).encode("utf-8")
            )
            st.download_button(
                label="📥 Descargar Vista Filtrada (CSV)",
                data=csv_data,
                file_name="tasa_registros_filtrados.csv",
                mime="text/csv",
            )
