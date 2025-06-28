from abc import ABC, abstractmethod

class BaseAdapter(ABC):
    """Abstract base class for all LLM adapters."""

    @abstractmethod
    async def send(self, prompt: str, **kwargs) -> str:
        """
        Sends a prompt to the LLM and returns the generated response.
        
        Args:
            prompt (str): The input prompt for the LLM.
            **kwargs: Additional parameters for the specific LLM API (e.g., max_tokens, temperature).
            
        Returns:
            str: The response from the LLM.
        """
        pass