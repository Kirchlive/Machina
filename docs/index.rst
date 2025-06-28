LLM2LLM-Bridge Documentation
=============================

Willkommen zur offiziellen Dokumentation der **LLM2LLM-Bridge** - einer universellen Middleware für bidirektionale LLM-Kommunikation.

Die LLM2LLM-Bridge ist eine hochperformante, erweiterbare Plattform, die es ermöglicht, verschiedene Large Language Models nahtlos zu orchestrieren und komplexe Workflows zu automatisieren.

🚀 **Schnellstart**
-------------------

.. code-block:: python

    from llm_bridge.core import LLMBridgeCore
    import asyncio

    async def main():
        # Bridge initialisieren (lädt automatisch Plugins und Model Registry)
        bridge = LLMBridgeCore()
        
        # Verfügbare Modelle anzeigen
        models = bridge.get_available_models()
        print("Verfügbare Modelle:", models)
        
        # Nachricht senden
        response = await bridge.bridge_message(
            conversation_id="demo_chat",
            target_llm_name="claude35_sonnet_via_or",
            message="Erkläre Quantencomputing in einem Satz."
        )
        print("Antwort:", response)
        
        # Workflow aus YAML-Datei ausführen
        result = await bridge.execute_workflow_from_file("my_workflow.yaml")
        print("Workflow-Ergebnis:", result)

    asyncio.run(main())

📖 **Inhaltsverzeichnis**
-------------------------

.. toctree::
   :maxdepth: 2
   :caption: Benutzerhandbuch

   quickstart
   installation
   configuration
   workflows

.. toctree::
   :maxdepth: 2
   :caption: API-Referenz

   api/core
   api/routing
   api/plugins
   api/orchestration

.. toctree::
   :maxdepth: 2
   :caption: Entwickler-Guide

   development/plugins
   development/adapters
   development/extending

.. toctree::
   :maxdepth: 1
   :caption: Zusätzliches

   changelog
   contributing
   license

✨ **Hauptfeatures**
---------------------

🔌 **Plugin-System**
   Dynamisches Laden von LLM-Adaptern basierend auf verfügbaren API-Schlüsseln

🔄 **Workflow-Engine**
   YAML-basierte Orchestrierung komplexer, mehrstufiger LLM-Pipelines

📊 **Observability**
   Integration mit LangFuse für umfassendes Monitoring und Tracing

🛡️ **Resilience**
   Circuit Breaker Pattern und State Machines für hohe Verfügbarkeit

🌐 **API Gateway**
   RESTful API für einfache Integration in bestehende Systeme

📋 **Model Registry**
   Zentrale Konfiguration und Verwaltung aller unterstützten LLM-Modelle

Indizes und Tabellen
====================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`