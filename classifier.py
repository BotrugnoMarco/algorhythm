"""
classifier.py
──────────────
Logica matematica per la classificazione per decadi
e orchestratore che unisce regole temporali + output AI.
Gestisce anche il caricamento/salvataggio delle impostazioni (categorie).
"""

import json
import os
from datetime import datetime

SETTINGS_DIR = "user_data"
if not os.path.exists(SETTINGS_DIR):
    os.makedirs(SETTINGS_DIR)
    
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


# ── DEFAULTS ───────────────────────────────────────────────────────────

DEFAULT_YEAR_PLAYLISTS = {
    "📅 2020 - Oggi":          (2020, datetime.now().year),
    "🗓️ 2010 - 2019":         (2010, 2019),
    "💿 2000 - 2009":          (2000, 2009),
    "📼 Pre-2000 Classics":   (0,    1999),
}

DEFAULT_GENRE_PLAYLISTS = [
    "🤪 Meme, Sigle & Trash",
    "🎸 Indie ma non è un gioco",
    "🇮🇹 Pop & Cantautorato ITA",
    "🌍 Pop & Radio Hits",
    "🎸 Guitar Anthems",
    "🏙️ Concrete Jungle",
    "🪩 Club Life",
    "💔 Deep & Emotional",
    "⚡ High Voltage",
    "🍃 Chill State of Mind",
    "⚠️ To Review",
]


# ── SETTINGS MANAGEMENT ────────────────────────────────────────────────

def load_settings():
    """Carica le impostazioni da file o usa i default."""
    genres = DEFAULT_GENRE_PLAYLISTS.copy()
    years = DEFAULT_YEAR_PLAYLISTS.copy()

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Se nel file ci sono chiavi, usale
            if "GENRE_PLAYLISTS" in data:
                genres = data["GENRE_PLAYLISTS"]
            
            # I tuple in JSON diventano liste, li riconvertiamo in tuple
            if "YEAR_PLAYLISTS" in data:
                raw_years = data["YEAR_PLAYLISTS"]
                years = {k: tuple(v) for k, v in raw_years.items()}
                
        except Exception as e:
            print(f"Errore caricamento settings: {e}")
            # Fallback ai default se il file è corrotto

    return genres, years

def save_settings_to_file(genres, years):
    """Salva le impostazioni su file."""
    data = {"GENRE_PLAYLISTS": genres, "YEAR_PLAYLISTS": years}
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Caricamento iniziale (Global variables accessible by other modules)
# Questa chiamata avverrà all'importazione del modulo.
GENRE_PLAYLISTS, YEAR_PLAYLISTS = load_settings()


# ── LOGIC ──────────────────────────────────────────────────────────────

def classify_by_year(track: dict) -> str | None:
    """
    Assegna una traccia alla playlist temporale corretta
    in base al suo anno di release.

    Ritorna il nome della playlist o None se l'anno non è valido.
    """
    year = track.get("release_year", 0)
    if year <= 0:
        return None

    # Iteriamo su YEAR_PLAYLISTS (che potrebbe essere cambiato tramite reload)
    # Se serve dinamismo perfetto, potremmo richiamare load_settings() qui,
    # ma per performance e semplicità, ci affidiamo alle globali (streamlet ricarica lo script).
    
    for playlist_name, (start, end) in YEAR_PLAYLISTS.items():
        if start <= year <= end:
            return playlist_name
            
    return None
