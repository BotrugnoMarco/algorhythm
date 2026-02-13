# ☁️ Guida al Deploy su Server (Streamlit Cloud / Render / VPS)

L'applicazione è stata aggiornata per supportare il deploy su server remoti grazie al flusso di autenticazione "web-based" (gestione query params).

Ecco i passaggi per metterla online in pochi minuti.

---

## Opzione 1: Streamlit Community Cloud (Consigliata, Gratuita)

È l'opzione più semplice e veloce.

### 1. Prepara il repo GitHub

Crea un repository GitHub (pubblico o privato) e carica tutto il codice:

```bash
git init
git add .
git commit -m "Initial commit"
# git remote add origin <tuo-repo-url>
# git push -u origin master
```

### 2. Configura Streamlit Cloud

1. Vai su [share.streamlit.io](https://share.streamlit.io/) e fai login con GitHub.
2. Clicca su **New App**.
3. Seleziona il repository, il branch (`main` o `master`) e il file principale (`app.py`).
4. **IMPORTANTE:** Prima di fare deploy, clicca su **Advanced Settings...** (o "Secrets").
5. Incolla il contenuto del tuo `.env` nel formato TOML accettato da Streamlit Secrets:

```toml
SPOTIPY_CLIENT_ID = "tuo_client_id"
SPOTIPY_CLIENT_SECRET = "tuo_client_secret"
SPOTIPY_REDIRECT_URI = "https://<tua-app>.streamlit.app"
GEMINI_API_KEY = "tua_gemini_key"
```

_Nota: L'URI di redirect lo scoprirai DOPO aver scelto il sottodominio, ma di solito è `https://<nome-repo>.streamlit.app`._

### 3. Aggiorna Dashboard Spotify Developer

1. Vai su [developer.spotify.com](https://developer.spotify.com/dashboard).
2. Apri la tua App → **Settings**.
3. Aggiungi il nuovo Redirect URI sotto "Redirect URIs":
   - `https://<tua-app>.streamlit.app`
     _(Non deve esserci `/callback` alla fine se non lo gestisci esplicitamente nel codice. La modifica attuale gestisce i parametri sulla root)._

---

## Opzione 2: Render.com / Railway

Se vuoi un controllo maggiore o Docker.

1. Crea un file `Procfile` (per Render/Heroku) nella root:

   ```txt
   web: streamlit run app.py --server.port $PORT --server.address 0.0.0.0
   ```

   _(Oppure usa il comando start fornito nella config web)_.

2. Crea un nuovo **Web Service** collegato al tuo repo GitHub.
3. Imposta le variabili d'ambiente nella dashboard del provider:
   - `SPOTIPY_CLIENT_ID`
   - `SPOTIPY_CLIENT_SECRET`
   - `SPOTIPY_REDIRECT_URI` → L'URL che ti assegna Render (es. `https://algorhythm.onrender.com`)
   - `GEMINI_API_KEY`
4. Aggiorna sempre il Redirect URI su Spotify Developer Dashboard.

---

## Opzione 3: VPS Linux (Ubuntu + Nginx)

Se hai un server VPS (EC2, DigitalOcean, Hetzner).

1. Clona il repo sul server.
2. Installa Python e venv:
   ```bash
   sudo apt update && sudo apt install python3-venv nginx
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Avvia l'app in background (es. con `nohup` o `systemd`):
   ```bash
   nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &
   ```
4. Configura **Nginx** come reverse proxy (opzionale ma consigliato per HTTPS/SSL) oppure apri la porta 8501 nel firewall.
5. Ricordati di impostare le variabili d'ambiente (nel file `.env` sul server o via `export`).
6. Aggiorna il Redirect URI su Spotify Dashboard (es. `http://<IL-TUO-IP>:8501`).

---

## ⚠️ Nota Fondamentale per il Deploy

L'app usa la cache `.spotify_cache` per salvare il token.

- Sui server cloud (Streamlit Cloud, Heroku, Render), il file system è **effimero**. Significa che se il server si riavvia, perdi il login.
- Per uso personale non è grave (basta rifare login).
- Per salvare la sessione in modo permanente dovresti implementare un `CacheHandler` personalizzato (es. su Database o S3), ma per questa versione v1.0 il file system locale è sufficiente.
