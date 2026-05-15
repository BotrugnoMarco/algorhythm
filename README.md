# 🎵 AlgoRhythm

A Streamlit web app that connects to your Spotify account, classifies all your Liked Songs using AI (Google Gemini), and automatically creates organized playlists — grouped by genre/mood and by decade.

---

## Features

- **Spotify OAuth2 login** — secure web-based authentication flow
- **Liked Songs sync** — fetches your entire Saved Tracks library with local JSON caching
- **AI classification** — Google Gemini analyzes each track and assigns genre/mood categories (batched, resumable)
- **Decade classification** — mathematical bucketing by release year (2020s, 2010s, 2000s, Pre-2000)
- **Auto playlist creation** — generates and populates playlists directly on your Spotify account
- **Analytics dashboard** — interactive charts (genre breakdown, decade distribution, top artists, release timeline)
- **Customizable categories** — edit genre/mood playlists from the Settings page
- **Resume support** — classification cache survives restarts; picks up where it left off

## Tech Stack

| Layer | Technology |
|---|---|
| UI | [Streamlit](https://streamlit.io/) |
| Spotify API | [Spotipy](https://spotipy.readthedocs.io/) |
| AI Classifier | [Google Gemini Flash](https://ai.google.dev/) |
| Charts | [Plotly](https://plotly.com/python/) |
| Data | [Pandas](https://pandas.pydata.org/) |

## Project Structure

```
algorhythm/
├── app.py                  # Entry-point: auth, home page
├── spotify_client.py       # OAuth2 + Spotify API calls
├── gemini_classifier.py    # Gemini batch classifier with cache/resume
├── classifier.py           # Year-bucket logic + settings manager
├── sidebar.py              # Shared sidebar component
├── pages/
│   ├── 1_🎵_My_Tracks.py   # Browse & search your library
│   ├── 2_📈_Dashboard.py   # Analytics & charts
│   ├── 3_🛠️_Create_Playlists.py  # AI classification + playlist creation
│   └── 4_⚙️_Settings.py   # Configure genre categories
├── .env.example            # Environment variable template
├── requirements.txt
└── DEPLOY.md               # Deployment guide (Streamlit Cloud, Render, VPS)
```

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/BotrugnoMarco/algorhythm.git
cd algorhythm
pip install -r requirements.txt
```

### 2. Set up credentials

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Where to get it |
|---|---|
| `SPOTIPY_CLIENT_ID` | [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
| `SPOTIPY_CLIENT_SECRET` | Spotify Developer Dashboard |
| `SPOTIPY_REDIRECT_URI` | Set `http://127.0.0.1:8888/callback` in the dashboard |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `APP_ACCESS_KEY` | Optional — any string to password-protect the app |

### 3. Run

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501), log in with Spotify, and you're set.

## Deploy

See [DEPLOY.md](DEPLOY.md) for step-by-step instructions on deploying to **Streamlit Community Cloud** (free), **Render**, or a **VPS**.

## How It Works

1. After Spotify login, the app downloads your full Liked Songs library and caches it locally.
2. On the **Create Playlists** page, Gemini Flash receives batches of `"Artist - Title"` strings and returns JSON with genre/mood categories per track.
3. Classification results are cached incrementally — if the API quota is hit, progress is saved and the next run resumes automatically.
4. Once classified, the app calls the Spotify API to create and populate each playlist in your account.
