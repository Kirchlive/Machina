Schnellstart
============

Diese Anleitung führt Sie durch die ersten Schritte mit der LLM2LLM-Bridge.

Installation
------------

1. **Repository klonen:**

.. code-block:: bash

    git clone <repository-url>
    cd llm2llm-bridge

2. **Abhängigkeiten installieren:**

.. code-block:: bash

    pip install -r requirements.txt

3. **Umgebungsvariablen konfigurieren:**

Erstellen Sie eine ``.env`` Datei im Projektverzeichnis:

.. code-block:: bash

    # OpenRouter (empfohlen für den Start)
    OPENROUTER_API_KEY=your_openrouter_api_key_here
    
    # Optional: Direkte Provider-APIs
    CLAUDE_API_KEY=your_claude_api_key_here
    GOOGLE_API_KEY=your_google_api_key_here
    
    # LangFuse Observability (optional)
    LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
    LANGFUSE_SECRET_KEY=your_langfuse_secret_key
    LANGFUSE_HOST=https://cloud.langfuse.com

Erste Schritte
--------------

**1. Plugin-System testen**

.. code-block:: python

    from llm_bridge.core import LLMBridgeCore
    import asyncio

    async def test_plugins():
        bridge = LLMBridgeCore()
        
        # Plugin-Status anzeigen
        status = bridge.get_plugin_status()
        print(f"🔌 Geladene Plugins: {status['total_plugins']}")
        
        for plugin_name, info in status['plugins'].items():
            status_icon = "✅" if info['is_available'] else "⚠️"
            print(f"   {status_icon} {plugin_name}: {info['description']}")

    asyncio.run(test_plugins())

**2. Verfügbare Modelle anzeigen**

.. code-block:: python

    async def show_models():
        bridge = LLMBridgeCore()
        models = bridge.get_available_models()
        
        print("📋 Verfügbare Modelle:")
        for model in models:
            print(f"   - {model}")

    asyncio.run(show_models())

**3. Erste Nachricht senden**

.. code-block:: python

    async def send_message():
        bridge = LLMBridgeCore()
        
        response = await bridge.bridge_message(
            conversation_id="quickstart_demo",
            target_llm_name="claude35_sonnet_via_or",  # Über OpenRouter
            message="Erkläre mir Machine Learning in einem Satz."
        )
        
        print("🤖 Antwort:", response)

    asyncio.run(send_message())

**4. Einfachen Workflow ausführen**

Erstellen Sie eine Datei ``my_first_workflow.yaml``:

.. code-block:: yaml

    name: "Mein erster Workflow"
    description: "Erstellt eine Idee und bewertet sie"
    
    steps:
      - id: "idea_generation"
        model: "claude35_sonnet_via_or"
        prompt: "Generiere eine innovative App-Idee in 2 Sätzen."
      
      - id: "idea_evaluation"
        model: "gemini_15_pro_via_or"
        prompt: |
          Bewerte diese App-Idee auf einer Skala von 1-10:
          "{{ outputs.idea_generation }}"
          
          Gib nur die Zahl zurück.

Workflow ausführen:

.. code-block:: python

    async def run_workflow():
        bridge = LLMBridgeCore()
        
        result = await bridge.execute_workflow_from_file("my_first_workflow.yaml")
        
        if result['success']:
            print("✅ Workflow erfolgreich!")
            print(f"💡 Idee: {result['outputs']['idea_generation']}")
            print(f"⭐ Bewertung: {result['outputs']['idea_evaluation']}")
        else:
            print(f"❌ Workflow fehlgeschlagen: {result['error']}")

    asyncio.run(run_workflow())

API-Server starten
------------------

Für REST-API Zugriff:

.. code-block:: bash

    # API-Server starten
    cd api_server
    uvicorn main:app --reload --port 8000

    # Testen mit curl
    curl http://localhost:8000/v1/models

Dashboard starten
-----------------

Für die grafische Oberfläche:

.. code-block:: bash

    streamlit run dashboard.py

Öffnen Sie http://localhost:8501 in Ihrem Browser.

Nächste Schritte
----------------

- :doc:`configuration` - Detaillierte Konfiguration
- :doc:`workflows` - Erweiterte Workflow-Patterns  
- :doc:`api/core` - Vollständige API-Referenz
- :doc:`development/plugins` - Eigene Plugins entwickeln

Fehlerbehebung
--------------

**Problem: "Keine Plugins geladen"**

- Überprüfen Sie Ihre ``.env`` Datei
- Stellen Sie sicher, dass mindestens ein API-Schlüssel gesetzt ist

**Problem: "Model not found"**

- Verwenden Sie ``bridge.get_available_models()`` um verfügbare Modelle zu sehen
- Überprüfen Sie die ``models.yaml`` Konfiguration

**Problem: API-Verbindungsfehler**

- Überprüfen Sie Ihre API-Schlüssel
- Testen Sie die Netzwerkverbindung zu den Provider-APIs