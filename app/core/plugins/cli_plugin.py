# app/core/plugins/cli_plugin.py
import asyncio
import os
import shlex
from typing import Dict, Any, List
from ..adapters.universal_adapter import UniversalAdapter, AdapterError
from .base_plugin import LLMAdapterPlugin

class CLIToolAdapter(UniversalAdapter):
    """Adapter für die Interaktion mit Kommandozeilen-Tools."""
    def __init__(self, model_config: Dict[str, Any]):
        super().__init__(model_config)
        self.command = self.config.get('command')
        self.execution_env = self.config.get('execution_env', 'local')
        self.wsl_distro = self.config.get('wsl_distro')

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        
        # --- NEUE DEBUG-AUSGABE ---
        print("\n--- DEBUG: CLIToolAdapter-Instanz ---")
        print(f"  Modell-Config Name: {self.config.get('name', 'N/A')}")
        print(f"  Tool-Name: {self.tool_name}")
        print(f"  Befehl: {self.command}")
        print(f"  Ausführungsumgebung: {self.execution_env}")
        print("-------------------------------------\n")
        # --- ENDE DEBUG-AUSGABE ---

        prompt = messages[-1]['content']
        if self.execution_env == 'wsl':
            response_text = await self._execute_wsl_command(prompt, **kwargs)
        else:
            response_text = await self._execute_local_command(prompt, **kwargs)
        
        return {"choices": [{"message": {"content": response_text}}]}

    async def _execute_local_command(self, prompt, **kwargs):
        process = await asyncio.create_subprocess_shell(
            self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate(input=prompt.encode('utf-8'))
        if process.returncode != 0:
            raise AdapterError(f"Local command failed: {stderr.decode()}")
        return stdout.decode().strip()

    async def _execute_wsl_command(self, prompt, **kwargs):
        if not self.wsl_distro:
            # Versuche, die Standard-Distribution zu finden
            proc_distro = await asyncio.create_subprocess_shell('wsl -l', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout_distro, _ = await proc_distro.communicate()
            output = stdout_distro.decode('utf-16-le', errors='ignore').strip()
            lines = output.splitlines()
            for line in lines:
                if '(Default)' in line:
                    self.wsl_distro = line.replace('(Default)', '').strip()
                    break
            if not self.wsl_distro and len(lines) > 1:
                 self.wsl_distro = lines[1].strip() # Nimm die erste aus der Liste

        if not self.wsl_distro:
            raise AdapterError("Keine WSL-Distribution gefunden oder konfiguriert.")
        
        # Bereinige den Distributionsnamen
        clean_distro = self.wsl_distro.replace('\x00', '').strip()
        wsl_command = f'wsl -d "{clean_distro}" {self.command}'
        
        process = await asyncio.create_subprocess_shell(
            wsl_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=prompt.encode('utf-8'))
        if process.returncode != 0:
            raise AdapterError(f"WSL command failed (Code {process.returncode}): {stderr.decode()}")
        return stdout.decode().strip()

class CLIAdapterPlugin(LLMAdapterPlugin):
    """Plugin-Definition für den CLI-Adapter."""
    
    @property
    def name(self) -> str:
        return "cli_adapter"
    
    @property
    def description(self) -> str:
        return "Adapter for command-line tools"
    
    @property
    def requires_api_key(self) -> bool:
        return False  # CLI-Tools benötigen normalerweise keine API-Schlüssel
    
    def create_adapter(self, model_config: Dict[str, Any] = None) -> UniversalAdapter:
        if not model_config:
            raise ValueError("CLI-Adapter benötigt eine Modellkonfiguration")
        return CLIToolAdapter(model_config)

    def is_available(self, model_config: Dict[str, Any] = None) -> bool:
        return True  # CLI-Tools gelten als immer verfügbar