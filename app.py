"""
app.py  –  🎵 AlgoRhythm
─────────────────────────
Entry-point Streamlit: autenticazione, processing e dashboard.
Avvia con:  streamlit run app.py
"""

import os  # Necessario per leggere variabili d'ambiente
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from spotify_client import (
    get_auth_manager,
    get_spotify_client,
    fetch_all_liked_songs,
    get_or_create_playlist,
    add_tracks_to_playlist,
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

def fetch_tracks():
    """Scarica le liked songs (con progress bar) e le salva in session."""
    if "tracks" in st.session_state:
        return

    sp = st.session_state["sp"]

    st.subheader("📥 Scaricamento Liked Songs")
    progress_bar = st.progress(0, text="Recupero le tue tracce salvate…")
    status_text = st.empty()

    def _progress(done, total):
        pct = done / total if total else 0
        progress_bar.progress(pct, text=f"Scaricate {done}/{total} tracce…")
        status_text.caption(f"Pagina {done // 50} completata")

    tracks = fetch_all_liked_songs(sp, progress_callback=_progress)

    progress_bar.progress(1.0, text=f"✅ {len(tracks)} tracce scaricate!")
    status_text.empty()
    st.session_state["tracks"] = tracks
    st.success(f"**{len(tracks)}** tracce trovate nella tua libreria!")


# ══════════════════════════════════════════════════════════════════════
#  FASE 3 – Classificazione
# ══════════════════════════════════════════════════════════════════════

def classify_tracks():
    """Classifica per decade (math) e genere (AI) e salva i bucket."""
    if "year_buckets" in st.session_state:
        return

    tracks = st.session_state["tracks"]

    # ── Classificazione per decade (istantanea) ──
    st.subheader("📊 Classificazione per Decade")
    year_buckets = build_year_buckets(tracks)
    for name, bucket in year_buckets.items():
        st.write(f"  {name}: **{len(bucket)}** brani")
    st.session_state["year_buckets"] = year_buckets

    # ── Classificazione AI ──
    st.subheader("🤖 Classificazione AI con Gemini")
    
    stop_btn = st.button("🛑 Stop Classificazione", key="stop_ai")
    
    ai_status = st.empty()
    ai_progress = st.progress(0, text="Avvio classificazione...")
    results_container = st.expander("Dettaglio Classificazione (Live)", expanded=True)
    
    classifications = {}
    
    # Bottoni di controllo
    start_btn = st.empty()
    stop_btn = st.empty()
    
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
        
        classifications = st.session_state.get("classifications", {})
        
        # Logica di "Resume": 
        # Se abbiamo già classificazioni, non dovremmo ricominciare da zero ma saltare i brani già fatti
        # Per semplicità in questa v1, se premi stop e riavvii, ricominciamo il processo, 
        # MA teniamo le classificazioni vecchie se non sono sovrascritte.
        # Sarebbe meglio filtrare i brani da inviare, ma richiederebbe modifiche a gemini_classifier.py
        # MODIFICA: Per ora lasciamo che riparta (utile x retry errori), 
        # ma l'utente vede il log live.
        
        classifier_generator = classify_all_tracks(tracks)
        
        try:
            for batch_num, total_batches, batch_result in classifier_generator:
                # Controlla se l'utente ha premuto Stop nel frattempo
                # Nota: Streamlit non aggiorna st.session_state["is_running"] dentro un loop bloccante 
                # a meno che non usiamo st.rerun(). 
                # Tuttavia, il bottone "Stop" sopra aggiorna lo stato al prossimo ciclo di script.
                # TRUCCO: Un loop heavy blocca l'interazione. Dobbiamo usare un approccio asincrono o
                # accettare che "Stop" funzioni solo al termine del batch corrente.
                # Per la UX, stop_btn.button causa un rerun immediato che imposta is_running=False
                # Quindi al prossimo rerun entriamo nell'else del blocco "is_running"
                pass 
                
                # Aggiornamento UI
                pct = batch_num / total_batches if total_batches else 0
                ai_progress.progress(pct, text=f"Batch {batch_num}/{total_batches} completato...")
                
                # Log a video dei brani classificati
                with results_container:
                    msg = ""
                    for track, cats in list(batch_result.items())[:3]: # Mostra primi 3 del batch
                         msg += f"🎵 **{track}** → `{' '.join(cats)}`\n\n"
                    st.info(msg) # Usa st.info per un box visibile che si aggiunge
                
                classifications.update(batch_result)
                
                # Salva stato parziale in sessione
                st.session_state["classifications"] = classifications
                
        except Exception as e:

            st.error(f"Errore: {e}")
            st.session_state["is_running"] = False
        
        if "classifications" in st.session_state and st.session_state["classifications"]:
            st.rerun()

    # Se abbiamo risultati (parziali o totali), costruiamo i bucket
    if "classifications" in st.session_state and st.session_state["classifications"]:
        classifications = st.session_state["classifications"]
        genre_buckets = build_genre_buckets(tracks, classifications)
        st.session_state["genre_buckets"] = genre_buckets
        
        st.info(f"Classificati {len(classifications)} brani su {len(tracks)}.")
        
        # Se abbiamo almeno qualche classificazione (anche parziale), permettiamo di creare playlist
        if classifications and not st.session_state["is_running"]:
             if st.button("🚀 Crea Playlist con risultati attuali", type="primary"):
                 create_playlists()
                 st.rerun()


# ══════════════════════════════════════════════════════════════════════
#  FASE 4 – Creazione playlist su Spotify
# ══════════════════════════════════════════════════════════════════════

def create_playlists():
    """Crea le playlist e aggiunge le tracce su Spotify."""
    if "playlists_created" in st.session_state:
        return

    sp = st.session_state["sp"]
    user_id = st.session_state["user"]["id"]
    year_buckets = st.session_state["year_buckets"]
    genre_buckets = st.session_state["genre_buckets"]

    all_buckets = {**year_buckets, **genre_buckets}
    total = len(all_buckets)

    st.subheader("🚀 Creazione Playlist su Spotify")
    pl_progress = st.progress(0, text="Creo le playlist…")

    created_info: list[dict] = []

    for idx, (name, bucket) in enumerate(all_buckets.items(), 1):
        if not bucket:
            pl_progress.progress(idx / total, text=f"Skip (vuota): {name}")
            continue

        pl_progress.progress(idx / total, text=f"Creo: {name} ({len(bucket)} brani)…")

        playlist_id = get_or_create_playlist(
            sp, user_id, name,
            description=f"Creata da AlgoRhythm 🎵 – {len(bucket)} brani"
        )
        uris = [t["track_id"] for t in bucket]
        add_tracks_to_playlist(sp, playlist_id, uris)

        created_info.append({"Playlist": name, "Brani": len(bucket)})

    pl_progress.progress(1.0, text="✅ Tutte le playlist sono pronte!")
    st.session_state["playlists_created"] = True
    st.session_state["created_info"] = created_info

    st.success("Playlist create con successo! Controlla il tuo Spotify 🎧")


# ══════════════════════════════════════════════════════════════════════
#  FASE 5 – Dashboard analitica
# ══════════════════════════════════════════════════════════════════════

def show_dashboard():
    """Mostra grafici e statistiche sulla libreria."""
    tracks = st.session_state["tracks"]
    year_buckets = st.session_state["year_buckets"]
    genre_buckets = st.session_state["genre_buckets"]
    classifications = st.session_state["classifications"]

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
            st.markdown("---")

        if "tracks" in st.session_state:
            st.metric("🎶 Liked Songs", len(st.session_state["tracks"]))

        if "playlists_created" in st.session_state:
            st.success("✅ Playlist create!")

        st.markdown("---")
        st.caption("v1.0 · Streamlit + Spotipy + Gemini")

    # Pipeline principale
    authenticate()
    fetch_tracks()

    # Pulsante per avviare la classificazione + creazione
    if "playlists_created" not in st.session_state:
        st.markdown("---")
        if st.button(
            "🚀  Classifica e Crea Playlist",
            type="primary",
            use_container_width=True,
        ):
            classify_tracks()
            create_playlists()
            st.rerun()
    else:
        show_dashboard()


if __name__ == "__main__":
    main()
