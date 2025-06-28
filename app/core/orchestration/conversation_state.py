# llm_bridge/orchestration/conversation_state.py
import asyncio
from enum import Enum, auto
from ..utils.task_manager import create_background_task

class State(Enum):
    IDLE = auto()
    AWAITING_RESPONSE = auto()
    RESPONSE_RECEIVED = auto()
    CONVERSATION_ENDED = auto()
    ERROR = auto()

class ConversationStateMachine:
    def __init__(self, conversation_id: str):
        self.id = conversation_id
        self.current_state = State.IDLE
        # Die Kette der LLMs, die an der Konversation teilgenommen haben.
        self.participants_chain = []
        print(f"  State Machine for conversation '{self.id}' created, initial state: IDLE.")

    def transition_to(self, target_llm_name: str, event_store, allow_repeats: bool = False) -> bool:
        if self.current_state in [State.CONVERSATION_ENDED, State.ERROR]:
            error_msg = f"Conversation '{self.id}' is already ended or in an error state."
            if event_store:
                create_background_task(
                    event_store.log_event("ERROR", "ConversationStateMachine", error_msg, conversation_id=self.id),
                    name=f"log-error-{self.id}"
                )
            raise Exception(f"Invalid state transition: {error_msg}")
            
        # ROBUSTERE LOOP-ERKENNUNG (deaktiviert für Mission Control)
        is_mission_control = self.id.startswith('mission_')
        
        if not allow_repeats and not is_mission_control:
            # Regel 1: Verhindert direkte Wiederholungen (A -> A)
            if len(self.participants_chain) > 0 and target_llm_name == self.participants_chain[-1]:
                error_msg = f"Direct repetition loop to '{target_llm_name}' is not allowed."
                if event_store:
                    asyncio.create_task(event_store.log_event("ERROR", "ConversationStateMachine", error_msg, conversation_id=self.id))
                self.current_state = State.ERROR
                raise Exception(f"Invalid state transition: {error_msg}")
            
            # Regel 2: Verhindert den Ping-Pong-Loop (A -> B -> A)
            if len(self.participants_chain) > 1 and target_llm_name == self.participants_chain[-2]:
                error_msg = f"Ping-pong loop back to '{target_llm_name}' is not allowed."
                if event_store:
                    asyncio.create_task(event_store.log_event("ERROR", "ConversationStateMachine", error_msg, conversation_id=self.id))
                self.current_state = State.ERROR
                raise Exception(f"Invalid state transition: {error_msg}")
            
        if event_store:
            create_background_task(
                event_store.log_event("INFO", "ConversationStateMachine", 
                                    f"State transition: {self.current_state.name} -> AWAITING_RESPONSE (target: {target_llm_name})", 
                                    conversation_id=self.id),
                name=f"log-transition-{self.id}"
            )
        self.current_state = State.AWAITING_RESPONSE
        self.participants_chain.append(target_llm_name)
        return True

    def record_response(self, from_llm_name: str, event_store):
        if self.current_state == State.AWAITING_RESPONSE and self.participants_chain and self.participants_chain[-1] == from_llm_name:
            if event_store:
                create_background_task(
                    event_store.log_event("INFO", "ConversationStateMachine", 
                                        f"State transition: AWAITING_RESPONSE -> RESPONSE_RECEIVED (from: {from_llm_name})", 
                                        conversation_id=self.id),
                    name=f"log-response-{self.id}"
                )
            self.current_state = State.RESPONSE_RECEIVED
        
    def end_conversation(self):
        self.current_state = State.CONVERSATION_ENDED