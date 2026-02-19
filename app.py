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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# ── Import Shared Logic from local modules or libs ──
from spotify_client import (
    get_auth_manager,
    get_spotify_client,
    fetch_all_liked_songs,
    get_all_user_playlists, 
)

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
    """Gestisce il flusso OAuth2 Web-based compatibile con server remoti."""
    
    # 1. Recupera Auth Manager
    auth_manager = get_auth_manager()

    # 2. Controllo: siamo in fase di callback?
    query_params = st.query_params
    if "code" in query_params:
        try:
            # Scambia il codice per il token
            auth_manager.get_access_token(query_params["code"], as_dict=False)
            st.query_params.clear() # Pulisci URL
        except Exception as e:
            st.error(f"Errore durante il login: {e}")
            return

    # 3. Istanzia client
    sp = get_spotify_client(auth_manager)

    if not sp:
        auth_url = auth_manager.get_authorize_url()
        st.info("🔐 **Connettiti a Spotify** per iniziare.")
        st.link_button("🔗  Vai al Login Spotify", auth_url, type="primary", use_container_width=True)
        st.stop()  # Ferma finché non autenticato

    # 4. Auth OK → Salva in sessione
    if "sp" not in st.session_state:
        st.session_state["sp"] = sp
        st.session_state["user"] = sp.current_user()

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

    # Sidebar con info utente e navigazione
    with st.sidebar:
        st.markdown("## 🎵 AlgoRhythm")
        st.markdown("---")

        if "user" in st.session_state:
            user = st.session_state["user"]
            name = user.get("display_name", user["id"])
            st.markdown(f"👤 **{name}**")
            
            if st.button("🚪 Logout / Reset Cache", use_container_width=True):
                # Rimuovi file di cache token
                if os.path.exists(".spotify_cache"): os.remove(".spotify_cache")
                base_dir = os.path.dirname(os.path.abspath(__file__))
                abs_cache_path = os.path.join(base_dir, ".spotify_cache")
                if os.path.exists(abs_cache_path): os.remove(abs_cache_path)

                # Rimuovi file di cache tracce
                track_cache_path = f"user_data/tracks_{user['id']}.json"
                if os.path.exists(track_cache_path): os.remove(track_cache_path)
                
                st.session_state.clear()
                st.rerun()

            st.markdown("---")
            st.info("👈 Usa il menu laterale per navigare tra le pagine!")

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
