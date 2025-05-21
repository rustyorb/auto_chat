import json
import logging
import requests
from typing import List, Dict, Any

log = logging.getLogger(__name__)
class APIClient:
    """Base class for LLM API clients."""

    def __init__(self, name: str):
        self.name = name

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from the LLM API."""
        raise NotImplementedError("Subclasses must implement this method")

    def get_available_models(self) -> List[str]:
        """Get list of available models from this provider."""
        raise NotImplementedError("Subclasses must implement this method")


class OllamaClient(APIClient):
    """Client for Ollama API."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        super().__init__("Ollama")
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.model = None

    def set_model(self, model_name: str):
        """Set the model to use for generation."""
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from Ollama API."""
        if not self.model:
            raise ValueError("Model must be set before generating responses")

        # Prepare the conversation format expected by Ollama
        messages = []

        # Add system message if provided
        if system:
            messages.append({"role": "system", "content": system})

        # Add conversation history
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the current prompt
        messages.append({"role": "user", "content": prompt})

        # Make API request
        try:
            response = requests.post(
                f"{self.api_url}/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]
        except requests.RequestException as e:
            log.error(f"Ollama API error: {str(e)}")
            return f"[Error generating response: {str(e)}]"

    def get_available_models(self) -> List[str]:
        """Get list of available models from Ollama."""
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
        """Set the model to use for generation."""
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from LM Studio API."""
        if not self.model:
            raise ValueError("Model must be set before generating responses")

        # Prepare the conversation format (OpenAI-compatible)
        messages = []

        # Add system message if provided
        if system:
            messages.append({"role": "system", "content": system})

        # Add conversation history
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the current prompt
        messages.append({"role": "user", "content": prompt})

        # Make API request
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            log.error(f"LM Studio API error: {str(e)}")
            return f"[Error generating response: {str(e)}]"

    def get_available_models(self) -> List[str]:
        """Get list of available models from LM Studio."""
        try:
            # Ensure the URL is properly formatted
            models_url = self.base_url
            if not models_url.endswith('/models'):
                if models_url.endswith('/'):
                    models_url += 'models'
                else:
                    models_url += '/models'
            
            log.info(f"Getting models from LM Studio at: {models_url}")
            response = requests.get(models_url, timeout=10)
            response.raise_for_status()
            models = response.json().get("data", [])
            return [model["id"] for model in models]
        except requests.RequestException as e:
            log.error(f"Failed to get LM Studio models: {str(e)}")
            return []


class OpenRouterClient(APIClient):
    def __init__(self, api_key):
        super().__init__("OpenRouter")
        self.base_url = "https://openrouter.ai/api/v1"
        self.api_key = api_key
        self.model = None
        self.update_headers()

    def update_headers(self):
        """Update headers with current API key."""
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def set_model(self, model_name: str):
        """Set the model to use for generation."""
        self.model = model_name

    def get_available_models(self) -> List[str]:
        """Get list of available models from OpenRouter."""
        if not self.api_key:
            log.error("OpenRouter API key not set")
            return []

        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return [model['id'] for model in data.get('data', [])]
        except Exception as e:
            log.error(f"Error fetching OpenRouter models: {str(e)}")
            return []

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from OpenRouter API."""
        if not self.api_key:
            raise ValueError("OpenRouter API key not set")
        if not self.model:
            raise ValueError("Model must be set before generating responses")

        try:
            messages = [
                {"role": "system", "content": system}
            ]
            
            # Convert conversation history to OpenAI format
            for msg in conversation_history:
                role = "assistant" if msg["role"] == "assistant" else "user"
                messages.append({"role": role, "content": msg["content"]})

            # Add the current prompt
            messages.append({"role": "user", "content": prompt})

            data = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            log.info(f"[OpenRouter] Sending request to {self.base_url}/chat/completions")
            log.info(f"[OpenRouter] Headers: {self.headers}")
            log.info(f"[OpenRouter] Payload: {json.dumps(data, indent=2)[:500]}...")

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            log.info(f"[OpenRouter] Response Status Code: {response.status_code}")
            log.info(f"[OpenRouter] Response Headers: {response.headers}")

            response.raise_for_status()
            
            result = response.json()
            log.info(f"[OpenRouter] Response Body (first 200 chars): {str(result)[:200]}...")
            
            return result['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            log.error(f"[OpenRouter] Request failed: {e}")
            log.error(f"[OpenRouter] Response content (if any): {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            log.error(f"[OpenRouter] Error processing response: {str(e)}")
            raise


class OpenAIClient(APIClient):
    def __init__(self, api_key):
        super().__init__("OpenAI")
        self.base_url = "https://api.openai.com/v1"
        self.api_key = api_key
        self.model = None
        self.update_headers()

    def update_headers(self):
        """Update headers with current API key."""
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def set_model(self, model_name: str):
        """Set the model to use for generation."""
        self.model = model_name

    def get_available_models(self) -> List[str]:
        """Get list of available models from OpenAI."""
        if not self.api_key:
            log.error("OpenAI API key not set")
            return []

        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            models = [model['id'] for model in data.get('data', []) if "gpt" in model['id']]
            return sorted(models)
        except Exception as e:
            log.error(f"Error fetching OpenAI models: {str(e)}")
            return []

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API key not set")
        if not self.model:
            raise ValueError("Model must be set before generating responses")

        try:
            messages = [
                {"role": "system", "content": system}
            ]
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
            log.info(f"[OpenAI] Sending request to {self.base_url}/chat/completions")
            log.info(f"[OpenAI] Headers: {self.headers}")
            log.info(f"[OpenAI] Payload: {json.dumps(data, indent=2)[:500]}...")
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=30
            )
            log.info(f"[OpenAI] Response Status Code: {response.status_code}")
            log.info(f"[OpenAI] Response Headers: {response.headers}")
            response.raise_for_status()
            result = response.json()
            log.info(f"[OpenAI] Response Body (first 200 chars): {str(result)[:200]}...")
            return result['choices'][0]['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            log.error(f"[OpenAI] Request failed: {e}")
            log.error(f"[OpenAI] Response content (if any): {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            log.error(f"[OpenAI] Error processing response: {str(e)}")
            raise
