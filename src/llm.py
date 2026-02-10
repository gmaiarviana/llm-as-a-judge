"""Abstração para provedores de LLM (Gemini, OpenAI, etc)."""

from abc import ABC, abstractmethod
import os


class LLMProvider(ABC):
    """Interface base para provedores de LLM."""
    
    @abstractmethod
    def call(self, system_prompt: str, user_prompt: str) -> dict | None:
        """
        Faz uma chamada ao LLM.
        
        Args:
            system_prompt: Instrução do sistema
            user_prompt: Prompt do usuário
            
        Returns:
            dict com resultado estruturado ou None se erro
        """
        pass


class GeminiProvider(LLMProvider):
    """Provedor Google Gemini."""
    
    def __init__(self):
        import requests
        from config import API_URL
        self.API_URL = API_URL
        self.requests = requests
    
    def call(self, system_prompt: str, user_prompt: str) -> dict | None:
        """Chamada à API Gemini."""
        import json
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": system_prompt + "\n\n" + user_prompt}],
                }
            ]
        }
        
        try:
            response = self.requests.post(self.API_URL, json=payload, timeout=30)
            response.raise_for_status()
        except self.requests.exceptions.RequestException as e:
            print(f"API error: {e}")
            return None
        
        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
            return result
        except (KeyError, json.JSONDecodeError, IndexError) as e:
            print(f"Parse error: {e}")
            return None


class OpenAIProvider(LLMProvider):
    """Provedor OpenAI."""
    
    def __init__(self):
        import os
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY não configurada")
    
    def call(self, system_prompt: str, user_prompt: str) -> dict | None:
        """Chamada à API OpenAI."""
        import json
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"API error: {e}")
            return None
        
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            result = json.loads(text)
            return result
        except (KeyError, json.JSONDecodeError, IndexError) as e:
            print(f"Parse error: {e}")
            return None


def get_provider() -> LLMProvider:
    """Factory: retorna o provedor configurado."""
    provider_name = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if provider_name == "gemini":
        return GeminiProvider()
    elif provider_name == "openai":
        return OpenAIProvider()
    else:
        raise ValueError(f"Provedor desconhecido: {provider_name}")
