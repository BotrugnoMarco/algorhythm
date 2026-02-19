"""
1_🎵_My_Tracks.py – Visualizza le tue Liked Songs
"""
import streamlit as st
import pandas as pd
from spotify_client import fetch_all_liked_songs

# Se l'utente arriva qui direttamente senza passare da app.py, non ha la sessione.
# Streamlit pages funzionano condividendo session state, ma bisogna essere sicuri che 
# l'autenticazione sia avvenuta.

st.set_page_config(page_title="My Tracks", page_icon="🎵", layout="wide")

if "sp" not in st.session_state:
    st.warning("⚠️ Non sei autenticato. Torna alla Home page per fare il login.")
    st.stop()

st.title("🎵 Le tue Liked Songs")

# Recupera tracce dalla sessione
if "tracks" not in st.session_state:
    st.info("📥 Scaricamento tracce in corso...")
    # Tenta recupero se non presenti (fallback)
    # In teoria app.py dovrebbe averle caricate
    st.warning("Nessuna traccia caricata. Torna alla Home per scaricarle.")
else:
    tracks = st.session_state["tracks"]
    st.write(f"Hai **{len(tracks)}** brani salvati.")
    
    # Mostra DataFrame interattivo
    df = pd.DataFrame(tracks)
    
    # Filtro rapido
    search = st.text_input("🔍 Cerca brano o artista:", "")
    if search:
        df = df[
            df["track_name"].str.contains(search, case=False) | 
            df["artist"].str.contains(search, case=False)
        ]
    
    st.dataframe(
        df[["track_name", "artist", "album", "release_year", "added_at"]],
        use_container_width=True,
        height=600,
        hide_index=True
    )
