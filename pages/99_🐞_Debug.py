import streamlit as st
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import logging
import uuid

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

st.write("---")
st.write("Debug: Verifica inizializzazione OAuth...")

# 2. Gestione Autenticazione
# NOTA: Usiamo la stessa cache dell'app principale (.spotify_cache_v2) così se il redirect
# finisce sulla Home (app.py) e lì avviene lo scambio del token, noi lo troviamo già pronto qui.
cache_path = ".spotify_cache_v2"

try:
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPES,
        cache_path=cache_path,
        show_dialog=True
    )
    st.write("Debug: OAuth inizializzato correttamente.")
except Exception as e:
    st.error(f"Errore inizializzazione OAuth: {e}")
    st.stop()

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

st.success("✅ DEBUGGER PRONTO: Scorri in basso per i test.")

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

# --- NUOVO DEBUG RAPIDO ---
import uuid

st.divider()
st.subheader("3. Test Rapido (Playlist Casuale)")
st.caption("Questo test crea immediatamente una playlist vuota con nome casuale per verificare i permessi di scrittura (scope: playlist-modify-*).")

if st.button("🎲 Crea Playlist Vuota Casuale (Test Immediato)", type="primary"):
    # Genera nome casuale
    random_suffix = str(uuid.uuid4())[:8]
    test_name = f"DEBUG_TEST_{random_suffix}"
    
    with st.status(f"Tentativo creazione playlist '{test_name}'...", expanded=True) as status:
        try:
            # 1. Recupera user corrente
            current_user = sp.current_user()
            user_id = current_user["id"]
            
            # Parametri usati
            token_info = auth_manager.get_cached_token()
            access_token = token_info['access_token']
            
            # Simuliamo la richiesta HTTP esatta che Spotipy sta per fare
            endpoint_url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "name": test_name,
                "public": False,
                "collaborative": False,
                "description": f"Playlist di test generata casualmente il {str(uuid.uuid4())}"
            }
            
            st.markdown("### 🔍 Dettagli Richiesta HTTP (Simulata)")
            st.code(f"POST {endpoint_url}", language="http")
            
            st.subheader("🔑 HEADER AUTHORIZATION (Reale)")
            st.write("Questo è l'header esatto che Spotipy invierà. Il token parte qui:")
            st.code(f"Authorization: Bearer {access_token}", language="http")
            
            with st.expander("Vedi Tutti gli Headers JSON", expanded=True):
                st.json(headers)
            
            st.markdown("**Body JSON:**")
            st.json(payload)
            
            # 2. Chiamata API
            st.write("⏳ Invio richiesta a Spotify API tramite Spotipy...")
            
            st.info(f"""
            **Chiamata sp.user_playlist_create() con:**
            - user = `{user_id}`
            - name = `{payload["name"]}`
            - public = `{payload["public"]}`
            - collaborative = `{payload["collaborative"]}`
            - description = `{payload["description"]}`
            
            👉 **Nota sul Token:** Il token NON viene passato come argomento qui sopra. 
            È gestito internamente dall'oggetto `sp` (istanziato con `auth_manager`) 
            che lo inserisce automaticamente nell'header `Authorization` della richiesta HTTP.
            """)

            # Usiamo kwargs espliciti per chiarezza, anche se spotipy gestisce tutto
            res = sp.user_playlist_create(
                user=user_id,
                name=payload["name"],
                public=payload["public"],
                collaborative=payload["collaborative"],
                description=payload["description"]
            )
            
            # 3. Risultato
            st.markdown("### 📩 Risposta API")
            st.json(res)
            
            playlist_url = res.get("external_urls", {}).get("spotify")
            if playlist_url:
                st.link_button("🔗 Apri Playlist Creata", playlist_url)
                
            status.update(label="✅ Successo! Permessi di scrittura confermati.", state="complete")
            st.balloons()
            
        except Exception as e:
            st.error(f"❌ Errore durante la creazione: {e}")
            status.update(label="❌ Fallito", state="error")
