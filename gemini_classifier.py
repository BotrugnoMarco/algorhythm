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
from dotenv import load_dotenv
import google.generativeai as genai

from classifier import GENRE_PLAYLISTS

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configurazione Gemini ──────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Utilizziamo l'alias "flash-latest" presente nella tua lista. 
# È la scelta più sicura per il Free Tier (solitamente punta a 1.5 Flash).
MODEL_NAME = "models/gemini-flash-latest" 
BATCH_SIZE = 10           # Flash gestisce bene batch più grandi
MAX_RETRIES = 5           
RETRY_DELAY = 10


# ── Prompt di sistema ──────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei un esperto musicale e classificatore di brani.
Ti verrà fornita una lista di brani nel formato "Artista - Titolo".

Gemini must assign each track to 1, or MAXIMUM 2 relevant categories.
The JSON output must use an array of strings for the "categories" key, like this:
{"track": "Artist - Title", "categories": ["Category 1", "Category 2"]}

Le categorie disponibili sono:

1. "🤪 Meme, Sigle & Trash" — Sigle di cartoni animati, canzoni troll, inni meme, brani trash/divertenti
2. "🎸 Indie ma non è un gioco" — Indie Rock, Indie Pop, Alternative, Indie italiano / Itpop
3. "🇮🇹 Pop & Cantautorato ITA" — Musica italiana classica e Pop italiano (ESCLUSI Indie e Rap italiani)
4. "🌍 Pop & Radio Hits" — Pop mainstream, hit internazionali, Synthpop
5. "🎸 Guitar Anthems" — Classic Rock, Hard Rock, Metal (ESCLUSO Indie)
6. "🏙️ Concrete Jungle" — Rap, Trap, Hip Hop, R&B, Urban
7. "🪩 Club Life" — House, Techno, EDM, Dance
8. "💔 Deep & Emotional" — Canzoni tristi, ballad emozionali
9. "⚡ High Voltage" — Brani ad alta energia / workout che non rientrano nelle categorie precedenti
10. "🍃 Chill State of Mind" — Musica rilassante, lo-fi, acustica, sottofondo

REGOLE IMPORTANTI:
- Ogni brano va in 1 o MASSIMO 2 categorie.
- I brani Indie NON vanno in "Guitar Anthems".
- **REGOLA SPECIALE ITALIA**: Se l'artista o il brano è italiano, DEVI inserirlo ANCHE nella categoria "🇮🇹 Pop & Cantautorato ITA", oltre alla sua categoria di genere (es. Rap, Indie, Rock). Questa categoria "extra" non conta nel limite.
- Rispondi SOLO con il JSON richiesto, senza testo aggiuntivo."""


def _build_user_prompt(labels: list[str]) -> str:
    """Costruisce il prompt utente con la lista di brani numerata."""
    numbered = "\n".join(f"{i+1}. {lbl}" for i, lbl in enumerate(labels))
    return (
        f"Classifica i seguenti {len(labels)} brani. "
        f"Rispondi con un array JSON di oggetti, ognuno con le chiavi "
        f'"track" (stringa esatta del brano) e "categories" (array di stringhe).\n\n'
        f"{numbered}"
    )


# ── Client Gemini ─────────────────────────────────────────────────────

def _init_model() -> genai.GenerativeModel:
    """Inizializza il modello Gemini con configurazione JSON."""
    logger.info(f"Inizializzazione modello Gemini: {MODEL_NAME}")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            # Gemini Pro 1.0 gestisce meglio il JSON via prompt che via config
            # response_mime_type="application/json", 
            temperature=0.2,
        ),
    )


def _classify_batch(model: genai.GenerativeModel,
                    labels: list[str]) -> dict[str, list[str]]:
    """
    Invia un singolo batch di label a Gemini e restituisce
    la mappa { "Artist - Title": ["cat1", "cat2"] }.

    Gestisce retry con backoff in caso di errori temporanei.
    """
    prompt = _build_user_prompt(labels)
    valid_categories = set(GENRE_PLAYLISTS)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                # Rimuove prima e ultima riga se sono marcatori
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            # P
            # Parse JSON — ci aspettiamo una lista di oggetti
            parsed = json.loads(raw_text)

            # Normalizza: accetta sia lista di oggetti che dict piatto
            track_map: dict[str, list[str]] = {}
            if isinstance(parsed, list):
                for item in parsed:
                    track = item.get("track", "")
                    cats = item.get("categories", [])
                    if isinstance(cats, str):
                        cats = [cats]
                    track_map[track] = cats[:4]  # max 4 per sicurezza
            elif isinstance(parsed, dict):
                for track, cats in parsed.items():
                    if isinstance(cats, str):
                        cats = [cats]
                    if isinstance(cats, list):
                        track_map[track] = cats[:4]

            # Validazione categorie
            result: dict[str, list[str]] = {}
            for label in labels:
                raw_cats = track_map.get(label, [])
                validated: list[str] = []
                for cat in raw_cats:
                    if cat in valid_categories:
                        validated.append(cat)
                    else:
                        matched = _fuzzy_match_category(cat, valid_categories)
                        if matched:
                            validated.append(matched)
                if not validated:
                    logger.warning(
                        "Nessuna categoria valida per '%s' → default", label
                    )
                    validated = ["🌍 Pop & Radio Hits"]
                result[label] = validated

            return result

        except json.JSONDecodeError as e:
            logger.warning("Tentativo %d/%d – JSON non valido: %s",
                           attempt, MAX_RETRIES, e)
        except Exception as e:
            logger.warning("Tentativo %d/%d – Errore Gemini: %s",
                           attempt, MAX_RETRIES, e)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)  # backoff lineare

    # Se tutti i tentativi falliscono, assegna un fallback
    logger.error("Tutti i tentativi falliti per il batch. Uso fallback.")
    return {label: ["🌍 Pop & Radio Hits"] for label in labels}


def _fuzzy_match_category(candidate: str | None,
                          valid: set[str]) -> str | None:
    """
    Tenta un match approssimativo se Gemini restituisce la
    categoria con lievi differenze (es. senza emoji).
    """
    if candidate is None:
        return None
    candidate_lower = candidate.lower().strip()
    for v in valid:
        # Confronto senza emoji (primi 2-4 caratteri possono essere emoji)
        v_text = v.split(" ", 1)[-1].lower() if " " in v else v.lower()
        if v_text in candidate_lower or candidate_lower in v_text:
            return v
    return None


# ── Funzione pubblica ─────────────────────────────────────────────────

def classify_all_tracks(tracks: list[dict]):
    """
    Generatore che classifica le tracce in batch.
    Yielda (batch_index, total_batches, partial_results) ad ogni step.
    Permette al chiamante di controllare il loop e aggiornare la UI.
    """
    model = _init_model()

    labels = [t["label"] for t in tracks]
    total_batches = (len(labels) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(0, len(labels), BATCH_SIZE):
        batch = labels[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        logger.info("Classifico batch %d/%d (%d brani)…",
                     batch_num, total_batches, len(batch))

        # Esegue la classificazione del batch
        batch_result = _classify_batch(model, batch)
        
        # Restituisce il controllo al chiamante
        yield batch_num, total_batches, batch_result

        # Rate-limiting gentile tra batch
        # Aumentato drasticamente per Free Tier (evita 429 Quota Exceeded)
        if i + BATCH_SIZE < len(labels):
            time.sleep(10)

