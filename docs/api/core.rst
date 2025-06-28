Core Module
===========

Das Core-Modul stellt die zentrale :class:`LLMBridgeCore` Klasse bereit, die als Haupteinstiegspunkt für die LLM2LLM-Bridge dient.

LLMBridgeCore
-------------

.. automodule:: llm_bridge.core
   :members:
   :undoc-members:
   :show-inheritance:

Verwendung
----------

Die :class:`LLMBridgeCore` ist der primäre Einstiegspunkt für alle Bridge-Operationen:

.. code-block:: python

    from llm_bridge.core import LLMBridgeCore
    import asyncio

    async def example():
        # Bridge mit automatischem Plugin-Loading initialisieren
        bridge = LLMBridgeCore()
        
        # Status der geladenen Plugins anzeigen
        status = bridge.get_plugin_status()
        print(f"Geladene Plugins: {status['total_plugins']}")
        print(f"Aktive Adapter: {status['active_adapters']}")
        
        # Verfügbare Modelle abrufen
        models = bridge.get_available_models()
        print(f"Verfügbare Modelle: {models}")
        
        # Nachricht an ein LLM senden
        response = await bridge.bridge_message(
            conversation_id="test_chat",
            target_llm_name="claude35_sonnet_via_or",
            message="Was ist die Hauptstadt von Deutschland?"
        )
        print(f"Antwort: {response}")

    asyncio.run(example())

Konfiguration
-------------

Die Bridge lädt automatisch die Modellkonfiguration aus der ``models.yaml`` Datei im Projektverzeichnis. Alternativ kann eine benutzerdefinierte Konfiguration übergeben werden:

.. code-block:: python

    # Mit benutzerdefinierter Konfiguration
    custom_config = {
        "my_model": {
            "adapter_service": "openrouter_gateway",
            "model_name_openrouter": "custom/model"
        }
    }
    
    bridge = LLMBridgeCore(model_config=custom_config)

Plugin-System
-------------

Das Plugin-System wird automatisch beim Initialisieren der Bridge geladen. Plugins werden erkannt, wenn:

1. Eine Plugin-Datei im ``llm_bridge/plugins/`` Verzeichnis existiert
2. Die entsprechenden API-Schlüssel als Umgebungsvariablen verfügbar sind

Unterstützte Plugins:

- **claude_service**: Direkte Anthropic Claude API (erfordert ``CLAUDE_API_KEY``)
- **gemini_service**: Direkte Google Gemini API (erfordert ``GOOGLE_API_KEY``)  
- **openrouter_gateway**: OpenRouter Gateway (erfordert ``OPENROUTER_API_KEY``)

Workflow-Ausführung
-------------------

Workflows können direkt aus YAML-Dateien geladen und ausgeführt werden:

.. code-block:: python

    # Workflow aus Datei ausführen
    result = await bridge.execute_workflow_from_file("workflows/my_workflow.yaml")
    
    # Ergebnis prüfen
    if result['success']:
        print("Workflow erfolgreich!")
        print("Ausgaben:", result['outputs'])
    else:
        print("Workflow fehlgeschlagen:", result['error'])

Error Handling
--------------

Die Bridge implementiert robuste Fehlerbehandlung:

.. code-block:: python

    try:
        response = await bridge.bridge_message(
            conversation_id="test",
            target_llm_name="non_existent_model",
            message="Test"
        )
    except ValueError as e:
        print(f"Modell nicht gefunden: {e}")
    except Exception as e:
        print(f"Allgemeiner Fehler: {e}")