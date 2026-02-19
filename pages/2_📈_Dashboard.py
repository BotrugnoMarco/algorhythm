"""
2_📈_Dashboard.py – Analisi della libreria
"""
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Dashboard", page_icon="📈", layout="wide")

if "sp" not in st.session_state:
    st.warning("⚠️ Non sei autenticato. Torna alla Home page per fare il login.")
    st.stop()

if "tracks" not in st.session_state:
    st.warning("⚠️ Nessuna traccia caricata. Torna alla Home per scaricarle.")
    st.stop()

st.title("📈 Dashboard Analitica")

tracks = st.session_state["tracks"]
year_buckets = st.session_state.get("year_buckets", {})
genre_buckets = st.session_state.get("genre_buckets", {})
classifications = st.session_state.get("classifications", {})

# ── HELPERS UI ──
def _stat_card(label: str, value) -> str:
    return (
        f'<div style="background: linear-gradient(135deg, #1DB954 0%, #191414 100%); '
        f'border-radius: 12px; padding: 1.2rem; color: white; text-align: center;">'
        f'<h2 style="margin:0; font-size: 2.2rem;">{value}</h2>'
        f'<p style="margin:0; opacity: 0.85; font-size: 0.95rem;">{label}</p>'
        f'</div>'
    )

# ── KPI cards ──
df = pd.DataFrame(tracks)
unique_artists = df["artist"].nunique()
unique_albums = df["album"].nunique()
if not df.empty and "release_year" in df.columns:
    valid_years = df[df['release_year'] > 0]
    year_range = f"{valid_years['release_year'].min()} – {valid_years['release_year'].max()}" if not valid_years.empty else "N/A"
else:
    year_range = "N/A"

col1, col2, col3, col4 = st.columns(4)
col1.markdown(_stat_card("Brani totali", len(tracks)), unsafe_allow_html=True)
col2.markdown(_stat_card("Artisti unici", unique_artists), unsafe_allow_html=True)
col3.markdown(_stat_card("Album unici", unique_albums), unsafe_allow_html=True)
col4.markdown(_stat_card("Arco temporale", year_range), unsafe_allow_html=True)

st.markdown("---")

# ── Layout a 2 colonne per i grafici principali ──
left, right = st.columns(2)

# ── PIE CHART – Generi / Mood ──
with left:
    st.subheader("🎨 Generi & Mood (AI)")
    if genre_buckets:
        genre_data = {k: len(v) for k, v in genre_buckets.items() if v}
        if genre_data:
            fig_pie = px.pie(
                names=list(genre_data.keys()),
                values=list(genre_data.values()),
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Bold,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("I generi non sono ancora stati calcolati. Vai alla pagina 'Crea Playlist' per avviare l'AI.")

# ── BAR CHART – Decadi ──
with right:
    st.subheader("📅 Brani per Decade")
    if year_buckets:
        decade_data = {k: len(v) for k, v in year_buckets.items() if v}
        if decade_data:
            fig_bar = px.bar(
                x=list(decade_data.keys()),
                y=list(decade_data.values()),
                color=list(decade_data.keys()),
                color_discrete_sequence=["#1DB954", "#1ed760", "#b3b3b3"],
                text=list(decade_data.values()),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Nessun dato sulle decadi disponibile.")

st.markdown("---")

# ── CHART – Anno di Uscita e Artisti ──
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("📆 Timeline Rilasci")
    if not df.empty:
        year_counts = df[df["release_year"] > 0]["release_year"].value_counts().sort_index()
        fig_years = px.bar(x=year_counts.index, y=year_counts.values, color_discrete_sequence=["#1DB954"])
        st.plotly_chart(fig_years, use_container_width=True)

with col_b:
    st.subheader("🎤 Top 15 Artisti")
    if not df.empty:
        top_artists = df["artist"].value_counts().head(15).sort_values()
        fig_artists = px.bar(x=top_artists.values, y=top_artists.index, orientation="h", color_discrete_sequence=["#1DB954"])
        st.plotly_chart(fig_artists, use_container_width=True)
