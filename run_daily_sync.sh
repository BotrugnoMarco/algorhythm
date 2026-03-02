#!/bin/bash

# Vai alla directory dello script
cd "$(dirname "$0")"

# Attiva environment se esiste (opzionale)
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Esegui il sync
python3 daily_sync.py
