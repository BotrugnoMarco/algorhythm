"""
app.py  –  🎵 AlgoRhythm
─────────────────────────
Entry-point Streamlit: autenticazione e home page.
Avvia con:  streamlit run app.py
"""

import os
import json
import logging
import streamlit as st
import pandas as pd
import spotipy
from spotipy.exceptions import SpotifyException

# Configurazione Logging
logging.basicConfig(
    level=logging.INFO, # Mettiamo INFO per non intasare, ma DEBUG per spotify_client impostato nel suo file
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ── Import Shared Logic from local modules or libs ──
from spotify_client import (
    get_auth_manager,
    get_spotify_client,
    fetch_all_liked_songs,
    get_all_user_playlists, 
)
from sidebar import render_sidebar  # Importa la funzione sidebar

st.set_page_config(
    page_title="AlgoRhythm",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════
#  FASE 1 – Autenticazione e Setup
# ══════════════════════════════════════════════════════════════════════

def check_access_password():
    """Mostra una schermata di login che chiede una KEY di accesso."""
    
    # Se ci sono parametri di callback OAuth (code), SALTIAMO il controllo password temporaneamente
    # Utilizziamo st.query_params se disponibile
    try:
        query_params = st.query_params
    except AttributeError:
        query_params = st.experimental_get_query_params()
        
    # Se c'è 'code' nell'URL, significa che stiamo tornando da Spotify
    if "code" in query_params:
        # IMPORTANTE: Segnamo l'accesso come garantito temporaneamente per permettere scambio token
        st.session_state["access_granted"] = True
        return

    # Se la chiave è in sessione, continua
    if st.session_state.get("access_granted", False):
        return

    # Leggi la chiave segreta (definita in .env o configurazione server)
    ACCESS_KEY = os.getenv("APP_ACCESS_KEY")
    if not ACCESS_KEY:
        st.session_state["access_granted"] = True
        return

    st.markdown('<div class="main-header"><h2>🔒 Accesso Riservato</h2></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Inserisci la Chiave di Accesso:", type="password")
        if st.button("Entra", type="primary", use_container_width=True):
            if password == ACCESS_KEY:
                st.session_state["access_granted"] = True
                st.rerun()
            else:
                st.error("Chiave errata! Riprova.")
    
    st.stop()  # Blocca l'esecuzione finché non si inserisce la pw corretta

def authenticate():
    """Gestisce il flusso OAuth2 Web-based robusto."""
    
    # 1. Recupera Auth Manager (che punta al file .spotify_cache)
    auth_manager = get_auth_manager()

    # 2. PRIMA di tutto: controlla se siamo GIÀ autenticati tramite cache su disco
    # Questo permette di condividere il login tra schede diverse o riavvii
    if auth_manager.validate_token(auth_manager.cache_handler.get_cached_token()):
        sp = get_spotify_client(auth_manager)
        if "sp" not in st.session_state:
            st.session_state["sp"] = sp
            st.session_state["user"] = sp.current_user()
        return  # Login già valido, usciamo subito

    # 3. Se non siamo autenticati, controlliamo se stiamo tornando da Spotify con un codice
    try:
        query_params = st.query_params
    except AttributeError:
        query_params = st.experimental_get_query_params()
        
    if "code" in query_params:
        code = query_params["code"]
        if isinstance(code, list):
            code = code[0]
            
        try:
            # Scambia il codice e SALVA SU DISCO il token
            # as_dict=False evita il DeprecationWarning, tanto il token viene salvato in cache
            auth_manager.get_access_token(code, as_dict=False)
            
            # Pulisci URL e ricarica
            st.query_params.clear()
            st.toast("Autenticazione riuscita!", icon="🎉")
            st.rerun()
            
        except Exception as e:
            st.error(f"Errore scambio token: {e}")
            st.stop()

    # 4. Caso finale: Non siamo autenticati e non abbiamo un codice. Mostriamo il link.
    auth_url = auth_manager.get_authorize_url()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("🔐 Per continuare, devi autorizzare l'app su Spotify.")
        # target="_self" cerca di forzare l'apertura nella stessa scheda, anche se i browser moderni decidono loro
        st.markdown(f'<a href="{auth_url}" target="_self" style="background-color:#1DB954;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;display:block;text-align:center;font-weight:bold;">🔗 ACCEDI CON SPOTIFY</a>', unsafe_allow_html=True)
    
    st.stop() # Ferma tutto qui finché non c'è login

CACHE_DIR = "user_data"
os.makedirs(CACHE_DIR, exist_ok=True)

def fetch_tracks():
    """Scarica le liked songs (con progress bar) e le salva in session. Usa caching."""
    if "tracks" in st.session_state:
        return

    sp = st.session_state["sp"]
    user = st.session_state.get("user", {})
    user_id = user.get("id", "unknown_user")
    
    cache_file = os.path.join(CACHE_DIR, f"tracks_{user_id}.json")
    
    # TENTATIVO CARICAMENTO DA CACHE
    if os.path.exists(cache_file):
        if not st.session_state.get("force_refresh_tracks", False):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                st.session_state["tracks"] = cached
                st.toast(f"Caricati {len(cached)} brani dalla cache.", icon="📂")
                return
            except Exception as e:
                st.warning(f"Cache corrotta: {e}")

    # DOWNLOAD DA SPOTIFY
    st.subheader("📥 Scaricamento Liked Songs da Spotify")
    st.session_state["force_refresh_tracks"] = False 

    progress_bar = st.progress(0, text="Recupero le tue tracce salvate…")

    def _progress(done, total):
        pct = done / total if total else 0
        progress_bar.progress(pct, text=f"Scaricate {done}/{total} tracce…")

    try:
        tracks = fetch_all_liked_songs(sp, progress_callback=_progress)
        
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(tracks, f)
            
        st.session_state["tracks"] = tracks
        st.success(f"**{len(tracks)}** tracce scaricate!")
        st.rerun() # Ricarica per pulire UI
        
    except Exception as e:
        st.error(f"Errore durante il download da Spotify: {e}")
        st.stop()


# ══════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════

def main():
    # 1. Controllo Accesso
    check_access_password()

    # 2. Autenticazione (Critica per l'accesso a tutte le pagine)
    authenticate()

    # Sidebar condivisa
    render_sidebar()

    # 4. Fetch Tracce (necessario per tutto il resto)
    fetch_tracks()

    # HOMEPAGE CONTENT
    st.title("🎵 AlgoRhythm")
    st.caption("v2.0 · Streamlit Multi-Page")
    st.markdown("---")
    
    st.markdown("""
    ### 👋 Benvenuto!
    Questa app ti permette di riorganizzare la tua libreria Spotify in modo intelligente.
    
    ### 📂 **Naviga tra le pagine:**
    
    * **[🎵 My Tracks](./My_Tracks)**: Esplora e cerca tra tutte le tue canzoni salvate.
    * **[📈 Dashboard](./Dashboard)**: Visualizza statistiche, grafici e curiosità sulla tua musica.
    * **[🛠️ Create Playlists](./Create_Playlists)**: Il cuore dell'app. Usa l'AI per classificare i brani e creare automaticamente nuove playlist su Spotify.
    """)
    
    # Quick Actions
    st.markdown("### ⚡ Stato Attuale")
    col1, col2 = st.columns(2)
    with col1:
        n_tracks = len(st.session_state.get("tracks", []))
        st.success(f"✅ Hai **{n_tracks}** brani caricati in memoria.")
    
    with col2:
        if st.session_state.get("playlists_created"):
            st.info("🎉 Hai già creato playlist in questa sessione!")
        else:
            st.info("Nessuna playlist creata in questa sessione.")

if __name__ == "__main__":
    main()
