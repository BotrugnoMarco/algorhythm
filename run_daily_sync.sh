#!/bin/bash

# Vai alla directory dello script
cd "$(dirname "$0")"

# Tentativi di attivazione environment (venv, .venv, env)
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "env" ]; then
    source env/bin/activate
fi

# Verifica se le dipendenze sono installate
python3 -c "import spotipy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️ ERRORE: Modulo 'spotipy' non trovato. Assicurati di aver installato le dipendenze."
    echo "Esegui: pip install -r requirements.txt"
    exit 1
fi

# Esegui il sync
python3 daily_sync.py
