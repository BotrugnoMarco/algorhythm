"""
app.py  –  🎵 AlgoRhythm
─────────────────────────
Entry-point Streamlit: autenticazione, processing e dashboard.
Avvia con:  streamlit run app.py
"""

import os  # Necessario per leggere variabili d'ambiente
import json
import logging
import streamlit as st
import pandas as pd
from spotipy.exceptions import SpotifyException

# Configurazione Logging di base per vedere INFO su console/file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

import plotly.express as px
import plotly.graph_objects as go

from spotify_client import (
    get_auth_manager,
    get_spotify_client,
    fetch_all_liked_songs,
    get_or_create_playlist,
    add_tracks_to_playlist,
    get_all_user_playlists, # Nuovo
)
from classifier import (
    YEAR_PLAYLISTS,
    GENRE_PLAYLISTS,
    build_year_buckets,
    build_genre_buckets,
)
from gemini_classifier import classify_all_tracks

# ── Page config ────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AlgoRhythm",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0 0.5rem;
    }
    .stat-card {
        background: linear-gradient(135deg, #1DB954 0%, #191414 100%);
        border-radius: 12px;
        padding: 1.2rem;
        color: white;
        text-align: center;
    }
    .stat-card h2 { margin: 0; font-size: 2.2rem; }
    .stat-card p  { margin: 0; opacity: 0.85; font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
#  HELPER – Sezioni UI
# ══════════════════════════════════════════════════════════════════════

def _stat_card(label: str, value) -> str:
    return (
        f'<div class="stat-card">'
        f'<h2>{value}</h2>'
        f'<p>{label}</p>'
        f'</div>'
    )


def show_header():
    st.markdown('<div class="main-header">', unsafe_allow_html=True)
    st.markdown("# 🎵 AlgoRhythm")
    st.markdown(
        "##### Analizza le tue Liked Songs · Classifica con AI · Crea playlist automatiche"
    )
    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
#  FASE 1 – Autenticazione
# ══════════════════════════════════════════════════════════════════════

def authenticate():
    """Importante: gestisce il flusso OAuth2 Web-based compatibile con server remoti."""
    
    # 1. Recupera Auth Manager
    auth_manager = get_auth_manager()

    # 2. Controllo: siamo in fase di callback? (C'è un codice nell'URL?)
    # st.query_params sostituisce st.experimental_get_query_params
    query_params = st.query_params
    if "code" in query_params:
        try:
            # Scambia il codice per il token
            auth_manager.get_access_token(query_params["code"])
            # Pulisci l'URL per evitare riutilizzo del codice
            st.query_params.clear()
        except Exception as e:
            st.error(f"Errore durante il login: {e}")
            return

    # 3. Tentativo di istanziare il client (controlla token in cache/sessione)
    sp = get_spotify_client(auth_manager)

    if not sp:
        # User non autenticato → Mostra pulsante con Link
        auth_url = auth_manager.get_authorize_url()
        st.info("🔐 **Connettiti a Spotify** per iniziare.")
        
        # Streamlit non permette di aprire tab automaticamente senza js hack, 
        # ma st.link_button è perfetto per questo
        st.link_button("🔗  Vai al Login Spotify", auth_url, type="primary", use_container_width=True)
        st.stop()  # Ferma l'esecuzione finché non torna autenticato

    # 4. Auth OK → Salva in sessione
    if "sp" not in st.session_state:
        st.session_state["sp"] = sp
        st.session_state["user"] = sp.current_user()


# ══════════════════════════════════════════════════════════════════════
#  FASE 2 – Fetch liked songs
# ══════════════════════════════════════════════════════════════════════

CACHE_DIR = "user_data"
os.makedirs(CACHE_DIR, exist_ok=True)

def fetch_tracks():
    """Scarica le liked songs (con progress bar) e le salva in session. Usa caching su disco."""
    if "tracks" in st.session_state:
        return

    sp = st.session_state["sp"]
    user = st.session_state.get("user", {})
    user_id = user.get("id", "unknown_user")
    
    cache_file = os.path.join(CACHE_DIR, f"tracks_{user_id}.json")
    
    # 1. TENTATIVO CARICAMENTO DA CACHE
    # Se il file esiste, evitiamo di chiamare Spotify (risparmio API)
    if os.path.exists(cache_file):
        # Aggiungiamo un toggle nella sidebar o un bottone per forzare il refresh
        # Per ora usiamo logica semplice: se c'è, usalo, a meno che l'utente non chieda refresh
        if not st.session_state.get("force_refresh_tracks", False):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_tracks = json.load(f)
                st.session_state["tracks"] = cached_tracks
                st.info(f"📂 **Cache trovata!** Caricati {len(cached_tracks)} brani dal disco locale (nessuna chiamata API).")
                
                if st.button("🔄 Forza riscaricamento da Spotify", key="btn_force_refresh"):
                    st.session_state["force_refresh_tracks"] = True
                    st.rerun()
                return
            except Exception as e:
                st.warning(f"Cache corrotta, procedo al download: {e}")

    # 2. DOWNLOAD DA SPOTIFY (Se non c'è cache o force refresh richiesto)
    st.subheader("📥 Scaricamento Liked Songs da Spotify")
    st.session_state["force_refresh_tracks"] = False # Reset flag

    progress_bar = st.progress(0, text="Recupero le tue tracce salvate…")
    status_text = st.empty()

    def _progress(done, total):
        pct = done / total if total else 0
        progress_bar.progress(pct, text=f"Scaricate {done}/{total} tracce…")
        status_text.caption(f"Pagina {done // 50} completata")

    try:
        tracks = fetch_all_liked_songs(sp, progress_callback=_progress)
        
        # Salvataggio su disco per il futuro
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(tracks, f)
            
        progress_bar.progress(1.0, text=f"✅ {len(tracks)} tracce scaricate!")
        status_text.empty()
        st.session_state["tracks"] = tracks
        st.success(f"**{len(tracks)}** tracce scaricate e salvate in cache!")
        
    except Exception as e:
        status_text.empty()
        st.error(f"Errore durante il download da Spotify: {e}")
        # Se abbiamo fallito ma c'è una cache vecchia, proviamola come fallback
        if os.path.exists(cache_file):
            st.warning("⚠️ Impossibile contattare Spotify (Rate Limit?), carico l'ultima versione salvata.")
            with open(cache_file, "r", encoding="utf-8") as f:
                 st.session_state["tracks"] = json.load(f)
            return
        else:
            st.error("🛑 Impossibile proseguire senza tracce. Riprova più tardi.")
            st.stop()




# ══════════════════════════════════════════════════════════════════════
#  FASE 3 – Logic Hub: Scelta Modalità & Classificazione AI
# ══════════════════════════════════════════════════════════════════════

def classify_tracks():
    """Logic Hub: Mostra scelta (Decadi vs AI) e gestisce l'interfaccia AI."""
    
    tracks = st.session_state["tracks"]
    
    # Calcolo sempre i bucket per anni (è istantaneo e serve comunque)
    if "year_buckets" not in st.session_state:
        st.session_state["year_buckets"] = build_year_buckets(tracks)
    
    # Se l'utente non ha ancora attivato la modalità AI, mostriamo il menu di scelta
    if not st.session_state.get("ai_mode_active", False):
        st.markdown("## 🎛️ Scegli la tua strada")
        st.write("Come vuoi organizzare la tua libreria oggi?")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("📅 **Modalità Classica (Decadi)**")
            st.caption("Crea playlist basate sull'anno di uscita (es. 90s, 00s, 2024).")
            # Mostra preview
            year_buckets = st.session_state["year_buckets"]
            st.write(f"Verranno create **{len(year_buckets)}** playlist temporali.")
            
            if st.button("🚀 Crea Playlist per Decadi", use_container_width=True):
                 create_playlists(mode="decades")
                 st.rerun()

        with col2:
            st.info("🤖 **Modalità AI (Generi & Mood)**")
            st.caption("Usa Gemini per analizzare il mood di ogni brano (Indie, Club, Sad...).")
            st.write(f"Richiede analisi di **{len(tracks)}** brani.")
            
            if st.button("✨ Vai alla Classificazione AI", use_container_width=True):
                st.session_state["ai_mode_active"] = True
                st.rerun()
                
    else:
        # ── SEZIONE AI ATTIVA ──
        # Mostra pulsante per tornare indietro
        if st.button("⬅️ Torna alla scelta iniziale"):
            st.session_state["ai_mode_active"] = False
            st.rerun()
            
        _show_ai_interface(tracks)


def _show_ai_interface(tracks):
    """Logica interna per la UI di classificazione AI."""
    st.subheader("🤖 Classificazione AI con Gemini")
    
    # Bottoni di controllo
    start_btn = st.empty()
    stop_btn = st.empty()
    
    classifications = {}
    
    # Stato di esecuzione
    if "is_running" not in st.session_state:
        st.session_state["is_running"] = False
    
    # Bottone AVVIA
    if not st.session_state["is_running"]:
        if start_btn.button("▶️ Avvia Classificazione AI", key="start_ai"):
            st.session_state["is_running"] = True
            st.rerun()

    else:
        # Bottone STOP (solo se sta girando)
        if stop_btn.button("🛑 Interrompi esecuzione", key="stop_ai"):
            st.session_state["is_running"] = False
            st.warning("Esecuzione interrotta dall'utente.")
            # Non facciamo rerun immediato per permettere di salvare i risultati parziali
    
    # Esecuzione Loop
    if st.session_state["is_running"]:
        ai_status = st.empty()
        ai_progress = st.progress(0, text="Avvio classificazione...")
        results_container = st.container() # Container per log live scorrevole
        
        classifier_generator = classify_all_tracks(tracks)
        
        try:
            for batch_num, total_batches, batch_result in classifier_generator:
                # Aggiornamento UI
                pct = batch_num / total_batches if total_batches else 0
                ai_progress.progress(pct, text=f"Batch {batch_num}/{total_batches} completato...")
                
                # Log a video dei brani classificati
                with results_container:
                    msg = ""
                    for track, cats in batch_result.items():
                         msg += f"🎵 **{track}** → `{' '.join(cats)}`\n\n"
                    st.info(msg) 
                
                classifications = st.session_state.get("classifications", {})
                classifications.update(batch_result)
                st.session_state["classifications"] = classifications
                
        except Exception as e:
            st.error(f"Errore durante classificazione AI: {e}")
            st.session_state["is_running"] = False
            return
        
        # Se il loop è finito senza errori
        if st.session_state["is_running"]:
             st.session_state["is_running"] = False
             st.success("Analisi completata!")
             st.rerun()

    # Se abbiamo risultati (parziali o totali), costruiamo i bucket
    if "classifications" in st.session_state and st.session_state["classifications"]:
        classifications = st.session_state["classifications"]
        genre_buckets = build_genre_buckets(tracks, classifications)
        st.session_state["genre_buckets"] = genre_buckets
        
        st.info(f"Classificati {len(classifications)} brani su {len(tracks)}.")
        
        # Se abbiamo almeno qualche classificazione, permettiamo di creare playlist
        if classifications and not st.session_state["is_running"]:
             if st.button("🚀 Crea Playlist Generi (AI) + Decadi", type="primary"):
                 create_playlists(mode="all") # Crea tutto insieme
                 st.rerun()



# ══════════════════════════════════════════════════════════════════════
#  FASE 4 – Creazione playlist su Spotify
# ══════════════════════════════════════════════════════════════════════

def create_playlists(mode="all"):
    """
    Crea le playlist e aggiunge le tracce su Spotify.
    mode: "all", "decades", "genres"
    """
    # Rimuoviamo il check bloccante, gestiamo la ricreazione
    # if "playlists_created" in st.session_state: return

    sp = st.session_state["sp"]
    user_id = st.session_state["user"]["id"]
    year_buckets = st.session_state.get("year_buckets", {})
    genre_buckets = st.session_state.get("genre_buckets", {})

    all_buckets = {}
    
    # Seleziona cosa creare in base alla modalità
    if mode == "all" or mode == "decades":
        all_buckets.update(year_buckets)
    
    if mode == "all" or mode == "genres":
        all_buckets.update(genre_buckets)
        
    if not all_buckets:
        st.warning("Nessuna categoria selezionata o disponibile per la creazione!")
        return

    total = len(all_buckets)

    st.subheader(f"🚀 Creazione Playlist su Spotify ({mode.upper()})")
    pl_progress = st.progress(0, text="Inizio creazione…")

    # Recuperiamo info sulle playlist già create in questa sessione
    created_info = st.session_state.get("created_info", [])
    
    # Configurazione manuale dell'utente (mappatura NOME -> ID)
    pl_config = st.session_state.get("playlist_config", {})
    
    auth_manager = get_auth_manager()

    try:
        for idx, (name, bucket) in enumerate(all_buckets.items(), 1):
            if not bucket:
                continue

            pl_progress.progress(idx / total, text=f"Processing: {name} ({len(bucket)} brani)…")

            # ID manuale se esiste mappatura per questa categoria
            mapped_id = pl_config.get(name)

            playlist_id = get_or_create_playlist(
                sp, user_id, name,
                description=f"Creata da AlgoRhythm 🎵 – {len(bucket)} brani",
                known_id=mapped_id
            )
            uris = [t["track_id"] for t in bucket]
            add_tracks_to_playlist(sp, playlist_id, uris)

            # Aggiungi alla lista solo se non c'è già (per evitare duplicati in report)
            if not any(x["Playlist"] == name for x in created_info):
                created_info.append({"Playlist": name, "Brani": len(bucket)})
    
    except SpotifyException as e:
        if e.http_status == 403:
            st.error("🚨 ERRORE DI PERMESSI: Spotify ha rifiutato l'operazione (403 Forbidden).")
            st.error("Sembra che manchino i permessi per creare/modificare playlist. Prova a rifare il login.")
            if st.button("Logout e Riprova"):
                # Pulisce sessione e cache
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
        else:
            st.error(f"Errore Spotify Generico: {e}")
            st.warning("⚠️ Probabilmente i permessi dell'app sono cambiati o il token è scaduto/invalido per questa operazione.")
            st.info("💡 Soluzione: Esegui il Logout dalla barra laterale (pulsante 'Logout / Reset Cache') e ri-effettua il Login.")
            if st.button("🔄 Force Logout Now", key="force_logout_error"):
                if os.path.exists(auth_manager.cache_path):
                     os.remove(auth_manager.cache_path)
                
                # Rimuovi anche cache tracce per sicurezza
                track_cache_path = f"user_data/tracks_{user_id}.json"
                if os.path.exists(track_cache_path):
                     os.remove(track_cache_path)

                st.session_state.clear()
                st.rerun()
            st.stop()


    pl_progress.progress(1.0, text="✅ Operazione completata!")
    
    st.session_state["playlists_created"] = True
    st.session_state["created_info"] = created_info

    st.success("Playlist aggiornate con successo! 🎧")


# ══════════════════════════════════════════════════════════════════════
#  FASE 5 – Dashboard analitica
# ══════════════════════════════════════════════════════════════════════

def show_dashboard():
    """Mostra grafici e statistiche sulla libreria."""
    tracks = st.session_state["tracks"]
    year_buckets = st.session_state.get("year_buckets", {})
    genre_buckets = st.session_state.get("genre_buckets", {})
    classifications = st.session_state.get("classifications", {})

    st.markdown("---")
    st.markdown("## 📈 Dashboard – La tua libreria in numeri")

    # ── KPI cards ──
    df = pd.DataFrame(tracks)
    unique_artists = df["artist"].nunique()
    unique_albums = df["album"].nunique()
    year_range = f"{df['release_year'][df['release_year'] > 0].min()} – {df['release_year'].max()}"

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(_stat_card("Brani totali", len(tracks)), unsafe_allow_html=True)
    col2.markdown(_stat_card("Artisti unici", unique_artists), unsafe_allow_html=True)
    col3.markdown(_stat_card("Album unici", unique_albums), unsafe_allow_html=True)
    col4.markdown(_stat_card("Arco temporale", year_range), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Layout a 2 colonne per i grafici principali ──
    left, right = st.columns(2)

    # ── PIE CHART – Generi / Mood ──
    with left:
        st.markdown("### 🎨 Distribuzione Generi / Mood")
        genre_data = {
            name: len(bucket)
            for name, bucket in genre_buckets.items()
            if bucket
        }
        if genre_data:
            fig_pie = px.pie(
                names=list(genre_data.keys()),
                values=list(genre_data.values()),
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig_pie.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>%{value} brani (%{percent})<extra></extra>",
            )
            fig_pie.update_layout(
                showlegend=False,
                margin=dict(t=20, b=20, l=20, r=20),
                height=420,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # ── BAR CHART – Decadi ──
    with right:
        st.markdown("### 📅 Brani per Decade")
        decade_data = {
            name: len(bucket)
            for name, bucket in year_buckets.items()
            if bucket
        }
        if decade_data:
            fig_bar = px.bar(
                x=list(decade_data.keys()),
                y=list(decade_data.values()),
                color=list(decade_data.keys()),
                color_discrete_sequence=["#1DB954", "#1ed760", "#b3b3b3"],
                text=list(decade_data.values()),
            )
            fig_bar.update_traces(
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>%{y} brani<extra></extra>",
            )
            fig_bar.update_layout(
                xaxis_title="",
                yaxis_title="Numero di brani",
                showlegend=False,
                margin=dict(t=20, b=20),
                height=420,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # ── BAR CHART – Distribuzione per anno ──
    st.markdown("### 📆 Distribuzione per Anno di Uscita")
    year_counts = (
        df[df["release_year"] > 0]["release_year"]
        .value_counts()
        .sort_index()
    )
    if not year_counts.empty:
        fig_years = px.bar(
            x=year_counts.index.astype(str),
            y=year_counts.values,
            color_discrete_sequence=["#1DB954"],
        )
        fig_years.update_layout(
            xaxis_title="Anno",
            yaxis_title="Brani",
            margin=dict(t=20, b=20),
            height=350,
            xaxis=dict(dtick=5),
        )
        fig_years.update_traces(
            hovertemplate="<b>%{x}</b><br>%{y} brani<extra></extra>"
        )
        st.plotly_chart(fig_years, use_container_width=True)

    # ── HORIZONTAL BAR – Top 15 Artisti ──
    left2, right2 = st.columns(2)

    with left2:
        st.markdown("### 🎤 Top 15 Artisti")
        top_artists = df["artist"].value_counts().head(15).sort_values()
        fig_artists = px.bar(
            x=top_artists.values,
            y=top_artists.index,
            orientation="h",
            color_discrete_sequence=["#1DB954"],
            text=top_artists.values,
        )
        fig_artists.update_traces(textposition="outside")
        fig_artists.update_layout(
            xaxis_title="Brani",
            yaxis_title="",
            margin=dict(t=20, b=20, l=10),
            height=450,
        )
        st.plotly_chart(fig_artists, use_container_width=True)

    # ── TABELLA – Riepilogo playlist ──
    with right2:
        st.markdown("### 📋 Riepilogo Playlist Create")
        if "created_info" in st.session_state:
            info_df = pd.DataFrame(st.session_state["created_info"])
            info_df = info_df.sort_values("Brani", ascending=False).reset_index(drop=True)
            info_df.index += 1
            st.dataframe(
                info_df,
                use_container_width=True,
                height=450,
            )

    # ── Multi-genere stats ──
    multi_genre_count = sum(
        1 for cats in classifications.values() if len(cats) > 1
    )
    if multi_genre_count > 0:
        st.markdown("### 🔀 Brani Multi-Genere")
        st.info(
            f"**{multi_genre_count}** brani su {len(tracks)} "
            f"({multi_genre_count * 100 // len(tracks)}%) sono stati "
            f"classificati in 2 categorie."
        )

    st.markdown("---")
    st.caption("Fatto con ❤️ da AlgoRhythm · Powered by Spotify API & Google Gemini")


def check_access_password():
    """Mostra una schermata di login che chiede una KEY di accesso."""
    
    # Se la chiave è già validata in sessione, continua
    if st.session_state.get("access_granted", False):
        return

    # Leggi la chiave segreta (definita in .env o configurazione server)
    # Se non è impostata, lasciamo l'accesso libero (opzionale)
    ACCESS_KEY = os.getenv("APP_ACCESS_KEY")
    if not ACCESS_KEY:
        st.session_state["access_granted"] = True
        return

    st.markdown('<div class="main-header"><h2>🔒 Accesso Riservato</h2></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Inserisci la Chiave di Accesso:", type="password")
        if st.button("Entra", type="primary", use_container_width=True):
            if password == ACCESS_KEY:
                st.session_state["access_granted"] = True
                st.rerun()
            else:
                st.error("Chiave errata! Riprova.")
    
    st.stop()  # Blocca l'esecuzione finché non si inserisce la pw corretta

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    # 1. Controllo Accesso (PRIMA di ogni altra cosa)
    check_access_password()

    show_header()

    # 2. Autenticazione (spostata PRIMA della sidebar per avere i dati utente subito)
    authenticate()

    # Sidebar con info utente
    with st.sidebar:
        st.markdown("## 🎵 AlgoRhythm")
        st.markdown("---")

        if "user" in st.session_state:
            user = st.session_state["user"]
            name = user.get("display_name", user["id"])
            st.markdown(f"👤 **{name}**")
            if user.get("images"):
                st.image(user["images"][0]["url"], width=100)
            st.caption(f"ID: {user['id']}")
            
            if st.button("🚪 Logout / Reset Cache", use_container_width=True):
                # Rimuovi file di cache token
                if os.path.exists(".spotify_cache"):
                    os.remove(".spotify_cache")
                # Rimuovi file di cache tracce
                track_cache_path = f"user_data/tracks_{user['id']}.json"
                if os.path.exists(track_cache_path):
                    os.remove(track_cache_path)
                
                # Pulisci session state
                st.session_state.clear()
                st.rerun()

            st.markdown("---")

        if "tracks" in st.session_state:
            st.metric("🎶 Liked Songs", len(st.session_state["tracks"]))

        if "playlists_created" in st.session_state:
            st.success("✅ Playlist create!")
        
        # Sezione Impostazioni
        st.markdown("---")
        with st.expander("⚙️ Impostazioni Playlist"):
            st.caption("Collega le categorie a playlist esistenti.")
            
            # Carica le playlist disponibili (una volta sola)
            if "sp" in st.session_state and "user_playlists" not in st.session_state:
                with st.spinner("Carico le tue playlist..."):
                    try:
                        st.session_state["user_playlists"] = get_all_user_playlists(st.session_state["sp"])
                    except:
                        st.warning("Impossibile caricare playlist.")

            # Carica CONFIGURAZIONE salvata da file
            mapping_file = "user_data/playlist_mapping.json"
            if "playlist_config" not in st.session_state and os.path.exists(mapping_file):
                try:
                    with open(mapping_file, "r") as f:
                        st.session_state["playlist_config"] = json.load(f)
                except:
                    pass # Se file corrotto o vuoto

            # Mappatura Decadi
            st.markdown("**Decadi**")
            pl_config = st.session_state.get("playlist_config", {})
            user_pls = st.session_state.get("user_playlists", [])
            
            # Helper per creare opzioni
            options = ["(Crea Nuova)"] + [f"{p['name']}" for p in user_pls]
            pl_map = {p['name']: p['id'] for p in user_pls} # Nome -> ID

            config_changed = False 

            for name in YEAR_PLAYLISTS.keys():
                # Trova indice corrente
                current_id = pl_config.get(name, None)
                selected_index = 0
                
                # Se abbiamo un ID salvato, cerchiamo il nome corrispondente tra le playlist utente
                if current_id:
                     found_name = next((k for k, v in pl_map.items() if v == current_id), None)
                     if found_name and found_name in options:
                         selected_index = options.index(found_name)

                choice = st.selectbox(f"{name}", options, index=selected_index, key=f"sel_{name}")
                
                new_id = None
                if choice != "(Crea Nuova)":
                    new_id = pl_map[choice]
                
                # Se è cambiato qualcosa rispetto al config attuale
                if new_id != current_id:
                    if new_id is None:
                        if name in pl_config: del pl_config[name]
                    else:
                        pl_config[name] = new_id
                    config_changed = True
            
            # Mappatura Generi (solo se necessario)
            st.markdown("**Generi AI**")
            for name in GENRE_PLAYLISTS:
                current_id = pl_config.get(name, None)
                selected_index = 0
                
                if current_id:
                     found_name = next((k for k, v in pl_map.items() if v == current_id), None)
                     if found_name and found_name in options:
                         selected_index = options.index(found_name)

                choice = st.selectbox(f"{name}", options, index=selected_index, key=f"sel_{name}")
                
                new_id = None
                if choice != "(Crea Nuova)":
                    new_id = pl_map[choice]

                if new_id != current_id:
                    if new_id is None:
                        if name in pl_config: del pl_config[name]
                    else:
                        pl_config[name] = new_id
                    config_changed = True

            # SALVATAGGIO SU DISCO se cambiato
            if config_changed:
                st.session_state["playlist_config"] = pl_config
                # Assicuriamoci che la cartella user_data esista (dovrebbe già esistere)
                os.makedirs("user_data", exist_ok=True)
                with open(mapping_file, "w") as f:
                    json.dump(pl_config, f, indent=4)
                # Piccola notifica toast (opzionale) o rerun per aggiornare stato?
                # st.toast("Mappatura salvata!") 


        st.markdown("---")
        st.caption("v1.1 · Streamlit + Spotipy + Gemini")

    # Pipeline principale
    # authenticate()  <-- Spostato sopra
    fetch_tracks()

    # Se le playlist sono già state create, mostra la dashboard
    if "playlists_created" in st.session_state:
        show_dashboard()
    else:
        # Altrimenti mostra l'interfaccia di classificazione interattiva
        # Sarà classify_tracks a mostrare il bottone "Crea Playlist" quando pronto
        st.markdown("---")
        classify_tracks()

if __name__ == "__main__":
    main()
