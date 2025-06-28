# llm_bridge/core.py
import os
import importlib.util
import inspect
import yaml
import aiofiles
from langfuse import Langfuse
from pydantic import ValidationError
from .config.schema import RegistrySchema
from .routing.router import Router
from .monitoring.status_monitor import StatusMonitor
from .monitoring.event_store import EventStore  # <-- NEU: EventStore statt BasicLogger
from .orchestration.circuit_breaker import CircuitBreaker
from .plugins.base_plugin import LLMAdapterPlugin

class LLMBridgeCore:
    def __init__(self, model_config: dict = None, registry_config: RegistrySchema = None):
        """
        Private Constructor - verwende stattdessen create() oder create_async() Factory-Methoden.
        """
        self.adapters = {}
        self.circuit_breakers = {}
        self.loaded_plugins = {}
        # Der Router muss die Breaker und EventStore kennen
        self.event_store = EventStore()  # <-- NEU: EventStore initialisieren
        
        # --- NEU: LangFuse Initialisierung ---
        self.langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST"),
        )
        # --- Ende NEU ---
        
        # Registry-Konfiguration setzen
        self.registry_config = registry_config
        
        # Model config aus Registry extrahieren oder direkt verwenden
        if model_config is None and registry_config is not None:
            model_config = {k: v.model_dump() for k, v in registry_config.models.items()}
        elif model_config is None:
            raise ValueError("Entweder model_config oder registry_config muss angegeben werden.")
        
        # --- NEU: Universelles Adapter-System laden ---
        self._load_all_adapters(model_config)
        # --- Ende NEU ---
        
        self.router = Router(self.adapters, self.circuit_breakers, model_config, self.event_store, self.langfuse)

    @classmethod
    async def create_async(cls, model_config: dict = None) -> 'LLMBridgeCore':
        """
        Asynchrone Factory-Methode zur Erstellung einer LLMBridgeCore-Instanz.
        Lädt die Konfiguration asynchron aus Dateien.
        
        Args:
            model_config (dict, optional): Direkte Modell-Konfiguration (für Tests).
                                         Falls None, wird die Registry asynchron geladen.
        
        Returns:
            LLMBridgeCore: Vollständig initialisierte Instanz
        """
        print("🔄 [ASYNC] Erstelle LLMBridgeCore mit asynchroner Konfigurationsladung...")
        
        registry_config = None
        if model_config is None:
            try:
                # Erstelle temporäre Instanz nur zum Laden der Registry
                temp_instance = cls.__new__(cls)
                registry_config = await temp_instance._load_and_validate_registry_async()
                print("✅ [ASYNC] Registry erfolgreich asynchron geladen")
            except (ValidationError, FileNotFoundError) as e:
                print(f"❌ [ASYNC] FATAL: Konnte die Registry nicht laden oder validieren. Fehler: {e}")
                print("Das System kann ohne gültige Konfiguration nicht funktionieren.")
                raise SystemExit(1)
        
        # Erstelle die finale Instanz mit den geladenen Daten
        return cls(model_config=model_config, registry_config=registry_config)

    @classmethod
    def create(cls, model_config: dict = None) -> 'LLMBridgeCore':
        """
        Synchrone Factory-Methode für Backward-Kompatibilität.
        
        Args:
            model_config (dict): Direkte Modell-Konfiguration
        
        Returns:
            LLMBridgeCore: Instanz (ohne asynchrone Konfigurationsladung)
        """
        print("⚠️ [SYNC] Erstelle LLMBridgeCore im synchronen Kompatibilitätsmodus...")
        
        if model_config is None:
            raise ValueError("Im synchronen Modus muss model_config angegeben werden. "
                           "Verwende create_async() für automatische Registry-Ladung.")
        
        return cls(model_config=model_config, registry_config=None)

    def _discover_plugins(self):
        """Lädt alle Plugin-Klassen aus dem plugins-Verzeichnis."""
        plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')
        
        if not os.path.exists(plugins_dir):
            print("⚠️ Plugin-Verzeichnis nicht gefunden.")
            return
        
        for filename in os.listdir(plugins_dir):
            if filename.endswith('.py') and not filename.startswith('__') and filename != 'base_plugin.py':
                try:
                    # Modul dynamisch laden
                    module_path = os.path.join(plugins_dir, filename)
                    module_name = f"llm_bridge.plugins.{filename[:-3]}"
                    
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Nach Plugin-Klassen suchen
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (issubclass(obj, LLMAdapterPlugin) and 
                            obj is not LLMAdapterPlugin):
                            
                            # Plugin-Klasse unter ihrem service_name speichern
                            plugin_instance = obj()
                            self.loaded_plugins[plugin_instance.name] = obj
                            
                except Exception as e:
                    print(f"❌ Fehler beim Laden von Plugin-Datei '{filename}': {e}")

    def _load_all_adapters(self, model_config: dict):
        """
        Lädt dynamisch ALLE Adapter und unterscheidet dabei korrekt
        zwischen API-basierten Diensten und plattformbasierten Modellen.
        """
        print("🔌 Lade universelle Adapter...")
        
        self._discover_plugins()  # Helper-Methode, die nur Plugin-Klassen lädt
        initialized_api_services = {}

        for model_name, config in model_config.items():
            if model_name.startswith('_'):
                continue

            adapter_service = config.get('adapter_service')
            platform = config.get('platform', 'api')

            if not adapter_service: 
                continue
            plugin_class = self.loaded_plugins.get(adapter_service)
            if not plugin_class: 
                continue
            
            try:
                plugin_instance = plugin_class()
                # API-Adapter: Eine Instanz pro Service (z.B. 'openrouter_gateway')
                if platform == 'api':
                    if adapter_service not in initialized_api_services:
                        if plugin_instance.is_available(config):
                            adapter = plugin_instance.create_adapter(config)
                            self.adapters[adapter_service] = adapter
                            self.circuit_breakers[adapter_service] = CircuitBreaker(self.event_store, adapter_service)
                            initialized_api_services[adapter_service] = True
                            print(f"✅ API-Adapter-Service '{adapter_service}' geladen.")
                # Plattform-Adapter: Eine Instanz pro Modell (z.B. 'claude_code_wsl')
                else:
                    if plugin_instance.is_available(config):
                        adapter = plugin_instance.create_adapter(config)
                        self.adapters[model_name] = adapter
                        self.circuit_breakers[model_name] = CircuitBreaker(self.event_store, model_name)
                        print(f"✅ Plattform-Adapter für '{model_name}' ({platform}) geladen.")
            except Exception as e:
                print(f"❌ Fehler beim Laden des Adapters für '{model_name}': {e}")
        
        print(f"🔌 Universelle Adapter geladen: {len(self.adapters)} Instanzen insgesamt.")
    
    async def _load_and_validate_registry_async(self) -> RegistrySchema:
        """
        Lädt die YAML-Datei asynchron, parst sie und validiert sie gegen unser Pydantic-Schema.
        Bricht bei Fehlern den Start der Anwendung ab (Fail-Fast-Prinzip).
        """
        registry_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'registry.yaml')
        
        if not os.path.exists(registry_path):
            print(f"❌ FATAL: Registry nicht gefunden: {registry_path}")
            raise FileNotFoundError(f"Registry-Datei fehlt: {registry_path}")
        
        print(f"🔍 Lade und validiere Registry asynchron von: {registry_path}")
        
        try:
            async with aiofiles.open(registry_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                raw_data = yaml.safe_load(content)
            
            # Die `build_from_yaml_data`-Methode kümmert sich um die Transformation
            # und die `model_validate`-Methode im Inneren löst die `ValidationError` aus.
            validated_config = RegistrySchema.build_from_yaml_data(raw_data)
            
            print(f"✅ Registry erfolgreich geladen und validiert:")
            print(f"   🤖 {len(validated_config.models)} Modelle")
            print(f"   👤 {len(validated_config.agents)} Agenten")
            print(f"   👥 {len(validated_config.crews)} Crews")
            print(f"   📜 {len(validated_config.mission_templates)} Mission Templates")
            
            return validated_config
            
        except yaml.YAMLError as e:
            print(f"❌ FATAL: YAML-Parsing-Fehler in {registry_path}: {e}")
            raise
        except ValidationError as e:
            print(f"❌ FATAL: Schema-Validierungsfehler in {registry_path}:")
            print(f"   {e}")
            raise
    
    def get_registry_config(self) -> RegistrySchema:
        """Gibt die validierte Registry-Konfiguration zurück."""
        if self.registry_config is None:
            raise RuntimeError("Registry-Konfiguration nicht geladen")
        return self.registry_config

    def get_plugin_status(self) -> dict:
        """Gibt Status-Informationen über alle geladenen Plugins zurück."""
        return {
            "total_plugins": len(self.loaded_plugins),
            "active_adapters": len(self.adapters),
            "plugins": {name: plugin.get_status_info() for name, plugin in self.loaded_plugins.items()}
        }

    async def register_llm(self, name: str, adapter):
        """Registriert einen neuen LLM-Adapter UND einen passenden Circuit Breaker."""
        self.adapters[name] = adapter
        self.circuit_breakers[name] = CircuitBreaker(self.event_store, name)  # <-- Breaker mit EventStore
        await self.event_store.log_event("INFO", "LLMBridgeCore", f"Adapter '{name}' registered.")

    async def bridge_message(self, conversation_id: str, target_llm_name: str, message: str, **kwargs) -> str:
        await self.event_store.log_event("INFO", "LLMBridgeCore", 
                                        f"Bridging message to '{target_llm_name}'", 
                                        conversation_id=conversation_id,
                                        message_length=len(message))
        self.monitor.set_status("YELLOW")
        await self.event_store.log_event("STATUS", "StatusMonitor", 
                                        f"Monitor status: {self.monitor.get_status_colored()}")
        
        try:
            # Reiche die conversation_id an den Router weiter
            response = await self.router.route_message(
                conversation_id=conversation_id,
                target_llm_name=target_llm_name,
                prompt=message,
                **kwargs
            )
            self.monitor.set_status("GREEN")
            await self.event_store.log_event("INFO", "LLMBridgeCore", "Message bridged successfully.",
                                            conversation_id=conversation_id)
            await self.event_store.log_event("STATUS", "StatusMonitor", 
                                            f"Monitor status: {self.monitor.get_status_colored()}")
            return response
            
        except Exception as e:
            # KORREKTUR: Loggen und dann die Exception weiterwerfen
            self.monitor.set_status("RED")
            await self.event_store.log_event("ERROR", "LLMBridgeCore", 
                                            f"Failed to bridge message: {e}",
                                            conversation_id=conversation_id)
            await self.event_store.log_event("STATUS", "StatusMonitor", 
                                            f"Monitor status: {self.monitor.get_status_colored()}")
            raise e  # <-- Wirft den Fehler weiter, anstatt ihn zu "schlucken"
    
    # ========================================
    # SDK-KOMFORT-METHODEN FÜR ENTWICKLER
    # ========================================
    
    def get_available_models(self) -> list[str]:
        """
        Gibt eine Liste aller aktuell verfügbaren Modelle zurück.
        
        Returns:
            list[str]: Liste der Modellnamen, die über die geladenen Adapter verfügbar sind.
        """
        return list(self.router.model_config.keys()) if self.router.model_config else []
    
    def get_plugin_status(self) -> dict:
        """
        Gibt detaillierte Informationen über geladene Plugins und aktive Adapter zurück.
        
        Returns:
            dict: Status-Dictionary mit Plugin- und Adapter-Informationen.
        """
        plugin_info = {}
        for name, plugin in self.loaded_plugins.items():
            plugin_info[name] = {
                'description': plugin.description,
                'is_available': name in self.adapters
            }
        
        return {
            'total_plugins': len(self.loaded_plugins),
            'active_adapters': len(self.adapters),
            'plugins': plugin_info
        }
    
    async def execute_workflow_from_file(self, workflow_path: str) -> dict:
        """
        Lädt und führt einen YAML-Workflow aus einer Datei aus.
        
        Args:
            workflow_path (str): Pfad zur YAML-Workflow-Datei.
            
        Returns:
            dict: Workflow-Ausführungsergebnisse.
            
        Raises:
            FileNotFoundError: Wenn die Workflow-Datei nicht gefunden wird.
            yaml.YAMLError: Wenn die YAML-Datei nicht geparst werden kann.
        """
        import yaml
        from .orchestration.workflow_engine import WorkflowOrchestrator
        
        if not os.path.exists(workflow_path):
            raise FileNotFoundError(f"Workflow-Datei nicht gefunden: {workflow_path}")
        
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow_def = yaml.safe_load(f)
        
        orchestrator = WorkflowOrchestrator(self)
        return await orchestrator.execute_workflow(workflow_def)