import streamlit as st
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import logging

# Configurazione base
st.set_page_config(page_title="Debug Playlist 403", layout="wide")
load_dotenv()

# Logger locale per mostrare output a schermo
log_buffer = []

def log(msg):
    """Aggiunge un messaggio al log visuale"""
    print(msg)
    log_buffer.append(msg)

st.title("🕵️ Debugger Creazione Playlist")
st.warning("Usa questa pagina per testare SOLTANTO la creazione delle playlist e i permessi.")

# 1. Recupera credenziali da env
client_id = os.getenv("SPOTIPY_CLIENT_ID")
client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8501")

st.subheader("1. Configurazione")
col1, col2 = st.columns(2)
with col1:
    st.text_input("Client ID (Primi 4 char)", value=client_id[:4]+"..." if client_id else "MANCANTE", disabled=True)
    st.text_input("Redirect URI", value=redirect_uri, disabled=True)
    
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-email ugc-image-upload"
st.text_area("Scopes Richiesti", SCOPES, height=70, disabled=True)

# 2. Gestione Autenticazione
cache_path = ".spotify_cache_debug"

auth_manager = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope=SCOPES,
    cache_path=cache_path,
    show_dialog=True
)

if st.button("🗑️ Cancella Cache & Rilogga"):
    if os.path.exists(cache_path):
        os.remove(cache_path)
    # Rimuovi anche la cache v2 per sicurezza
    if os.path.exists(".spotify_cache_v2"):
        os.remove(".spotify_cache_v2")
    st.toast("Cache eliminata! Ricarica la pagina.")
    st.rerun()

# Login Flow
if "code" in st.query_params:
    try:
        code = st.query_params["code"]
        auth_manager.get_access_token(code, as_dict=False)
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Errore scambio token: {e}")

if not auth_manager.validate_token(auth_manager.cache_handler.get_cached_token()):
    auth_url = auth_manager.get_authorize_url()
    st.link_button("🔐 LOGIN CON SPOTIFY (Debug)", auth_url, type="primary")
    st.stop()

# Se siamo qui, siamo loggati
sp = spotipy.Spotify(auth_manager=auth_manager)
user = sp.current_user()

st.success(f"Loggato come: **{user['id']}** ({user.get('email', 'No Email')})")

# Mostra Token Scopes Reali
token_info = auth_manager.get_cached_token()
real_scopes = token_info.get("scope", "")
st.info(f"Scopes Attivi nel Token: `{real_scopes}`")

missing = []
for s in SCOPES.split():
    if s not in real_scopes:
        missing.append(s)

if missing:
    st.error(f"⚠️ MANCANO I SEGUENTI SCOPES: {missing}")
else:
    st.success("✅ Tutti gli scope necessari sono presenti.")

# 3. Test Creazione Playlist
st.divider()
st.subheader("2. Test Creazione")

pl_name = st.text_input("Nome Playlist da creare", value="DEBUG TEST 403")
pl_public = st.checkbox("Pubblica?", value=False)
pl_desc = "Playlist creata dal debugger"

if st.button("🚀 CREA PLAYLIST ORA"):
    with st.status("Esecuzione in corso...", expanded=True) as status:
        try:
            st.write(f"Tentativo creazione per user: `{user['id']}`")
            st.write(f"Parametri: Name='{pl_name}', Public={pl_public}")
            
            res = sp.user_playlist_create(
                user=user['id'],
                name=pl_name,
                public=pl_public,
                description=pl_desc
            )
            
            st.write("--- RISPOSTA API ---")
            st.json(res)
            
            status.update(label="✅ Successo!", state="complete")
            st.balloons()
            
        except spotipy.SpotifyException as e:
            status.update(label="❌ Errore Spotify", state="error")
            st.error(f"Errore HTTP: {e.http_status}")
            st.error(f"Codice: {e.code}")
            st.error(f"Messaggio: {e.msg}")
            st.error(f"Reason: {e.reason}")
            st.error(f"Headers: {e.headers}")
        except Exception as e:
            status.update(label="❌ Errore Generico", state="error")
            st.exception(e)
