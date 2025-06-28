import os
import asyncio  # NEU: asyncio importieren
import uuid  # Zum Generieren einer einzigartigen ID
from dotenv import load_dotenv
from app.core.core import LLMBridgeCore
from app.core.adapters.openrouter_adapter import OpenRouterAdapter
from app.core.adapters.claude_adapter import ClaudeAdapter
# NEU: Den neuen GeminiAdapter importieren
from app.core.adapters.gemini_adapter import GeminiAdapter
from app.core.config import MODEL_CONFIG

load_dotenv()

# 'def main' wird zu 'async def main'
async def main():
    print("🚀 Initializing bridge with a central model registry from config.py...")
    bridge = LLMBridgeCore(model_config=MODEL_CONFIG)

    # Alle API-Schlüssel laden
    openai_api_key = os.getenv("OPENAI_API_KEY")
    claude_api_key = os.getenv("CLAUDE_API_KEY")
    google_api_key = os.getenv("GOOGLE_API_KEY")  # NEU
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

    print("\n🔍 Registering adapter services based on API key priority...")
    
    # Registrierung für "openai_service" (unverändert)
    if openai_api_key:
        bridge.register_llm("openai_service", OpenRouterAdapter(api_key=openai_api_key))
        print("  ✅ 'openai_service' registered using DIRECT API key.")
    elif openrouter_api_key:
        bridge.register_llm("openai_service", OpenRouterAdapter(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1"))
        print("  🟡 'openai_service' registered using OpenRouter (fallback).")

    # Registrierung für "claude_service" (unverändert)
    if claude_api_key:
        bridge.register_llm("claude_service", ClaudeAdapter(api_key=claude_api_key))
        print("  ✅ 'claude_service' registered using DIRECT API key.")
    elif openrouter_api_key:
        bridge.register_llm("claude_service", OpenRouterAdapter(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1"))
        print("  🟡 'claude_service' registered using OpenRouter (fallback).")
        
    # NEU: Registrierung für "gemini_service"
    if google_api_key:
        bridge.register_llm("gemini_service", GeminiAdapter(api_key=google_api_key))
        print("  ✅ 'gemini_service' registered using DIRECT API key.")
    elif openrouter_api_key:
        bridge.register_llm("gemini_service", OpenRouterAdapter(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1"))
        print("  🟡 'gemini_service' registered using OpenRouter (fallback).")
        
    # Registrierung für "openrouter_gateway" (unverändert)
    if openrouter_api_key:
        bridge.register_llm("openrouter_gateway", OpenRouterAdapter(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1"))
        print("  ✅ Generic 'openrouter_gateway' registered.")

    print("\n✅ Bridge initialization complete.")

    # Eine einzigartige ID für diese eine Konversation erstellen
    conv_id = f"conv_{uuid.uuid4().hex[:8]}"
    print(f"\nStarting new conversation with ID: {conv_id}")

    # Neues Beispiel: Claude -> Direct Gemini
    if "claude35_sonnet" in MODEL_CONFIG and "gemini_1_5_pro" in MODEL_CONFIG:
        print("\n--- Creative Relay: Claude 3.5 Sonnet -> Direct Google Gemini 1.5 Pro ---")
        
        prompt_step1 = "Erfinde ein Konzept für ein Videospiel, das auf dem Prinzip der Photosynthese basiert. Beschreibe es in zwei Sätzen."
        print(f"\n[Schritt 1] 💬 Prompt an 'claude35_sonnet': {prompt_step1}")
        
        game_idea = await bridge.bridge_message(
            conversation_id=conv_id,  # <-- ID übergeben
            target_llm_name="claude35_sonnet", 
            message=prompt_step1
        )
        print(f"🤖 Antwort von 'claude35_sonnet': {game_idea}")

        if game_idea and "Error:" not in game_idea:
            prompt_step2 = f"Schreibe einen kurzen, atmosphärischen Eröffnungs-Absatz für die Spielanleitung dieses Spiels: '{game_idea}'"
            print(f"\n[Schritt 2] 💬 Stafettenübergabe an 'gemini_1_5_pro': {prompt_step2}")
            
            opening_paragraph = await bridge.bridge_message(
                conversation_id=conv_id,  # <-- Dieselbe ID übergeben
                target_llm_name="gemini_1_5_pro", 
                message=prompt_step2
            )
            print(f"🤖 Finale Antwort von 'gemini_1_5_pro':\n{opening_paragraph}")

    print("\n🏁 All operations finished.")


if __name__ == "__main__":
    asyncio.run(main())