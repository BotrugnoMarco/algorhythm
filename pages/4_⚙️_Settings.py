"""
4_⚙️_Settings.py – Gestione Impostazioni Playlist
"""
import streamlit as st
import json
import sys
import os

# Init path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sidebar import render_sidebar
import classifier

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

render_sidebar()

if "sp" not in st.session_state:
    st.warning("⚠️ Devi essere autenticato.")
    st.stop()

st.title("⚙️ Impostazioni Playlist")
st.markdown("Qui puoi personalizzare come l'AI classifica i tuoi brani e crea le playlist.")

# ── Carica impostazioni attuali ────────────────────────────────────────
current_genres, current_years = classifier.load_settings()

# ── SEZIONE 1: Generi e Mood ───────────────────────────────────────────
st.subheader("🎨 Categorie (Generi & Moods)")
st.info("Queste sono le categorie che Gemini userà per classificare i tuoi brani. Scrivi una categoria per riga.")

# Convert list to string for text_area
genres_str = "\n".join(current_genres)

new_genres_str = st.text_area(
    "Modifica Categorie:", 
    value=genres_str, 
    height=300,
    help="Aggiungi, rimuovi o rinomina le categorie. L'AI cercherà di seguire queste etichette."
)

# ── SEZIONE 2: Decadi (Avanzato) ───────────────────────────────────────
st.subheader("📅 Raggruppamento Temporale")
# Per ora mostriamo solo un JSON editor per flessibilità massima
# Convertiamo tuple in liste per compatibilità JSON editor di streamlit
years_for_editor = {k: list(v) for k, v in current_years.items()}

st.caption("Configura gli intervalli di anni per le playlist temporali. (Formato: [Inizio, Fine])")
new_years_raw = st.data_editor(
    years_for_editor, 
    use_container_width=True,
    num_rows="dynamic"
)


# ── SALVATAGGIO ────────────────────────────────────────────────────────

if st.button("💾 Salva Nuove Impostazioni", type="primary"):
    # 1. Processa Generi
    new_genres_list = [line.strip() for line in new_genres_str.split("\n") if line.strip()]
    
    # 2. Processa Anni
    # Riconvertiamo liste in tuple e validiamo
    new_years_clean = {}
    try:
        for name, interval in new_years_raw.items():
            if isinstance(interval, list) and len(interval) == 2:
                start, end = int(interval[0]), int(interval[1])
                new_years_clean[name] = (start, end)
            else:
                st.error(f"Formato anni non valido per '{name}'. Usa [YYYY, YYYY].")
                st.stop()
                
        # 3. Salva su file
        # Chiamata corretta alla funzione definita in classifier.py
        classifier.save_settings_to_file(new_genres_list, new_years_clean)
        
        st.success("Impostazioni salvate con successo! Le prossime classificazioni useranno queste regole.")
        st.balloons()
        
        # Ricarica pagina per confermare
        import time
        time.sleep(1.5)
        st.rerun()
        
    except ValueError as e:
        st.error(f"Errore nel formato dei dati: {e}")

# ── Reset ──────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("🔴 Zona Pericolo: Reset"):
    if st.button("Ripristina impostazioni di fabbrica"):
        if os.path.exists(classifier.SETTINGS_FILE):
            os.remove(classifier.SETTINGS_FILE)
        st.warning("Impostazioni resettate ai default originali.")
        st.rerun()
