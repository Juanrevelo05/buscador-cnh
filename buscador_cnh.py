import subprocess
import sys
import os
import re
import urllib.parse
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

# Control de estado de sesión
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
    st.markdown("Consulta multitienda en **Messicks, MyCNHStore y Red CNH** | Salida principal en **Libras** y secundaria en **Kilos**.")

st.divider()

def extraer_peso_universal(texto):
    """Extrae y normaliza el peso a Libras desde texto plano."""
    if not texto:
        return None
    
    # 1. Búsqueda explícita de peso en Libras (lb / lbs)
    patrones_lb = [
        r'(?:Weight|Lbs?|Package\s*Weight|Shipping\s*Weight)[\s\n:-]*([\d\.,]+)\s*(?:lbs?|pounds?)\b',
        r'([\d\.,]+)\s*(?:lbs?|pounds?)\b',
        r'(?:Weight|Peso)[\s\n:-]*([\d\.,]+)'
    ]
    for pat in patrones_lb:
        m = re.search(pat, texto, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
                if 0.01 <= val <= 2500.0:
                    return val
            except: pass

    # 2. Búsqueda en Kilos (kg / kilogramos)
    patrones_kg = [
        r'(?:Weight|Package\s*Weight|Shipping\s*Weight)[\s\n:-]*([\d\.,]+)\s*(?:kg|kilo|kilograms?)\b',
        r'([\d\.,]+)\s*(?:kg|kilo|kilograms?)\b'
    ]
    for pat in patrones_kg:
        m = re.search(pat, texto, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", "."))
                if 0.005 <= val <= 1200.0:
                    return val * 2.20462262
            except: pass

    # 3. Búsqueda en Onzas (oz)
    m_oz = re.search(r'([\d\.,]+)\s*(?:oz|ounces?)\b', texto, re.IGNORECASE)
    if m_oz:
        try:
            val = float(m_oz.group(1).replace(",", "."))
            return val / 16.0
        except: pass

    return None

def descartar_modales(page):
    """Descarta banners de cookies y modales que bloqueen la visibilidad."""
    selectores = [
        "button#onetrust-accept-btn-handler",
        "button:has-text('Accept All Cookies')",
        "button:has-text('Accept All')",
        "button:has-text('Select Later')",
        "button:has-text('Dismiss')",
        "button:has-text('Close')",
        "button[aria-label='Close']"
    ]
    for sel in selectores:
        try:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=350)
        except: pass

st.write("### 1. Pega tu lista de combate CNH:")
referencias_input = st.text_area("Referencias (una por línea):", height=150, placeholder="51572706\n92265164\n84576869")

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
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900}
        )
        page = context.new_page()

        while st.session_state.indice_actual < total:
            idx = st.session_state.indice_actual
            ref = st.session_state.lista_referencias[idx].upper()
            texto_progreso.text(f"Rastreando peso de CNH: {ref} ({idx + 1} de {total})...")
            barra_progreso.progress((idx + 1) / total)
            peso_lb = None

            # =================================================================
            # MOTOR 1: MESSICKS (Líder en catálogo Case IH / New Holland con peso en lbs)
            # =================================================================
            try:
                url_messicks = f"https://www.messicks.com/search?q={ref}"
                page.goto(url_messicks, timeout=20000)
                page.wait_for_timeout(1000)
                descartar_modales(page)
                
                # Si redirige directo o si hay que entrar a la ficha del producto
                link_prod = page.locator(f"a[href*='/part/'], a[href*='{ref.lower()}']")
                if link_prod.count() > 0 and "/part/" not in page.url:
                    try:
                        link_prod.first.click(force=True, timeout=2500)
                        page.wait_for_timeout(1000)
                    except: pass
                
                texto_messicks = page.evaluate("document.body.innerText")
                peso_lb = extraer_peso_universal(texto_messicks)
            except Exception:
                pass

            # =================================================================
            # MOTOR 2: MYCNHSTORE OFICIAL (Case IH / New Holland)
            # =================================================================
            if peso_lb is None:
                try:
                    url_cnh = f"https://www.mycnhstore.com/us/en/caseih/p/{ref}"
                    page.goto(url_cnh, timeout=22000)
                    page.wait_for_timeout(1200)
                    descartar_modales(page)
                    
                    if "/p/" not in page.url:
                        url_search = f"https://www.mycnhstore.com/us/en/caseih/search?text={ref}"
                        page.goto(url_search, timeout=20000)
                        page.wait_for_timeout(1000)
                        descartar_modales(page)
                        enlaces = page.locator('a[href*="/p/"]')
                        if enlaces.count() > 0:
                            enlaces.first.click(force=True, timeout=2500)
                            page.wait_for_timeout(1200)
                    
                    # Scroll forzado para despertar las especificaciones dinámicas
                    for scroll_pos in [400, 800, 1400]:
                        page.evaluate(f"window.scrollTo(0, {scroll_pos})")
                        page.wait_for_timeout(250)
                    
                    texto_cnh = page.evaluate("document.body.innerText")
                    peso_lb = extraer_peso_universal(texto_cnh)
                except Exception:
                    pass

            # =================================================================
            # MOTOR 3: COLEMAN EQUIPMENT (Distribuidor oficial CNH)
            # =================================================================
            if peso_lb is None:
                try:
                    url_coleman = f"https://www.colemanequip.com/case-parts/?search={ref}"
                    page.goto(url_coleman, timeout=18000)
                    page.wait_for_timeout(1000)
                    texto_col = page.evaluate("document.body.innerText")
                    peso_lb = extraer_peso_universal(texto_col)
                except Exception:
                    pass

            # =================================================================
            # MOTOR 4: RASTREO GLOBAL DIRIGIDO (Google Search en vivo)
            # =================================================================
            if peso_lb is None:
                try:
                    query = urllib.parse.quote(f"CNH {ref} weight lbs OR kg (Case IH OR New Holland)")
                    url_search_engine = f"https://www.google.com/search?q={query}"
                    page.goto(url_search_engine, timeout=18000)
                    page.wait_for_timeout(900)
                    try:
                        page.locator("button:has-text('Aceptar todo'), button:has-text('Accept all')").click(timeout=1000)
                    except: pass
                    
                    texto_web = page.evaluate("document.body.innerText")
                    peso_lb = extraer_peso_universal(texto_web)
                except Exception:
                    pass

            # Protocolo de fallback si ninguna fuente pública lo registra
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

# ----------------------------------------------------
# VISUALIZACIÓN DE RESULTADOS
# ----------------------------------------------------
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
            "Libras (Principal)": f"{lb:.2f}".replace(".", ","),
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
