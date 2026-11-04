import subprocess
import sys
import os
import re
import streamlit as st
import pandas as pd

# -------------------------------------------------------------------
# INSTALACIÓN AUTOMÁTICA DE CHROMIUM EN STREAMLIT CLOUD
# -------------------------------------------------------------------
@st.cache_resource
def instalar_navegador():
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

try:
    instalar_navegador()
except Exception as e:
    st.error(f"Error instalando el navegador: {e}")

from playwright.sync_api import sync_playwright

st.set_page_config(page_title="Buscador CNH", page_icon="🚜", layout="wide")

# Estilos visuales
st.markdown("""
<style>
    button[kind="primary"] { background-color: #C00000 !important; color: white !important; border-radius: 6px !important; font-weight: bold !important; border: none !important; padding: 0.6rem 2rem !important; }
    button[kind="primary"]:hover { background-color: #8A0000 !important; }
    button[kind="secondary"] { background-color: #222222 !important; color: white !important; font-weight: bold !important; border-radius: 6px !important; }
    h1, h2, h3 { color: #C00000 !important; }
    .stTextArea textarea { border: 1px solid #C00000 !important; }
    code { color: #C00000 !important; font-size: 15px !important; font-weight: bold !important; border-left: 5px solid #C00000 !important; }
    [data-testid="stAlert"] { background-color: #1E1E1E !important; border-left: 5px solid #C00000 !important; color: #FFFFFF !important; }
</style>
""", unsafe_allow_html=True)

# Control de estado
if "resultados" not in st.session_state:
    st.session_state.resultados = []
    st.session_state.lista_referencias = []
    st.session_state.indice_actual = 0
    st.session_state.estado = "ESPERANDO"

col_logo, col_titulo = st.columns([1.5, 5.5])
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=180)
    elif os.path.exists("logo.jpg"):
        st.image("logo.jpg", width=180)
    elif os.path.exists("logo.jpeg"):
        st.image("logo.jpeg", width=180)

with col_titulo:
    st.title("🚜 Buscador CNH - Extracción de Pesos")
    st.markdown("Consulta en **MyCNHStore (Case IH / New Holland)** | Salida principal en **Libras** y secundaria en **Kilos**.")

st.divider()

def extraer_peso_universal(texto):
    if not texto:
        return None
    
    # 1. Prioridad: Búsqueda en KG / G
    m_kg = re.search(r'(?:Package\s*Weight|Weight)[\s\n:-]*([\d\.,]+)\s*(?:kg|kilo|kilograms?)\b', texto, re.IGNORECASE)
    if not m_kg:
        m_kg = re.search(r'([\d\.,]+)\s*(?:kg|kilo|kilograms?)\b', texto, re.IGNORECASE)
    if m_kg:
        try:
            val = float(m_kg.group(1).replace(",", "."))
            return val * 2.20462262
        except: pass

    m_g = re.search(r'(?:Package\s*Weight|Weight)[\s\n:-]*([\d\.,]+)\s*(?:g|gramos?|grams?)\b', texto, re.IGNORECASE)
    if m_g:
        try:
            val = float(m_g.group(1).replace(",", "."))
            return (val / 1000.0) * 2.20462262
        except: pass

    # 2. Búsqueda si viene en Libras u Onzas
    m_lb = re.search(r'(?:Package\s*Weight|Weight)[\s\n:-]*([\d\.,]+)\s*(?:lb|lbs?)\b', texto, re.IGNORECASE)
    if not m_lb:
        m_lb = re.search(r'([\d\.,]+)\s*(?:lb|lbs?)\b', texto, re.IGNORECASE)
    if m_lb:
        try:
            return float(m_lb.group(1).replace(",", "."))
        except: pass

    m_oz = re.search(r'([\d\.,]+)\s*(?:oz|ounces?)\b', texto, re.IGNORECASE)
    if m_oz:
        try:
            return float(m_oz.group(1).replace(",", ".")) / 16.0
        except: pass

    return None

def descartar_modales_cnh(page):
    selectores = [
        "button#onetrust-accept-btn-handler",
        "button:has-text('Accept All Cookies')",
        "button:has-text('Select Later')",
        "button:has-text('Dismiss')",
        "button:has-text('Close')",
        "button[aria-label='Close']"
    ]
    for sel in selectores:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=400)
        except: pass

st.write("### 1. Pega tu lista de combate CNH:")
referencias_input = st.text_area("Referencias (una por línea):", height=150, placeholder="84269799\n47833568\n87384351")

col_btn1, col_btn2, col_btn3 = st.columns(3)

with col_btn1:
    if st.button("🚀 Iniciar Búsqueda", type="primary"):
        lista_limpia = [r.strip() for r in referencias_input.split('\n') if r.strip()]
        if lista_limpia:
            st.session_state.lista_referencias = lista_limpia
            st.session_state.resultados = []
            st.session_state.indice_actual = 0
            st.session_state.estado = "PROCESANDO"
        else:
            st.warning("Pega al menos una referencia.")

with col_btn2:
    if st.session_state.estado in ["PAUSADO", "PROCESANDO"] and 0 < st.session_state.indice_actual < len(st.session_state.lista_referencias):
        if st.button("▶️ Continuar", type="primary"):
            st.session_state.estado = "PROCESANDO"

with col_btn3:
    if st.session_state.estado == "PROCESANDO":
        if st.button("🛑 Pausar", type="secondary"):
            st.session_state.estado = "PAUSADO"

st.write("---")

if st.session_state.estado == "PROCESANDO":
    total = len(st.session_state.lista_referencias)
    barra_progreso = st.progress(st.session_state.indice_actual / total)
    texto_progreso = st.empty()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        while st.session_state.indice_actual < total:
            idx = st.session_state.indice_actual
            ref = st.session_state.lista_referencias[idx].upper()
            texto_progreso.text(f"Extrayendo peso de: {ref} ({idx + 1} de {total})...")
            barra_progreso.progress((idx + 1) / total)
            peso_lb = None

            try:
                # Motor 1: URL directa CNH Case IH
                url_directa = f"https://www.mycnhstore.com/us/en/caseih/p/{ref}"
                page.goto(url_directa, timeout=25000)
                page.wait_for_timeout(1000)
                descartar_modales_cnh(page)

                if "/p/" in page.url:
                    for _ in range(2):
                        page.mouse.wheel(0, 500)
                        page.wait_for_timeout(300)
                    texto_cnh = page.evaluate("document.body.innerText")
                    peso_lb = extraer_peso_universal(texto_cnh)

                # Motor 2: Buscador interno
                if peso_lb is None:
                    url_search = f"https://www.mycnhstore.com/us/en/caseih/search?text={ref}"
                    page.goto(url_search, timeout=25000)
                    page.wait_for_timeout(1200)
                    descartar_modales_cnh(page)

                    enlaces = page.locator('a[href*="/p/"]')
                    if enlaces.count() > 0:
                        enlaces.first.click(force=True, timeout=3000)
                        page.wait_for_timeout(1500)
                        descartar_modales_cnh(page)
                        texto_cnh = page.evaluate("document.body.innerText")
                        peso_lb = extraer_peso_universal(texto_cnh)

                # Motor 3: Respaldo en red
                if peso_lb is None:
                    texto_progreso.text(f"Buscando respaldo global para: {ref}...")
                    url_google = f"https://www.google.com/search?q=Case+IH+part+{ref}+weight+kg+lbs"
                    page.goto(url_google, timeout=18000)
                    page.wait_for_timeout(800)
                    texto_web = page.evaluate("document.body.innerText")
                    peso_lb = extraer_peso_universal(texto_web)

            except Exception:
                pass

            # Protocolo fantasma si no existe peso registrado
            es_estimado = False
            if peso_lb is None or peso_lb <= 0:
                peso_lb = 0.05
                es_estimado = True

            st.session_state.resultados.append({
                "Referencia": ref,
                "peso_lb": peso_lb,
                "estimado": es_estimado
            })
            st.session_state.indice_actual += 1

        browser.close()

    st.session_state.estado = "FINALIZADO"
    st.rerun()

# Resultados
if st.session_state.estado in ["PAUSADO", "FINALIZADO"] and st.session_state.resultados:
    if st.session_state.estado == "PAUSADO":
        st.warning(f"⏸️ Pausado en la referencia {st.session_state.indice_actual}.")
    else:
        st.success("✅ Extracción terminada.")

    filas = []
    for item in st.session_state.resultados:
        ref = item["Referencia"]
        lb = item["peso_lb"]
        est = item["estimado"]
        kg = lb / 2.20462262

        filas.append({
            "Referencia": ref,
            "Libras (Principal)": f"{lb:.3f}".replace(".", ","),
            "Kilos": f"{kg:.3f}".replace(".", ","),
            "Estado": "Estimado (0,05 lb)" if est else "Exacto"
        })

    df = pd.DataFrame(filas)

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        st.write("**Columna Principal (Libras):**")
        st.code("\n".join(df["Libras (Principal)"].tolist()), language="text")

    with c2:
        st.write("**Columna Secundaria (Kilos):**")
        st.code("\n".join(df["Kilos"].tolist()), language="text")

    with c3:
        st.write("**Tabla General:**")
        st.dataframe(df, use_container_width=True)
