# llm_bridge/config.py

MODEL_CONFIG = {
    "gpt4o_mini": {
        "adapter_service": "openai_service",
        "model_name_direct": "gpt-4o-mini",          # Name für die direkte OpenAI API
        "model_name_openrouter": "openai/gpt-4o-mini" # Name für die OpenRouter API
    },
    "claude35_sonnet": {
        "adapter_service": "claude_service",
        "model_name_direct": "claude-3.5-sonnet-20240620", # Name für die native Claude API
        "model_name_openrouter": "anthropic/claude-3.5-sonnet"     # Name für die OpenRouter API
    },
    "gemini_1_5_pro": {
        "adapter_service": "gemini_service",
        "model_name_direct": "gemini-1.5-pro-latest", # Name für die native Google API
        "model_name_openrouter": "google/gemini-pro-1.5"  # Korrigierter Name für OpenRouter
    },
    
    # OpenRouter-Gateway Modelle (immer verfügbar wenn OpenRouter API-Key vorhanden)
    "llama3_70b_via_or": {
        "adapter_service": "openrouter_gateway",
        "model_name_direct": None,
        "model_name_openrouter": "meta-llama/llama-3-70b-instruct"
    },
    "claude35_sonnet_via_or": {
        "adapter_service": "openrouter_gateway",
        "model_name_direct": None,
        "model_name_openrouter": "anthropic/claude-3.5-sonnet"
    },
    "gemini_15_pro_via_or": {
        "adapter_service": "openrouter_gateway", 
        "model_name_direct": None,
        "model_name_openrouter": "google/gemini-pro-1.5"
    }
}