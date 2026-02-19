"""
gemini_classifier.py
────────────────────
Classifica le tracce in playlist di genere/mood usando
Google Gemini 1.5 Flash con output JSON strutturato.
"""

import os
import json
import time
import logging
import google.generativeai as genai
import classifier
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configurazione Gemini ──────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "models/gemini-1.5-flash"  # Aggiornato a 1.5-flash esplicito
BATCH_SIZE = 15
MAX_RETRIES = 3
RETRY_DELAY = 5


# ── Costruzione Prompt Dinamico ────────────────────────────────────────

def get_system_prompt() -> str:
    """Genera il prompt di sistema basandosi sulle categorie attuali."""
    
    # Ricarica settings attuali
    current_genres, _ = classifier.load_settings()
    
    # Formatta elenco numerato
    categories_text = "\n".join([f'{i+1}. "{genre}"' for i, genre in enumerate(current_genres)])

    return f"""Sei un esperto musicale e classificatore di brani.
Ti verrà fornita una lista di brani nel formato "Artista - Titolo".

Compito:
Assegna ogni brano a 1 o MASSIMO 2 categorie tra quelle elencate sotto.

Categorie Disponibili:
{categories_text}

Regole Output:
1. Restituisci SOLO un array JSON di oggetti.
2. Formato oggetto: {{"track": "Artist - Title", "categories": ["Category A", "Category B"]}}
3. NON usare markdown (no ```json).
4. Se nessuno delle categorie è perfetta, scegli la categoria "Altro" se esiste o la più adeguata.
5. Sii preciso e veloce.
"""

def _build_user_prompt(labels: list[str]) -> str:
    """Costruisce il prompt utente con la lista di brani numerata."""
    numbered = "\n".join(f"{i+1}. {lbl}" for i, lbl in enumerate(labels))
    return (
        f"Classifica questi {len(labels)} brani:\n\n"
        f"{numbered}\n\n"
        f"Rispondi SOLO con il JSON array."
    )


# ── Client Gemini ─────────────────────────────────────────────────────

def _init_model() -> genai.GenerativeModel:
    """Inizializza il modello Gemini."""
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Recupera prompt aggiornato
    system_instruction = get_system_prompt()
    
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_instruction,
        generation_config=genai.GenerationConfig(
            temperature=0.3,
            response_mime_type="application/json"
        ),
    )


def _classify_batch(model: genai.GenerativeModel,
                    labels: list[str]) -> dict[str, list[str]]:
    """Invia un batch a Gemini."""
    prompt = _build_user_prompt(labels)
    
    track_map: dict[str, list[str]] = {}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            
            # Pulizia MD se presente
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`").replace("json\n", "").strip()

            parsed = json.loads(raw_text)

            # Normalizzazione output da lista di oggetti a track_map
            if isinstance(parsed, list):
                for item in parsed:
                    track = item.get("track", "")
                    cats = item.get("categories", [])
                    if isinstance(cats, str): cats = [cats]
                    
                    if track:
                        track_map[track] = cats
            
            return track_map

        except Exception as e:
            logger.warning(f"Batch fallito (tentativo {attempt}): {e}")
            time.sleep(RETRY_DELAY)
    
    return track_map


# ── Public API ────────────────────────────────────────────────────────

def classify_all_tracks(tracks: list[str], progress_callback=None) -> dict[str, list[str]]:
    """
    Classifica una lista completa di brani "Artist - Title".
    """
    model = _init_model()
    results = {}
    total = len(tracks)
    
    # Batch processing
    for i in range(0, total, BATCH_SIZE):
        batch = tracks[i : i + BATCH_SIZE]
        
        # Aggiorna progress bar
        if progress_callback:
            progress_callback(i, total)
            
        batch_results = _classify_batch(model, batch)
        if batch_results:
            results.update(batch_results)
        
        # Rate limit safety per Free Tier
        time.sleep(1.0)
        
    if progress_callback:
        progress_callback(total, total)
        
    return results

