import streamlit as st
import os

def render_sidebar():
    """Renders the common sidebar for all pages."""
    with st.sidebar:
        st.markdown("## 🎵 AlgoRhythm")
        st.markdown("---")

        if "user" in st.session_state:
            user = st.session_state["user"]
            name = user.get("display_name", user["id"])
            st.markdown(f"👤 **{name}**")
            
            if st.button("🔄 Aggiorna Libreria", use_container_width=True):
                track_cache_path = f"user_data/tracks_{user['id']}.json"
                if os.path.exists(track_cache_path):
                    os.remove(track_cache_path)
                st.session_state.pop("tracks", None)
                st.session_state["force_refresh_tracks"] = True
                st.rerun()

            if st.button("🚪 Logout / Reset Cache", use_container_width=True):
                if os.path.exists(".spotify_cache"): os.remove(".spotify_cache")
                base_dir = os.path.dirname(os.path.abspath(__file__))
                abs_cache_path = os.path.join(base_dir, ".spotify_cache")
                if os.path.exists(abs_cache_path): os.remove(abs_cache_path)

                track_cache_path = f"user_data/tracks_{user['id']}.json"
                if os.path.exists(track_cache_path): os.remove(track_cache_path)

                st.session_state.clear()
                st.rerun()

            st.markdown("---")
        
        # Le pagine native di Streamlit appaiono automaticamente nella sidebar,
        # quindi non c'è bisogno di aggiungere link manuali se usiamo la struttura `pages/`.
        # Streamlit gestisce la navigazione.
        
        # Aggiungiamo solo info extra se necessario
        st.caption("v2.0 · Multi-Page")
