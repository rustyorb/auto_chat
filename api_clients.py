import json
import logging
from typing import List, Dict
import requests

log = logging.getLogger(__name__)

class APIClient:
    """Base class for LLM API clients."""

    def __init__(self, name: str):
        self.name = name

    def generate_response(self, prompt: str, system: str,
                          conversation_history: List[Dict[str, str]]) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def get_available_models(self) -> List[str]:
        raise NotImplementedError("Subclasses must implement this method")

class OllamaClient(APIClient):
    """Client for Ollama API."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        super().__init__("Ollama")
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.model = None

    def set_model(self, model_name: str):
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                          conversation_history: List[Dict[str, str]]) -> str:
        if not self.model:
            raise ValueError("Model must be set before generating responses")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                f"{self.api_url}/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]
        except requests.RequestException as e:
            log.error(f"Ollama API error: {str(e)}")
            return f"[Error generating response: {str(e)}]"

    def get_available_models(self) -> List[str]:
        try:
            response = requests.get(f"{self.api_url}/tags", timeout=10)
            response.raise_for_status()
            models = response.json().get("models", [])
            return [model["name"] for model in models]
        except requests.RequestException as e:
            log.error(f"Failed to get Ollama models: {str(e)}")
            return []

class LMStudioClient(APIClient):
    """Client for LM Studio API."""

    def __init__(self, base_url: str = "http://192.168.0.177:6969/v1"):
        super().__init__("LM Studio")
        self.base_url = base_url
        self.model = None

    def set_model(self, model_name: str):
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                          conversation_history: List[Dict[str, str]]) -> str:
        if not self.model:
            raise ValueError("Model must be set before generating responses")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            log.error(f"LM Studio API error: {str(e)}")
            return f"[Error generating response: {str(e)}]"

    def get_available_models(self) -> List[str]:
        try:
            models_url = self.base_url
            if not models_url.endswith('/models'):
                models_url = models_url.rstrip('/') + '/models'
            log.info(f"Getting models from LM Studio at: {models_url}")
            response = requests.get(models_url, timeout=10)
            response.raise_for_status()
            models = response.json().get("data", [])
            return [model["id"] for model in models]
        except requests.RequestException as e:
            log.error(f"Failed to get LM Studio models: {str(e)}")
            return []

class OpenRouterClient(APIClient):
    """Client for OpenRouter API."""

    def __init__(self, api_key=""):
        super().__init__("OpenRouter")
        self.base_url = "https://openrouter.ai/api/v1"
        self.api_key = api_key
        self.model = None
        self.update_headers()

    def update_headers(self):
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def set_model(self, model_name: str):
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                          conversation_history: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError("OpenRouter API key not set")
        if not self.model:
            raise ValueError("Model must be set before generating responses")
        messages = [{"role": "system", "content": system}]
        for msg in conversation_history:
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            log.error(f"[OpenRouter] Request failed: {e}")
            raise
        except Exception as e:
            log.error(f"[OpenRouter] Error processing response: {str(e)}")
            raise

    def get_available_models(self) -> List[str]:
        if not self.api_key:
            log.error("OpenRouter API key not set")
            return []
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return [model['id'] for model in data.get('data', [])]
        except Exception as e:
            log.error(f"Error fetching OpenRouter models: {str(e)}")
            return []

class OpenAIClient(APIClient):
    """Client for OpenAI API."""

    def __init__(self, api_key=""):
        super().__init__("OpenAI")
        self.base_url = "https://api.openai.com/v1"
        self.api_key = api_key
        self.model = None
        self.update_headers()

    def update_headers(self):
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def set_model(self, model_name: str):
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                          conversation_history: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API key not set")
        if not self.model:
            raise ValueError("Model must be set before generating responses")
        messages = [{"role": "system", "content": system}]
        for msg in conversation_history:
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            log.error(f"[OpenAI] Request failed: {e}")
            raise
        except Exception as e:
            log.error(f"[OpenAI] Error processing response: {str(e)}")
            raise

    def get_available_models(self) -> List[str]:
        if not self.api_key:
            log.error("OpenAI API key not set")
            return []
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            models = [model['id'] for model in data.get('data', []) if "gpt" in model['id']]
            return sorted(models)
        except Exception as e:
            log.error(f"Error fetching OpenAI models: {str(e)}")
            return []

