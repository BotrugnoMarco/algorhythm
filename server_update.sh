#!/bin/bash

# Script per aggiornare l'applicazione su server Linux (VPS)
# Utilizzo: ./server_update.sh

# Interrompe lo script se un comando fallisce
set -e

APP_FILE="app.py"
LOG_FILE="app.log"
PORT=8501

echo "=========================================="
echo "   ☁️  AlgoRhythm - Server Update Tool"
echo "=========================================="

# 1. Aggiornamento Codice dal Repository
echo ""
echo "[1/4] 📥 Eseguio git pull..."
git pull origin main

# 2. Aggiornamento Dipendenze
echo ""
echo "[2/4] 🐍 Aggiorno dipendenze..."

if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠️  Venv non trovato. Creazione in corso..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Installa/Aggiorna librerie
pip install -r requirements.txt

# 3. Stop Vecchio Processo
echo ""
echo "[3/4] 🛑 Arresto vecchio processo..."

# Cerca il PID di streamlit che esegue app.py
# || true serve perché pgrep restituisce exit code 1 se non trova nulla,
# e con set -e questo farebbe terminare lo script.
PID=$(pgrep -f "streamlit run $APP_FILE" || true)

if [ -n "$PID" ]; then
    echo "   Processo trovato (PID: $PID). Terminazione..."
    kill $PID || true
    sleep 2
else
    echo "   Nessun processo attivo trovato da terminare."
fi

# 4. Start Nuovo Processo
echo ""
echo "[4/4] 🚀 Avvio AlgoRhythm..."

# Esegue in background con nohup usando il path assoluto dell'eseguibile nel venv
# Questo evita l'errore "command not found" se l'activate non persiste
nohup ./venv/bin/streamlit run $APP_FILE --server.port $PORT --server.address 0.0.0.0 > $LOG_FILE 2>&1 &

NEW_PID=$(pgrep -f "streamlit run $APP_FILE")
echo "   ✅ Avviato con successo! (PID: $NEW_PID)"
echo ""
echo "=========================================="
echo "📝 Per vedere i log in tempo reale usa:"
echo "   tail -f $LOG_FILE"
echo "=========================================="
