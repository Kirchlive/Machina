# llm_bridge/orchestration/workflow_engine.py
"""
Workflow Engine
===============

Orchestriert komplexe, mehrstufige LLM-Workflows basierend auf konfigurierbaren Definitionen.
Unterstützt Platzhalter-Substitution und Pipeline-Verarbeitung.
"""

import uuid
import re
from typing import Dict, Any, List
from datetime import datetime


class WorkflowOrchestrator:
    """
    Orchestriert die Ausführung von mehrstufigen LLM-Workflows.
    
    Ein Workflow besteht aus mehreren Schritten, die sequenziell ausgeführt werden.
    Jeder Schritt kann auf die Ausgaben vorheriger Schritte zugreifen.
    """
    
    def __init__(self, bridge_core):
        """
        Initialisiert den Workflow-Orchestrator.
        
        Args:
            bridge_core: Die LLMBridgeCore-Instanz für LLM-Aufrufe
        """
        self.bridge = bridge_core
        self.active_workflows = {}
    
    async def execute_workflow(self, workflow_definition: Dict[str, Any], workflow_id: str = None) -> Dict[str, Any]:
        """
        Führt einen definierten Workflow aus.
        
        Args:
            workflow_definition: Die Workflow-Definition mit steps
            workflow_id: Optionale eindeutige ID für den Workflow
            
        Returns:
            Dict mit Ausführungsergebnissen und Metadaten
        """
        if not workflow_id:
            workflow_id = f"wf_{uuid.uuid4().hex[:8]}"
        
        workflow_name = workflow_definition.get('name', 'Unnamed Workflow')
        steps = workflow_definition.get('steps', [])
        
        # Workflow-Kontext initialisieren
        context = {
            'workflow_id': workflow_id,
            'workflow_name': workflow_name,
            'start_time': datetime.now(),
            'outputs': {},
            'step_results': [],
            'total_steps': len(steps)
        }
        
        self.active_workflows[workflow_id] = context
        
        print(f"🚀 Starte Workflow '{workflow_name}' (ID: {workflow_id}) mit {len(steps)} Schritten")
        
        try:
            # Jeden Schritt sequenziell ausführen
            for step_index, step in enumerate(steps, 1):
                step_result = await self._execute_step(context, step, step_index)
                context['step_results'].append(step_result)
                
                # Bei Fehlern abbrechen
                if not step_result['success']:
                    break
            
            # Workflow abschließen
            context['end_time'] = datetime.now()
            context['duration'] = (context['end_time'] - context['start_time']).total_seconds()
            context['success'] = all(step['success'] for step in context['step_results'])
            
            if context['success']:
                print(f"✅ Workflow '{workflow_name}' erfolgreich abgeschlossen ({context['duration']:.2f}s)")
            else:
                print(f"❌ Workflow '{workflow_name}' fehlgeschlagen ({context['duration']:.2f}s)")
            
            return self._create_result_summary(context)
            
        except Exception as e:
            print(f"💥 Kritischer Fehler in Workflow '{workflow_name}': {e}")
            context['error'] = str(e)
            context['success'] = False
            return self._create_result_summary(context)
        
        finally:
            # Workflow aus der aktiven Liste entfernen
            if workflow_id in self.active_workflows:
                del self.active_workflows[workflow_id]
    
    async def _execute_step(self, context: Dict[str, Any], step: Dict[str, Any], step_number: int) -> Dict[str, Any]:
        """
        Führt einen einzelnen Workflow-Schritt aus.
        
        Args:
            context: Workflow-Kontext
            step: Schritt-Definition
            step_number: Schritt-Nummer (1-basiert)
            
        Returns:
            Dict mit Schritt-Ergebnis
        """
        step_id = step.get('id', f'step_{step_number}')
        model = step.get('model', 'claude35_sonnet')
        prompt_template = step.get('prompt', '')
        
        step_start = datetime.now()
        
        print(f"  🔄 Schritt {step_number}/{context['total_steps']}: '{step_id}' mit Modell '{model}'")
        
        try:
            # Prompt-Platzhalter ersetzen
            processed_prompt = self._substitute_placeholders(prompt_template, context['outputs'])
            
            # LLM-Aufruf über die Bridge
            conversation_id = f"{context['workflow_id']}_step_{step_number}"
            response = await self.bridge.bridge_message(
                conversation_id=conversation_id,
                target_llm_name=model,
                message=processed_prompt
            )
            
            # Antwort in den Kontext einfügen
            context['outputs'][step_id] = response
            
            step_duration = (datetime.now() - step_start).total_seconds()
            
            print(f"    ✅ Schritt '{step_id}' abgeschlossen ({step_duration:.2f}s)")
            print(f"    📝 Antwort: {response[:100]}{'...' if len(response) > 100 else ''}")
            
            return {
                'step_id': step_id,
                'step_number': step_number,
                'model': model,
                'success': True,
                'response': response,
                'duration': step_duration,
                'prompt_length': len(processed_prompt),
                'response_length': len(response)
            }
            
        except Exception as e:
            step_duration = (datetime.now() - step_start).total_seconds()
            error_msg = str(e)
            
            print(f"    ❌ Schritt '{step_id}' fehlgeschlagen: {error_msg}")
            
            return {
                'step_id': step_id,
                'step_number': step_number,
                'model': model,
                'success': False,
                'error': error_msg,
                'duration': step_duration
            }
    
    def _substitute_placeholders(self, template: str, outputs: Dict[str, str]) -> str:
        """
        Ersetzt Platzhalter im Format {{ outputs.step_id }} durch tatsächliche Werte.
        
        Args:
            template: Template-String mit Platzhaltern
            outputs: Dictionary mit verfügbaren Ausgaben
            
        Returns:
            String mit ersetzten Platzhaltern
        """
        def replace_placeholder(match):
            placeholder = match.group(1)
            if placeholder.startswith('outputs.'):
                output_key = placeholder[8:]  # Entferne "outputs."
                return outputs.get(output_key, f"[MISSING: {output_key}]")
            return match.group(0)
        
        # Finde alle Platzhalter im Format {{ ... }}
        pattern = r'\{\{\s*([^}]+)\s*\}\}'
        return re.sub(pattern, replace_placeholder, template)
    
    def _create_result_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Erstellt eine Zusammenfassung der Workflow-Ausführung.
        
        Args:
            context: Workflow-Kontext
            
        Returns:
            Zusammenfassung als Dictionary
        """
        return {
            'workflow_id': context['workflow_id'],
            'workflow_name': context['workflow_name'],
            'success': context.get('success', False),
            'duration': context.get('duration', 0),
            'total_steps': context['total_steps'],
            'completed_steps': len([s for s in context['step_results'] if s['success']]),
            'failed_steps': len([s for s in context['step_results'] if not s['success']]),
            'outputs': context['outputs'],
            'step_details': context['step_results'],
            'error': context.get('error'),
            'timestamp': context['start_time'].isoformat()
        }
    
    def get_active_workflows(self) -> Dict[str, Dict[str, Any]]:
        """
        Gibt Informationen über aktuell laufende Workflows zurück.
        
        Returns:
            Dictionary mit aktiven Workflows
        """
        return {
            wf_id: {
                'workflow_name': context['workflow_name'],
                'start_time': context['start_time'].isoformat(),
                'completed_steps': len(context['step_results']),
                'total_steps': context['total_steps']
            }
            for wf_id, context in self.active_workflows.items()
        }


# Workflow-Definition Validierung
class WorkflowValidator:
    """Validiert Workflow-Definitionen vor der Ausführung."""
    
    @staticmethod
    def validate_workflow(workflow_def: Dict[str, Any]) -> List[str]:
        """
        Validiert eine Workflow-Definition.
        
        Args:
            workflow_def: Workflow-Definition
            
        Returns:
            Liste mit Fehlermeldungen (leer wenn gültig)
        """
        errors = []
        
        if not isinstance(workflow_def, dict):
            return ["Workflow-Definition muss ein Dictionary sein"]
        
        # Grundlegende Felder prüfen
        if 'steps' not in workflow_def:
            errors.append("Workflow muss 'steps' enthalten")
            return errors
        
        steps = workflow_def['steps']
        if not isinstance(steps, list) or len(steps) == 0:
            errors.append("'steps' muss eine nicht-leere Liste sein")
            return errors
        
        # Jeden Schritt validieren
        step_ids = set()
        for i, step in enumerate(steps):
            step_errors = WorkflowValidator._validate_step(step, i + 1, step_ids)
            errors.extend(step_errors)
        
        return errors
    
    @staticmethod
    def _validate_step(step: Dict[str, Any], step_number: int, existing_ids: set) -> List[str]:
        """Validiert einen einzelnen Workflow-Schritt."""
        errors = []
        
        if not isinstance(step, dict):
            errors.append(f"Schritt {step_number}: Muss ein Dictionary sein")
            return errors
        
        # ID prüfen
        step_id = step.get('id')
        if not step_id:
            errors.append(f"Schritt {step_number}: Feld 'id' ist erforderlich")
        elif step_id in existing_ids:
            errors.append(f"Schritt {step_number}: ID '{step_id}' ist bereits vergeben")
        else:
            existing_ids.add(step_id)
        
        # Model prüfen
        if 'model' not in step:
            errors.append(f"Schritt {step_number}: Feld 'model' ist erforderlich")
        
        # Prompt prüfen
        if 'prompt' not in step:
            errors.append(f"Schritt {step_number}: Feld 'prompt' ist erforderlich")
        elif not isinstance(step['prompt'], str):
            errors.append(f"Schritt {step_number}: 'prompt' muss ein String sein")
        
        return errors