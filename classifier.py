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
    genres = list(DEFAULT_GENRE_PLAYLISTS)
    years = dict(DEFAULT_YEAR_PLAYLISTS)

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
    
    # Reload settings on the fly if needed, here we use globals
    # Assuming runtime reload updates GENRE_PLAYLISTS/YEAR_PLAYLISTS if desired.
    # But streamlit likely reloads module on change anyway.
    
    for playlist_name, (start, end) in YEAR_PLAYLISTS.items():
        if start <= year <= end:
            return playlist_name
            
    return None


def build_year_buckets(tracks: list[dict]) -> dict[str, list[dict]]:
    """
    Raggruppa le tracce per playlist annuale.
    Ritorna { "Nome Playlist": [track_dict, ...], ... }
    """
    # Inizializza buckets vuoti per le chiavi definite in YEAR_PLAYLISTS
    buckets = {name: [] for name in YEAR_PLAYLISTS.keys()}
    
    for t in tracks:
        p_name = classify_by_year(t)
        if p_name:
            if p_name not in buckets:
                 buckets[p_name] = []
            buckets[p_name].append(t)
            
    return buckets


def build_genre_buckets(tracks: list[dict], ai_results: dict[str, list[str]]) -> dict[str, list[dict]]:
    """
    Raggruppa le tracce per genere usando i risultati dell'AI.
    Ritorna { "Nome Genre Playlist": [track_dict, ...], ... }
    """
    # Inizializza buckets vuoti per le chiavi definite in GENRE_PLAYLISTS
    buckets = {name: [] for name in GENRE_PLAYLISTS}
    if "⚠️ To Review" not in buckets:
        buckets["⚠️ To Review"] = [] # Assicura che esista una fallback

    for t in tracks:
        # Recupera label usata per AI
        label = t.get("label", "")
        if not label:
            # Fallback se label mancante
            label = f"{t.get('artist', 'Unknown')} - {t.get('name', 'Unknown')}"
            
        categories = ai_results.get(label, [])
        
        # Se nessuna categoria trovata o lista vuota
        if not categories:
            buckets["⚠️ To Review"].append(t)
            continue
            
        for cat in categories:
            if cat not in buckets:
                # Se l'AI restituisce una categoria non prevista (possibile con temperature > 0)
                # O la scartiamo, o la creiamo al volo.
                # Per robustezza, creiamola al volo o mettiamo in "Altro"?
                # Creiamola al volo
                buckets[cat] = []
            
            # Evita duplicati (stesso oggetto track listato 2 volte)
            if t not in buckets[cat]:
                buckets[cat].append(t)
                
    return buckets
