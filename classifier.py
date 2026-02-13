"""
classifier.py
──────────────
Logica matematica per la classificazione per decadi
e orchestratore che unisce regole temporali + output AI.
"""

from datetime import datetime

# ── Playlist per DECADI (logica matematica) ────────────────────────────

YEAR_PLAYLISTS: dict[str, tuple[int, int]] = {
    "📅 2020 - Oggi":          (2020, datetime.now().year),
    "🗓️ 2010 - 2019":         (2010, 2019),
    "📼 Pre-2010 Classics":   (0,    2009),
}

# ── Playlist per GENERE / MOOD (gestite da Gemini) ─────────────────────

GENRE_PLAYLISTS: list[str] = [
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
]


def classify_by_year(track: dict) -> str | None:
    """
    Assegna una traccia alla playlist temporale corretta
    in base al suo anno di release.

    Ritorna il nome della playlist o None se l'anno non è valido.
    """
    year = track.get("release_year", 0)
    if year <= 0:
        return None

    for playlist_name, (start, end) in YEAR_PLAYLISTS.items():
        if start <= year <= end:
            return playlist_name
    return None


def build_year_buckets(tracks: list[dict]) -> dict[str, list[dict]]:
    """
    Raggruppa tutte le tracce nelle tre playlist temporali.

    Ritorna
    -------
    dict  { nome_playlist: [tracce ...] }
    """
    buckets: dict[str, list[dict]] = {name: [] for name in YEAR_PLAYLISTS}

    for t in tracks:
        pl = classify_by_year(t)
        if pl:
            buckets[pl].append(t)

    return buckets


def build_genre_buckets(tracks: list[dict],
                        classifications: dict[str, list[str]]) -> dict[str, list[dict]]:
    """
    Raggruppa le tracce nei bucket di genere/mood usando
    la mappa restituita da Gemini.

    Ogni traccia può apparire in 1 o 2 playlist di genere.

    Parametri
    ---------
    tracks : list[dict]
        Lista completa delle tracce.
    classifications : dict[str, list[str]]
        Mappa  { "Artist - Title": ["cat1", "cat2"] }  prodotta da Gemini.

    Ritorna
    -------
    dict  { nome_playlist: [tracce ...] }
    """
    buckets: dict[str, list[dict]] = {name: [] for name in GENRE_PLAYLISTS}

    for t in tracks:
        label = t["label"]
        genres = classifications.get(label, [])
        for genre in genres:
            if genre in buckets:
                buckets[genre].append(t)

    return buckets
