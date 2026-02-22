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
MODEL_NAME = "models/gemini-flash-latest" # Usiamo l'alias generico che dovrebbe sempre esistere
BATCH_SIZE = 12
MAX_RETRIES = 3
RETRY_DELAY = 10
CLASSIFICATION_CACHE_FILE = "user_data/classification_cache.json"

# ── Cache Management ───────────────────────────────────────────────────

def load_classification_cache() -> dict[str, list[str]]:
    """Carica la cache delle classificazioni."""
    if os.path.exists(CLASSIFICATION_CACHE_FILE):
        try:
            with open(CLASSIFICATION_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Errore caricamento cache: {e}")
    return {}

def save_classification_cache(cache: dict[str, list[str]]):
    """Salva la cache delle classificazioni."""
    os.makedirs(os.path.dirname(CLASSIFICATION_CACHE_FILE), exist_ok=True)
    try:
        with open(CLASSIFICATION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Errore salvataggio cache: {e}")

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
            
            # Se è un errore 429 (Too Many Requests), aspettiamo esponenzialmente
            if "429" in str(e):
                logger.warning(f"Quota giornaliera o rate limit raggiunto. Interrompo batch.")
                # Se becchiamo 429, è probabile che sia inutile insistere subito se è la quota giornaliera.
                # Facciamo 1 tentativo lungo, poi basta.
                if attempt < MAX_RETRIES:
                    time.sleep(Retry_DELAY * 2)
                    continue 
                else:
                    raise e # Rilanciamo l'errore per fermare il loop principale
            else:
                time.sleep(RETRY_DELAY)
    
    return track_map


# ── Public API ────────────────────────────────────────────────────────

def classify_all_tracks(tracks: list, progress_callback=None):
    """
    Classifica una lista completa di brani "Artist - Title".
    Accetta sia list[str] che list[dict] (oggetti traccia).
    Restituisce un GENERATORE che yielda (n_processati, totale, batch_results).
    Gestisce automaticamente salvataggio e ripresa (resume) tramite cache JSON.
    """
    model = _init_model()
    
    # 1. Normalizzazione Input (Estrae stringhe univoche)
    # Crea una mappa o lista parallela di stringhe "Artist - Title"
    labels_to_process = []
    
    if tracks and isinstance(tracks[0], dict):
        # Caso input: list[dict]
        for t in tracks:
            lbl = t.get("label", "")
            if not lbl:
                lbl = f"{t.get('artist', 'Unknown')} - {t.get('name', 'Unknown')}"
            labels_to_process.append(lbl)
    else:
        # Caso input: list[str]
        labels_to_process = [str(t) for t in tracks]

    # 2. Carica cache esistente
    full_cache = load_classification_cache()
    
    # 3. Identifica brani mancanti (filtrando sulle stringhe)
    # Usiamo un set per lookup veloce, ma manteniamo l'ordine della lista originale se serve (anche se qui basta processare i mancanti)
    # Attenzione: labels_to_process può contenere duplicati? Meglio processare i valori unici mancanti.
    unique_labels = sorted(list(set(labels_to_process))) # Ordina per stabilità
    missing_labels = [lbl for lbl in unique_labels if lbl not in full_cache]
    
    total_count = len(unique_labels)
    processed_count = total_count - len(missing_labels)
    
    # Yield iniziale (stato cache)
    if processed_count > 0:
         existing_subset = {k: v for k, v in full_cache.items() if k in unique_labels}
         yield (processed_count, total_count, existing_subset)
    
    if not missing_labels:
        return

    # 4. Batch processing dei mancanti
    current_results = {} 
    
    # Processiamo la lista di stringhe mancanti
    for i in range(0, len(missing_labels), BATCH_SIZE):
        batch = missing_labels[i : i + BATCH_SIZE]
        
        batch_results = {}
        try:
            batch_results = _classify_batch(model, batch)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Quota exceeded" in msg:
                 logger.error(f"🛑 LIMITE RAGGIUNTO (Quota Giornaliera/Minuto): {e}")
                 # Segnaliamo che dobbiamo fermarci COMPLEATAMENTE per ora
                 break
            else:
                 logger.error(f"Errore critico nel batch {i}: {e}")
                 # Altri errori (network, 500) potrebbero essere temporanei, ma per sicurezza break
                 break
            
        if batch_results:
            full_cache.update(batch_results)
            save_classification_cache(full_cache)
            current_results.update(batch_results)
        
        processed_now = processed_count + i + len(batch)
        yield (processed_now, total_count, batch_results)
        
        # Rate limit safety
        # Torniamo a un valore ragionevole.
        time.sleep(2.0)


