"""
debug_spotify_auth.py
─────────────────────
Script diagnostico super-minimale per testare:
1. Autenticazione OAuth2
2. Scope effettivamente garantiti
3. Creazione playlist di test

Usa: .env
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

# Verifica variabili
print("\n🔍 VERIFICA ENV")
print(f"CLIENT_ID: {'✅ TROVATO' if os.getenv('SPOTIPY_CLIENT_ID') else '❌ MANCANTE'}")
print(f"CLIENT_SECRET: {'✅ TROVATO' if os.getenv('SPOTIPY_CLIENT_SECRET') else '❌ MANCANTE'}")
print(f"REDIRECT_URI: {os.getenv('SPOTIPY_REDIRECT_URI')}")

SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private"

def run_test():
    try:
        # Usa file di cache DIVERSO dall'app principale per non fare confusione
        cache_handler = spotipy.cache_handler.CacheFileHandler(cache_path=".debug_cache")
        
        sp_oauth = SpotifyOAuth(
            scope=SCOPES,
            cache_handler=cache_handler,
            show_dialog=True,  # FORZA il login dialog
            open_browser=False # IMPORTANTE su server
        )

        print("\n🔑 AUTENTICAZIONE START")
        
        # Se non c'è token valido, chiediamo il link
        token_info = sp_oauth.validate_token(cache_handler.get_cached_token())
        
        if not token_info:
            auth_url = sp_oauth.get_authorize_url()
            print(f"\n⚠️  TOKEN MANCANTE/SCADUTO. Apri questo link nel browser:\n\n{auth_url}\n")
            code = input("Incolla qui l'URL di redirect (o solo il codice 'code=...'): ").strip()
            
            # Estrai codice se incollato url intero
            if "code=" in code:
                code = code.split("code=")[1].split("&")[0]
            
            token_info = sp_oauth.get_access_token(code)
            print("\n✅ Token ottenuto!")

        sp = spotipy.Spotify(auth=token_info['access_token'])
        user = sp.current_user()
        print(f"\n👤 UTENTE: {user['id']} ({user['display_name']})")
        print(f"📧 EMAIL: {user.get('email', 'N/A')}")
        print(f"🛡️  SCOPE OTTENUTI: {token_info['scope']}")

        print("\n🛠️  TEST CREAZIONE PLAYLIST...")
        pl_name = f"Test Debug {os.urandom(2).hex()}"
        
        try:
            pl = sp.user_playlist_create(
                user=user['id'],
                name=pl_name,
                public=False,
                description="Creato da debug script"
            )
            print(f"✅ SUCCESSO! Playlist creata: {pl['name']} (ID: {pl['id']})")
            print("   (La elimino subito per pulizia...)")
            sp.current_user_unfollow_playlist(pl['id'])
            print("   (Eliminata/Unfollowed)")
            
        except spotipy.SpotifyException as e:
            print(f"\n❌ ERRORE CREAZIONE: {e}")
            print(f"   Status Code: {e.http_status}")
            print(f"   Msg: {e.msg}")
            
    except Exception as e:
        print(f"\n💥 ERRORE CRITICO: {e}")

if __name__ == "__main__":
    run_test()
