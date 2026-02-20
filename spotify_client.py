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
import requests 

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


def get_auth_manager(cache_path: str = ".spotify_cache") -> SpotifyOAuth:
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
        
        # --- CREAZIONE PLAYLIST MANUALE (REQUESTS) ---
        # Usiamo requests nudo e crudo come richiesto.
        token_info = sp.auth_manager.cache_handler.get_cached_token()
        if not token_info:
                raise Exception("Token mancante per creazione playlist manuale")
        
        access_token = token_info['access_token']
        
        # FIX: Usiamo l'endpoint /me/playlists invece di /users/{id}/playlists
        # Questo evita errori 403 se l'user_id non corrisponde esattamente a quello atteso dall'API
        endpoint = "https://api.spotify.com/v1/me/playlists"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # PROVIAMO A CREARE PRIVATA PER EVITARE PROBLEMI DI PERMESSI SULLE PUBBLICHE
        # Spesso le app in dev mode hanno restrizioni sulle playlist pubbliche o richiedono review.
        # Inoltre, riduce il rischio di errori 403 su account free o con restrizioni.
        payload = {
            "name": name,
            "description": description,
            "public": False # FIX: Impostiamo a FALSE per default (privata)
        }
        
        logger.info(f"REQUEST MANUALE: POST {endpoint} | Payload: {payload}")
        
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            res_json = response.json()
            logger.info(f"✅ Playlist creata manualmente! ID: {res_json['id']}")
            
            if existing_playlists_cache is not None:
                    existing_playlists_cache.append(res_json)
            return res_json['id']
        else:
            logger.error(f"❌ Errore Creazione Manuale: {response.status_code} - {response.text}")
            raise Exception(f"Errore creazione playlist: {response.status_code} - {response.text}")

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
    Usa REQUESTS manuali invece di spotipy per evitare problemi noti.
    """
    chunk_size = 100
    
    # Recupera token per chiamate manuali
    token_info = sp.auth_manager.cache_handler.get_cached_token()
    if not token_info:
         raise Exception("Token mancante per add_tracks_to_playlist")
    
    access_token = token_info['access_token']
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # -- 1. Svuota la playlist (PUT con lista vuota o inizia col primo chunk)
    # Strategia: 
    # - Se track_uris è vuoto -> Svuota tutto (PUT [])
    # - Se track_uris ha elementi -> Il primo chunk lo inseriamo con PUT (che sostituisce/svuota il resto)
    # - I successivi chunk con POST (append)
    
    if not track_uris:
        # Caso: Svuota playlist
        endpoint_replace = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        resp = requests.put(endpoint_replace, headers=headers, json={"uris": []})
        if resp.status_code not in [200, 201]:
             logger.error(f"Errore svuotamento playlist: {resp.status_code} {resp.text}")
        return

    # -- 2. Loop sui chunk
    
    endpoint = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    
    # PULIZIA ESPLICITA INIZIALE
    # Tentiamo di svuotare solo se necessario. Se fallisce con 403 (comune su nuove playlist vuote), ignoriamo.
    logger.info(f"Tentativo svuotamento playlist {playlist_id}...")
    try:
        # Usiamo PUT per svuotare. Alcuni utenti segnalano che PUT fallisce se la playlist è nuova.
        # Proviamo a non considerarlo errore fatale.
        resp_clear = requests.put(endpoint, headers=headers, json={"uris": []})
        if resp_clear.status_code not in [200, 201]:
            logger.warning(f"Svuotamento PUT completato con status {resp_clear.status_code}. Msg: {resp_clear.text}")
    except Exception as e:
        logger.warning(f"Eccezione durante svuotamento (ignorata): {e}")

    # AGGIUNTA TRAMITE POST (APPEND) PER TUTTI I CHUNK
    if not track_uris:
        logger.warning(f"Nessuna traccia da aggiungere alla playlist {playlist_id}")
        return

    for i in range(0, len(track_uris), chunk_size):
        chunk = track_uris[i : i + chunk_size]
        
        # Validazione URIs: devono iniziare con spotify:track:
        valid_chunk = [uri for uri in chunk if uri and uri.startswith("spotify:track:")]
        if len(valid_chunk) != len(chunk):
            logger.warning(f"Rilevati URI non validi nel chunk! Filtrati {len(chunk)-len(valid_chunk)} invalidi.")
        
        if not valid_chunk:
            logger.warning("Chunk vuoto dopo filtro validazione.")
            continue

        payload = {"uris": valid_chunk}
        
        logger.info(f"Adding tracks (POST/APPEND) to playlist {playlist_id} (chunk {i//chunk_size + 1}) - {len(valid_chunk)} tracks")
        
        try:
            resp = requests.post(endpoint, headers=headers, json=payload)
            
            if resp.status_code not in [200, 201]:
                logger.error(f"Errore aggiunta tracce playlist: {resp.status_code} - {resp.text}")
                raise Exception(f"Errore aggiunta tracce: {resp.status_code} - {resp.text}")
            else:
                logger.info(f"Chunk {i//chunk_size + 1} aggiunto con successo. Snapshot ID: {resp.json().get('snapshot_id')}")
        except Exception as e:
            logger.error(f"Eccezione critica durante POST tracce: {e}")
            raise e

