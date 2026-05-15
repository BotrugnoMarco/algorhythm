import os
import google.generativeai as genai
from dotenv import load_dotenv

def check_available_models():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ ERRORE: GEMINI_API_KEY non trovata nelle variabili d'ambiente.")
        print("Assicurati di avere un file .env corretto.")
        return

    print(f"✅ API Key trovata. Interrogo Google per i modelli disponibili...")
    
    try:
        genai.configure(api_key=api_key)
        
        found_any = False
        print("\n--- MODELLI DISPONIBILI PER generateContent ---")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f" Nome: {m.name}")
                print(f" Display Name: {m.display_name}")
                print(f" Input Token Limit: {m.input_token_limit}")
                print("-" * 30)
                found_any = True
        
        if not found_any:
            print("❌ Nessun modello disponibile trovato per generateContent.")
        else:
            print("\n✅ Copia uno dei codici 'Nome' (es. models/gemini-pro) e usalo in gemini_classifier.py")
            
    except Exception as e:
        print(f"❌ Errore durante il recupero dei modelli: {e}")

if __name__ == "__main__":
    check_available_models()
