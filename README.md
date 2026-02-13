# 🎵 AlgoRhythm

Connetti Spotify, categorizza le tue Liked Songs con AI e logica matematica,
crea playlist automatiche e visualizza statistiche sulla tua libreria.

## Struttura del progetto

```
algorhythm/
├── requirements.txt          # Dipendenze Python
├── .env                      # Credenziali (NON committare)
├── app.py                    # Entry-point Streamlit (UI + Dashboard)
├── spotify_client.py         # Autenticazione OAuth2 + fetch liked songs
├── gemini_classifier.py      # Classificazione AI (Gemini) a batch
├── classifier.py             # Logica matematica (decadi) + orchestratore
└── README.md
```

## Quick Start

```bash
pip install -r requirements.txt
# Compilare il file .env con le proprie credenziali
streamlit run app.py
```

## Variabili d'ambiente (.env)

```
SPOTIPY_CLIENT_ID=...
SPOTIPY_CLIENT_SECRET=...
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
GEMINI_API_KEY=...
```
