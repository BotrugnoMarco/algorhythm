"""
spotify_client.py
─────────────────
Gestisce l'autenticazione OAuth2 con Spotify e il recupero
di TUTTE le Liked Songs dell'utente (con paginazione).
"""

import os
import logging
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Configurazione logging locale
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

load_dotenv()

# ── Configurazione OAuth2 ──────────────────────────────────────────────
SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-email ugc-image-upload"

SPOTIFY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI",
                                  "http://localhost:8501")


def get_auth_manager(cache_path: str = ".spotify_cache_v2") -> SpotifyOAuth:
    """
    Crea e restituisce il gestore dell'autenticazione OAuth2.
    Configura open_browser=False per compatibilità server.
    """
    # DEBUG CREDENZIALI (Sicurezza: mostra solo i primi 4 caratteri)
    masked_id = SPOTIFY_CLIENT_ID[:4] + "..." if SPOTIFY_CLIENT_ID else "NONE"
    print(f"DEBUG AUTH: Client ID in uso: {masked_id}")

    # FORZIAMO la rimozione di cache errate se presenti
    if os.path.exists(cache_path):
        try:
              # Controllo preventivo, ma con il nuovo nome file dovremmo essere sicuri
            pass
        except:
            pass
            
    auth_manager = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SCOPES,
        cache_path=os.path.abspath(cache_path),
        show_dialog=True,     # FORZA LA RIAPERTURA DELLA FINESTRA DI LOGIN
        open_browser=False,
    )
    return auth_manager

def get_spotify_client(auth_manager: SpotifyOAuth = None) -> spotipy.Spotify | None:
    """
    Restituisce un client Spotify se c'è un token valido in cache.
    Gestisce automaticamente il refresh del token se scaduto.
    """
    if auth_manager is None:
        auth_manager = get_auth_manager()

    # Controlla se abbiamo un token (anche scaduto, il manager proverà a rinfrescarlo)
    token_info = auth_manager.cache_handler.get_cached_token()
    
    if not token_info:
        return None
        
    # validate_token rinfresca automaticamente se necessario e restituisce il nuovo token info
    # Se restituisce qualcosa, vuol dire che siamo a posto
    if auth_manager.validate_token(token_info):
        logger.info("Token valido (o rinfrescato correttamente). Inizializzo client con Auth Manager.")
        return spotipy.Spotify(auth_manager=auth_manager)
    
    logger.warning("Token non valido e impossibile da rinfrescare.")
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
                "track_name": t["name"],
                "name": t["name"], # Teniamo entrambi per compatibilità
                "artist": artist_name,
                "artists_all": ", ".join(a["name"] for a in t["artists"]),
                "album": t["album"]["name"],
                "release_date": release_date,
                "release_year": release_year,
                "added_at": item["added_at"], # Data di aggiunta ai preferiti
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
                           known_id: str = None,
                           existing_playlists_cache: list[dict] = None) -> str:
    """
    Restituisce l'ID di una playlist.
    - Se known_id è fornito e valido, usa quello.
    - Altrimenti cerca per nome nella lista (cache o fetch).
    - Se non esiste, la crea.
    """
    
    logger.info(f"START get_or_create_playlist: name='{name}'")
    
    # 1. Se abbiamo un ID mappato manualmente dall'utente, usiamo quello
    if known_id:
        try:
            # Verifica che esista e sia accessibile (leggera chiamata API, ma necessaria)
            sp.playlist(known_id, fields="id,owner,public")
            return known_id
        except Exception:
             logger.warning(f"Playlist nota {known_id} non valida. Ignorata.")

    # 2. Otteniamo la lista delle playlist (da cache passata o fetch se manca)
    if existing_playlists_cache is not None:
        playlists = existing_playlists_cache
    else:
        # FALLBACK PERICOLOSO: Se non passiamo la cache, scarica tutto (LENTO e RISCHIOSO PER RATE LIMIT)
        logger.warning("⚠️ Cache playlist non fornita a get_or_create_playlist! Scarico tutte le playlist...")
        playlists = get_all_user_playlists(sp)

    # 3. Cerca tra le playlist (in memoria)
    for pl in playlists:
        if pl["name"] == name:
            logger.info(f"Playlist trovata in cache: {pl['name']} ({pl['id']})")
            return pl["id"]

    # 4. Se non trovata, CREA
    try:
        current_user = sp.current_user()
        real_user_id = current_user["id"]
        
        # Tenta creazione
        # NOTA: Alcuni utenti riportano problemi se si passa user_id esplicito che non matcha esattamente quello interno
        # Spotipy user_playlist_create usa l'endpoint /users/{user}/playlists
        
        # PROVA DIRETTA SENZA ID UTENTE ESPLICITO (Usa l'endpoint /me/playlists se disponibile o hack)
        # Spotipy non ha un metodo .me_playlist_create(), ma possiamo usare .user_playlist_create con l'ID corrente.
        
        logger.info(f"Tentativo creazione playlist PUBBLICA per user: '{real_user_id}'")
        new_pl = sp.user_playlist_create(
            user=real_user_id,
            name=name,
            public=True, # FORZIAMO PUBBLICA SU RICHIESTA UTENTE
            description=description
        )
        logger.info(f"✅ Nuova playlist creata: {new_pl['name']} ({new_pl['id']})")
        
        # Aggiorna la cache locale se fornita
        if existing_playlists_cache is not None:
             existing_playlists_cache.append(new_pl)
             
        return new_pl["id"]

    except spotipy.SpotifyException as e:
        logger.error(f"❌ ERRORE SPOTIPY CREAZIONE PLAYLIST: {e}")
        raise e

    except Exception as e:
        logger.critical(f"❌ ERRORE CREAZIONE PLAYLIST FATALE: {e}", exc_info=True)
        # Diamo un messaggio più chiaro all'utente
        raise Exception(f"Impossibile creare la playlist. User: '{real_user_id}'. Error: {e}")


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
