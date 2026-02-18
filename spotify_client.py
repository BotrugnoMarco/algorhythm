"""
spotify_client.py
─────────────────
Gestisce l'autenticazione OAuth2 con Spotify e il recupero
di TUTTE le Liked Songs dell'utente (con paginazione).
"""

import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

# ── Configurazione OAuth2 ──────────────────────────────────────────────
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-email"

SPOTIFY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI",
                                  "http://127.0.0.1:8888/callback")


def get_auth_manager(cache_path: str = ".spotify_cache") -> SpotifyOAuth:
    """
    Crea e restituisce il gestore dell'autenticazione OAuth2.
    Configura open_browser=False per compatibilità server.
    """
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SCOPES,
        cache_path=cache_path,
        show_dialog=True,
        open_browser=False,  # IMPORTANTE per server/deploy
    )

def get_spotify_client(auth_manager: SpotifyOAuth = None) -> spotipy.Spotify | None:
    """
    Restituisce un client Spotify se c'è un token valido in cache.
    Altrimenti restituisce None.
    """
    if auth_manager is None:
        auth_manager = get_auth_manager()

    # Controlla se abbiamo un token valido salvato
    if auth_manager.validate_token(auth_manager.cache_handler.get_cached_token()):
        return spotipy.Spotify(auth_manager=auth_manager)
    
    return None


# ── Fetch di TUTTE le Liked Songs ──────────────────────────────────────

def fetch_all_liked_songs(sp: spotipy.Spotify,
                          progress_callback=None) -> list[dict]:
    """
    Scarica tutte le tracce salvate dall'utente gestendo la
    paginazione di Spotify (max 50 per richiesta).

    Parametri
    ---------
    sp : spotipy.Spotify
        Client autenticato.
    progress_callback : callable, opzionale
        Funzione chiamata con (tracce_scaricate, totale_stimato)
        ad ogni pagina, utile per aggiornare una progress bar.

    Ritorna
    -------
    list[dict]
        Lista di dizionari con le informazioni essenziali di ogni traccia:
        - track_id   : Spotify URI
        - name       : titolo
        - artist     : nome del primo artista
        - album      : nome dell'album
        - release_date : data di uscita (stringa YYYY o YYYY-MM-DD)
        - release_year : anno di uscita (int)
        - label      : "Artist - Title" (per l'invio a Gemini)
    """
    tracks: list[dict] = []
    offset = 0
    limit = 50
    total = None

    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)

        if total is None:
            total = results["total"]

        for item in results["items"]:
            t = item["track"]
            if t is None:
                continue

            release_date: str = t["album"].get("release_date", "")
            try:
                release_year = int(release_date[:4])
            except (ValueError, TypeError):
                release_year = 0

            artist_name = t["artists"][0]["name"] if t["artists"] else "Unknown"

            tracks.append({
                "track_id": t["uri"],
                "name": t["name"],
                "artist": artist_name,
                "artists_all": ", ".join(a["name"] for a in t["artists"]),
                "album": t["album"]["name"],
                "release_date": release_date,
                "release_year": release_year,
                "label": f"{artist_name} - {t['name']}",
            })

        offset += limit

        if progress_callback and total:
            progress_callback(min(offset, total), total)

        # Se non ci sono più pagine, esci
        if results["next"] is None:
            break

    return tracks


# ── Gestione Playlist ──────────────────────────────────────────────────

def get_all_user_playlists(sp: spotipy.Spotify) -> list[dict]:
    """
    Recupera TUTTE le playlist dell'utente corrente.
    Restituisce una lista di oggetti playlist (id, name, etc).
    """
    playlists = []
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        playlists.extend(page["items"])
        if page["next"] is None:
            break
        offset += 50
    return playlists


def get_or_create_playlist(sp: spotipy.Spotify,
                           user_id: str,
                           name: str,
                           description: str = "",
                           known_id: str = None) -> str:
    """
    Restituisce l'ID di una playlist.
    - Se known_id è fornito, restituisce direttamente quello (dopo verifica esistenza).
    - Altrimenti cerca per nome. Se non esiste, la crea.
    """
    
    # 1. Se abbiamo un ID mappato manualmente dall'utente, usiamo quello
    if known_id:
        try:
            # Verifica che esista e sia accessibile
            pl = sp.playlist(known_id)
            # Verifica permesso scrittura (provi a svuotare)
            sp.playlist_replace_items(known_id, [])
            return known_id
        except spotipy.SpotifyException as e:
            print(f"⚠️ Playlist mappata '{known_id}' non accessibile/scrivibile. Fallback su ricerca per nome.")
            # Se fallisce, procedi con la logica standard (ignora l'ID rotto)

    # 2. Cerca tra le playlist esistenti dell'utente (per nome)
    playlists = []
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        playlists.extend(page["items"])
        if page["next"] is None:
            break
        offset += 50

    for pl in playlists:
        if pl["name"] == name:
            # ── VALIDAZIONE PERMESSI (FIX PER ERRORE 403) ──
            # Se la playlist esiste ma è stata creata da una vecchia App, controlliamo
            # se possiamo SCRIVERE su di essa provando a svuotarla (replace_items con lista vuota).
            try:
                # Eseguiamo una scrittura "test" reale
                sp.playlist_replace_items(pl["id"], [])
                # Se passa, ripristiniamo anche la descrizione corretta
                sp.playlist_change_details(pl["id"], description=description)
                return pl["id"]
            except spotipy.SpotifyException as e:
                if e.http_status == 403:
                    print(f"⚠️  Playlist '{name}' ({pl['id']}) trovata ma NON scrivibile (403). Creazione nuova istanza.")
                    continue  # Ignora questa vecchia playlist e cercane un'altra o creane una nuova
                else:
                    # Se è un altro errore, lo solleviamo
                    raise e

    # Non trovata (o non scrivibile) → crea
    try:
        print(f"DEBUG: Tentativo creazione playlist per user_id='{user_id}' con nome='{name}'")
        new_pl = sp.user_playlist_create(
            user=user_id,
            name=name,
            public=False,
            description=description,
        )
        return new_pl["id"]
    except Exception as e:
        print(f"ERRORE CREAZIONE PLAYLIST: {e}")
        # Riprova facendo una fetch fresca dell'user id
        me = sp.me()
        real_id = me['id']
        print(f"DEBUG: Riprovo con user_id fresco da API: '{real_id}'")
        new_pl = sp.user_playlist_create(
            user=real_id,
            name=name,
            public=False,
            description=description,
        )
        return new_pl["id"]


def add_tracks_to_playlist(sp: spotipy.Spotify,
                           playlist_id: str,
                           track_uris: list[str]) -> None:
    """
    Sostituisce le tracce nella playlist (svuotandola prima),
    gestendo i blocchi da 100 tracce.
    """
    chunk_size = 100
    
    # Se non ci sono tracce, svuotiamo e basta
    if not track_uris:
        sp.playlist_replace_items(playlist_id, [])
        return

    # Prima svuota SEMPRE la playlist per sicurezza
    sp.playlist_replace_items(playlist_id, [])

    # Poi aggiungi a blocchi di 100
    for i in range(0, len(track_uris), chunk_size):
        chunk = track_uris[i : i + chunk_size]
        sp.playlist_add_items(playlist_id, chunk)
