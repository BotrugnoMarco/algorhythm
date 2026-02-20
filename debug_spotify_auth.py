# debug_spotify_auth.py
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

# COPIA ESATTA DEGLI SCOPE usati nell'app principale
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-email ugc-image-upload"

print("--- DEBUG SCRIPT SPOTIFY 403 ---")
print(f"Client ID: {os.getenv('SPOTIPY_CLIENT_ID')[:4]}********")
print(f"Redirect URI: {os.getenv('SPOTIPY_REDIRECT_URI')}")
print(f"Cache Path: .spotify_cache_v2 (come nell'app)")
print("-" * 30)

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    scope=SCOPES,
    cache_path=".spotify_cache_v2",  # IMPORTANTE: usa la stessa cache pulita creata prima
    open_browser=True # Nel terminale possiamo permetterci di aprire il browser se serve
))

try:
    user_info = sp.current_user()
    mio_id = user_info['id']
    email_user = user_info.get('email', 'N/A')
    
    print(f"✅ Login ok!")
    print(f"   TD: {mio_id}")
    print(f"   Email: {email_user}")
    
    # Controlla gli scope reali del token
    token_info = sp.auth_manager.get_cached_token()
    scopes_token = token_info.get('scope', 'N/A')
    print(f"   Scopes attivi: {scopes_token}")
    
    if "playlist-modify-private" not in scopes_token:
        print("\n⚠️ ATTENZIONE: Manca lo scope 'playlist-modify-private' nel token!")
    
    print("\n⏳ Provo a creare una playlist privata 'TEST 403'...")
    # Tenta creazione
    res = sp.user_playlist_create(user=mio_id, name="TEST 403", public=False)
    
    print(f"🎉 PLAYLIST CREATA CON SUCCESSO! ID: {res['id']}")
    print("Il problema 403 sembra RISOLTO a livello di API/Account.")
    
except spotipy.SpotifyException as e:
    print(f"\n❌ ERRORE SPOTIPY {e.http_status}: {e.msg}")
    if e.http_status == 403:
        print("\nRIPROVA DA DASHBOARD:")
        print(f"1. Vai su developer.spotify.com -> App -> User Management")
        print(f"2. Aggiungi ESPLICITAMENTE l'utente: '{mio_id}' (e anche '{email_user}')")
        print("3. Aspetta 1 minuto e riprova questo script.")
except Exception as e:
    print(f"\n❌ ERRORE GENERICO: {e}")
