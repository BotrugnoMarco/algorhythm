"""
daily_sync.py
─────────────
Script automatico (da eseguire via CRON) che:
1. Recupera tutte le Liked Songs.
2. Identifica le NUOVE tracce rispetto all'esecuzione precedente.
3. Classifica le nuove tracce (Anno & Genere/Mood con Gemini).
4. Aggiunge le tracce alle playlist corrispondenti su Spotify.
5. Aggiorna il db locale delle tracce note.
"""

import os
import json
import logging
from datetime import datetime
import time

# Terze parti
import spotipy
from dotenv import load_dotenv

# Moduli locali
import spotify_client
import classifier
import gemini_classifier

# Configurazione Logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "daily_sync.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# File per tenere traccia dei brani già processati
KNOWN_TRACKS_FILE = "data/known_tracks.json"
os.makedirs("data", exist_ok=True)

def load_known_tracks() -> set[str]:
    """Carica gli ID delle tracce già note."""
    if not os.path.exists(KNOWN_TRACKS_FILE):
        return set()
    try:
        with open(KNOWN_TRACKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except Exception as e:
        logger.error(f"Errore caricamento known_tracks: {e}")
        return set()

def save_known_tracks(track_ids: set[str]):
    """Salva gli ID delle tracce note."""
    try:
        with open(KNOWN_TRACKS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(track_ids), f)
    except Exception as e:
        logger.error(f"Errore salvataggio known_tracks: {e}")

def main():
    load_dotenv()
    logger.info("Script Daily Sync avviato.")

    # 1. Autenticazione Headless (da cache)
    auth_manager = spotify_client.get_auth_manager()
    sp = spotify_client.get_spotify_client(auth_manager)
    
    if not sp:
        logger.error("Impossibile autenticarsi. Esegui prima l'app Streamlit per generare il token.")
        return

    user_id = sp.current_user()["id"]
    logger.info(f"Autenticato come: {user_id}")

    # 2. Carica tracce note
    known_ids = load_known_tracks()
    logger.info(f"Tracce già note nel db locale: {len(known_ids)}")

    # 3. Scarica TUTTE le Liked Songs (per trovare le nuove)
    logger.info("Scaricamento Liked Songs da Spotify...")
    try:
        all_tracks = spotify_client.fetch_all_liked_songs(sp)
    except Exception as e:
        logger.error(f"Errore durante il fetch delle canzoni: {e}")
        return


    # 4. Filtra le NUOVE tracce
    current_ids = {t["track_id"] for t in all_tracks}
    current_ids_list = list(current_ids)
    
    # Se è la PRIMA scansione in assoluto (nessuna traccia nota),
    # consideriamo tutte le tracce come "conosciute" per evitare
    # di processare l'intero storico con l'AI (costoso e lento).
    # L'utente potrà comunque usare l'app UI per fare il backfill massivo se vuole.
    if not known_ids:
        logger.warning("Prima esecuzione assoluta: salvo lo stato attuale senza processare lo storico.")
        save_known_tracks(current_ids)
        return

    new_tracks = [t for t in all_tracks if t["track_id"] not in known_ids]
    
    logger.info(f"Totale tracce su Spotify: {len(all_tracks)}")
    logger.info(f"Nuove tracce da processare: {len(new_tracks)}")

    if not new_tracks:
        logger.info("Nessuna nuova traccia. Aggiorno solo il db locale per sicurezza e termino.")
        # Salviamo comunque l'elenco corrente
        known_ids = current_ids
        save_known_tracks(known_ids)
        return

    # 5. Classificazione
    # Mappa: Nome Playlist -> Lista URI Tracce
    playlist_additions = {}

    # A) Classificazione per ANNO
    logger.info("Classificazione per Anno...")
    for track in new_tracks:
        year_playlist = classifier.classify_by_year(track)
        if year_playlist:
            if year_playlist not in playlist_additions:
                playlist_additions[year_playlist] = []
            playlist_additions[year_playlist].append(track["track_id"])

    # B) Classificazione AI (Genere/Mood)
    logger.info("Classificazione AI (Gemini)...")
    # Prepariamo input per Gemini: "Artist - Title"
    track_labels = [t["label"] for t in new_tracks]
    
    try:
        # Chiamata a Gemini (a batch)
        ai_results = gemini_classifier.classify_all_tracks(track_labels)
        
        # Mappa label -> track_id per recuperare l'originale
        label_to_uri = {t["label"]: t["track_id"] for t in new_tracks}
        
        for label, categories in ai_results.items():
            uri = label_to_uri.get(label)
            if not uri: continue
            
            for cat in categories:
                if cat not in playlist_additions:
                    playlist_additions[cat] = []
                playlist_additions[cat].append(uri)
                
    except Exception as e:
        logger.error(f"Errore classificazione AI: {e}")
        # Continuiamo con quello che abbiamo (anni)

    # 6. Aggiunta a Spotify
    logger.info("Aggiunta tracce alle playlist...")
    
    # Recuperiamo cache playlist utente una volta sola per efficienza
    user_playlists = spotify_client.get_all_user_playlists(sp)

    for playlist_name, track_uris in playlist_additions.items():
        if not track_uris: continue
        
        try:
            logger.info(f"Processing playlist '{playlist_name}' con {len(track_uris)} brani.")
            
            # Ottieni ID playlist (creala se non esiste)
            pl_id = spotify_client.get_or_create_playlist(
                sp=sp, 
                user_id=user_id, 
                name=playlist_name, 
                description="Auto-generated bucket by Algorhythm Daily Sync",
                existing_playlists_cache=user_playlists
            )
            
            if pl_id:
                spotify_client.append_tracks_to_playlist(sp, pl_id, track_uris)
                logger.info(f" -> Aggiunti {len(track_uris)} brani a '{playlist_name}'")
            else:
                logger.error(f" -> Impossibile ottenere ID per '{playlist_name}'")
                
        except Exception as e:
            logger.error(f"Errore aggiunta brani a {playlist_name}: {e}")

    # 7. Aggiorna DB locale (Salva lo stato corrente esatto)
    # Sovrascriviamo con current_ids così se un brano viene rimosso e riaggiunto, 
    # verrà ri-processato. Mantiene il db pulito.
    known_ids = current_ids 
    save_known_tracks(known_ids)
    logger.info("Sync completato con successo.")

if __name__ == "__main__":
    main()
