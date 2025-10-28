import json
import logging
import requests
import time
import functools
from typing import List, Dict, Any, Optional, Callable, Iterator, Union

from config import (
    DEFAULT_TIMEOUT,
    MODEL_LIST_TIMEOUT,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    OLLAMA_DEFAULT_URL,
    LMSTUDIO_DEFAULT_URL,
    OPENROUTER_API_URL,
    OPENAI_API_URL,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_MAX_DELAY
)
from exceptions import (
    APIKeyMissingError,
    ModelNotSetError,
    APIRequestError
)

log = logging.getLogger(__name__)


def retry_with_backoff(max_retries: int = MAX_RETRIES,
                       backoff_base: float = RETRY_BACKOFF_BASE,
                       backoff_multiplier: float = RETRY_BACKOFF_MULTIPLIER,
                       max_delay: float = RETRY_MAX_DELAY) -> Callable:
    """
    Decorator for retrying API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        backoff_base: Initial delay between retries in seconds
        backoff_multiplier: Multiplier for exponential backoff
        max_delay: Maximum delay between retries

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    if attempt < max_retries:
                        # Calculate delay with exponential backoff
                        delay = min(backoff_base * (backoff_multiplier ** attempt), max_delay)
                        log.warning(
                            f"Connection error on attempt {attempt + 1}/{max_retries + 1}. "
                            f"Retrying in {delay:.1f}s... Error: {str(e)}"
                        )
                        time.sleep(delay)
                    else:
                        log.error(f"All {max_retries + 1} attempts failed. Last error: {str(e)}")
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(backoff_base * (backoff_multiplier ** attempt), max_delay)
                        log.warning(
                            f"Timeout on attempt {attempt + 1}/{max_retries + 1}. "
                            f"Retrying in {delay:.1f}s... Error: {str(e)}"
                        )
                        time.sleep(delay)
                    else:
                        log.error(f"All {max_retries + 1} attempts failed. Last error: {str(e)}")
                except requests.exceptions.RequestException as e:
                    # For other request exceptions, check if it's retryable
                    if hasattr(e, 'response') and e.response is not None:
                        # Don't retry on 4xx errors (client errors)
                        if 400 <= e.response.status_code < 500:
                            raise
                        # Retry on 5xx errors (server errors)
                        if 500 <= e.response.status_code < 600:
                            last_exception = e
                            if attempt < max_retries:
                                delay = min(backoff_base * (backoff_multiplier ** attempt), max_delay)
                                log.warning(
                                    f"Server error ({e.response.status_code}) on attempt {attempt + 1}/{max_retries + 1}. "
                                    f"Retrying in {delay:.1f}s..."
                                )
                                time.sleep(delay)
                            else:
                                log.error(f"All {max_retries + 1} attempts failed. Last error: {str(e)}")
                        else:
                            raise
                    else:
                        raise
                except (APIKeyMissingError, ModelNotSetError):
                    # Don't retry on configuration errors
                    raise

            # If we get here, all retries failed
            if last_exception:
                if isinstance(last_exception, requests.RequestException):
                    raise APIRequestError(
                        f"Request failed after {max_retries + 1} attempts: {str(last_exception)}"
                    )
                raise last_exception

        return wrapper
    return decorator


class APIClient:
    """Base class for LLM API clients."""

    def __init__(self, name: str):
        self.name = name
        self.model: Optional[str] = None

    def set_model(self, model_name: str) -> None:
        """Set the model to use for generation."""
        self.model = model_name

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from the LLM API."""
        raise NotImplementedError("Subclasses must implement this method")

    @retry_with_backoff()
    @retry_with_backoff()
    @retry_with_backoff()
    def generate_streaming_response(
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]]
    ) -> Iterator[str]:
        """Generate a streaming response from the LLM API."""
        raise NotImplementedError("Subclasses must implement this method")

    def get_available_models(self) -> List[str]:
        """Get list of available models from this provider."""
        raise NotImplementedError("Subclasses must implement this method")

    def _build_messages(self, prompt: str, system: str,
                       conversation_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Build message list from prompt, system message, and history.

        Args:
            prompt: The current prompt to send
            system: System message/instructions
            conversation_history: Previous conversation messages

        Returns:
            List of message dictionaries
        """
        messages = []

        # Add system message if provided
        if system:
            messages.append({"role": "system", "content": system})

        # Add conversation history
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the current prompt
        messages.append({"role": "user", "content": prompt})

        return messages


class OllamaClient(APIClient):
    """Client for Ollama API."""

    def __init__(self, base_url: str = OLLAMA_DEFAULT_URL):
        super().__init__("Ollama")
        self.base_url = base_url
        self.api_url = f"{base_url}/api"

    @retry_with_backoff()
    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from Ollama API.

        Args:
            prompt: The user prompt
            system: System message
            conversation_history: Previous conversation messages

        Returns:
            Generated response text

        Raises:
            ModelNotSetError: If model is not set
            APIRequestError: If the API request fails
        """
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        messages = self._build_messages(prompt, system, conversation_history)

        try:
            response = requests.post(
                f"{self.api_url}/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]
        except requests.HTTPError as e:
            log.error(f"Ollama API HTTP error: {str(e)}")
            raise APIRequestError(
                f"Ollama API request failed: {str(e)}",
                status_code=e.response.status_code if e.response else None,
                response_text=e.response.text if e.response else None
            )
        except requests.RequestException as e:
            log.error(f"Ollama API request error: {str(e)}")
            raise APIRequestError(f"Ollama API request failed: {str(e)}")

    def generate_streaming_response(
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]]
    ) -> Iterator[str]:
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        messages = self._build_messages(prompt, system, conversation_history)

        try:
            response = requests.post(
                f"{self.api_url}/chat",
                json={"model": self.model, "messages": messages, "stream": True},
                stream=True,
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if "content" in chunk["message"]:
                        yield chunk["message"]["content"]
                    if chunk.get("done"):
                        break
        except requests.HTTPError as e:
            log.error(f"Ollama API HTTP error: {str(e)}")
            raise APIRequestError(
                f"Ollama API request failed: {str(e)}",
                status_code=e.response.status_code if e.response else None,
                response_text=e.response.text if e.response else None,
            )
        except requests.RequestException as e:
            log.error(f"Ollama API request error: {str(e)}")
            raise APIRequestError(f"Ollama API request failed: {str(e)}")
        except json.JSONDecodeError as e:
            log.error(f"Ollama API JSON decoding error: {str(e)}")
            raise APIRequestError(f"Ollama API returned invalid JSON: {str(e)}")

    def get_available_models(self) -> List[str]:
        """Get list of available models from Ollama.

        Returns:
            List of model names
        """
        try:
            response = requests.get(f"{self.api_url}/tags", timeout=MODEL_LIST_TIMEOUT)
            response.raise_for_status()
            models = response.json().get("models", [])
            return [model["name"] for model in models]
        except requests.RequestException as e:
            log.error(f"Failed to get Ollama models: {str(e)}")
            return []


class LMStudioClient(APIClient):
    """Client for LM Studio API (OpenAI-compatible)."""

    def __init__(self, base_url: str = LMSTUDIO_DEFAULT_URL):
        super().__init__("LM Studio")
        self.base_url = base_url

    @retry_with_backoff()
    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from LM Studio API.

        Args:
            prompt: The user prompt
            system: System message
            conversation_history: Previous conversation messages

        Returns:
            Generated response text

        Raises:
            ModelNotSetError: If model is not set
            APIRequestError: If the API request fails
        """
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        messages = self._build_messages(prompt, system, conversation_history)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.HTTPError as e:
            log.error(f"LM Studio API HTTP error: {str(e)}")
            raise APIRequestError(
                f"LM Studio API request failed: {str(e)}",
                status_code=e.response.status_code if e.response else None,
                response_text=e.response.text if e.response else None
            )
        except requests.RequestException as e:
            log.error(f"LM Studio API request error: {str(e)}")
            raise APIRequestError(f"LM Studio API request failed: {str(e)}")

    def generate_streaming_response(
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]]
    ) -> Iterator[str]:
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        messages = self._build_messages(prompt, system, conversation_history)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={"model": self.model, "messages": messages, "stream": True},
                stream=True,
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    if line_str == "[DONE]":
                        break
                    if not line_str:
                        continue
                    try:
                        chunk = json.loads(line_str)
                        if (
                            "choices" in chunk
                            and chunk["choices"]
                            and "delta" in chunk["choices"][0]
                            and "content" in chunk["choices"][0]["delta"]
                        ):
                            content = chunk["choices"][0]["delta"]["content"]
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        log.warning(f"Failed to decode stream line: {line_str}")
                        continue
        except requests.HTTPError as e:
            log.error(f"LM Studio API HTTP error: {str(e)}")
            raise APIRequestError(
                f"LM Studio API request failed: {str(e)}",
                status_code=e.response.status_code if e.response else None,
                response_text=e.response.text if e.response else None,
            )
        except requests.RequestException as e:
            log.error(f"LM Studio API request error: {str(e)}")
            raise APIRequestError(f"LM Studio API request failed: {str(e)}")

    def get_available_models(self) -> List[str]:
        """Get list of available models from LM Studio.

        Returns:
            List of model names
        """
        try:
            # Ensure the URL is properly formatted
            models_url = self.base_url
            if not models_url.endswith('/models'):
                if models_url.endswith('/'):
                    models_url += 'models'
                else:
                    models_url += '/models'

            log.info(f"Getting models from LM Studio at: {models_url}")
            response = requests.get(models_url, timeout=MODEL_LIST_TIMEOUT)
            response.raise_for_status()
            models = response.json().get("data", [])
            return [model["id"] for model in models]
        except requests.RequestException as e:
            log.error(f"Failed to get LM Studio models: {str(e)}")
            return []


class OpenAICompatibleClient(APIClient):
    """Base class for OpenAI-compatible API clients (OpenRouter, OpenAI, etc.)."""

    def __init__(self, name: str, base_url: str, api_key: str):
        super().__init__(name)
        self.base_url = base_url
        self.api_key = api_key
        self.headers: Dict[str, str] = {}
        self.update_headers()

    def update_headers(self) -> None:
        """Update headers with current API key."""
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    @retry_with_backoff()
    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from OpenAI-compatible API.

        Args:
            prompt: The user prompt
            system: System message
            conversation_history: Previous conversation messages

        Returns:
            Generated response text

        Raises:
            APIKeyMissingError: If API key is not set
            ModelNotSetError: If model is not set
            APIRequestError: If the API request fails
        """
        if not self.api_key:
            raise APIKeyMissingError(f"{self.name} API key not set")
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        try:
            messages = self._build_messages(prompt, system, conversation_history)

            data = {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
                "max_tokens": DEFAULT_MAX_TOKENS
            }

            log.info(f"[{self.name}] Sending request to {self.base_url}/chat/completions")
            log.debug(f"[{self.name}] Payload: {json.dumps(data, indent=2)[:500]}...")

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                timeout=DEFAULT_TIMEOUT
            )

            log.info(f"[{self.name}] Response Status Code: {response.status_code}")
            response.raise_for_status()

            result = response.json()
            log.debug(f"[{self.name}] Response Body (first 200 chars): {str(result)[:200]}...")

            return result['choices'][0]['message']['content'].strip()
        except requests.HTTPError as e:
            log.error(f"[{self.name}] HTTP error: {e}")
            error_msg = f"{self.name} API request failed"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f": {e.response.text}"
                raise APIRequestError(
                    error_msg,
                    status_code=e.response.status_code,
                    response_text=e.response.text
                )
            raise APIRequestError(error_msg)
        except requests.RequestException as e:
            log.error(f"[{self.name}] Request error: {e}")
            raise APIRequestError(f"{self.name} API request failed: {str(e)}")
        except (KeyError, IndexError) as e:
            log.error(f"[{self.name}] Error parsing response: {str(e)}")
            raise APIRequestError(f"{self.name} API returned unexpected response format")

    def generate_streaming_response(
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]]
    ) -> Iterator[str]:
        if not self.api_key:
            raise APIKeyMissingError(f"{self.name} API key not set")
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        messages = self._build_messages(prompt, system, conversation_history)
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "stream": True,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data,
                stream=True,
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    if line_str == "[DONE]":
                        break
                    if not line_str:
                        continue
                    try:
                        chunk = json.loads(line_str)
                        if (
                            "choices" in chunk
                            and chunk["choices"]
                            and "delta" in chunk["choices"][0]
                            and "content" in chunk["choices"][0]["delta"]
                        ):
                            content = chunk["choices"][0]["delta"]["content"]
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        log.warning(f"Failed to decode stream line: {line_str}")
                        continue
        except requests.HTTPError as e:
            log.error(f"[{self.name}] HTTP error: {e}")
            raise APIRequestError(
                f"{self.name} API request failed: {e.response.text}",
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
        except requests.RequestException as e:
            log.error(f"[{self.name}] Request error: {e}")
            raise APIRequestError(f"{self.name} API request failed: {str(e)}")

    def get_available_models(self) -> List[str]:
        """Get list of available models.

        Returns:
            List of model names
        """
        if not self.api_key:
            log.error(f"{self.name} API key not set")
            return []

        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self.headers,
                timeout=MODEL_LIST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            return [model['id'] for model in data.get('data', [])]
        except Exception as e:
            log.error(f"Error fetching {self.name} models: {str(e)}")
            return []


class OpenRouterClient(OpenAICompatibleClient):
    """Client for OpenRouter API."""

    def __init__(self, api_key: str = ""):
        super().__init__("OpenRouter", OPENROUTER_API_URL, api_key)


class OpenAIClient(OpenAICompatibleClient):
    """Client for OpenAI API."""

    def __init__(self, api_key: str = ""):
        super().__init__("OpenAI", OPENAI_API_URL, api_key)

    def get_available_models(self) -> List[str]:
        """Get list of available GPT models from OpenAI.

        Returns:
            List of model names filtered to GPT models
        """
        models = super().get_available_models()
        # Filter to only GPT models and sort
        gpt_models = [model for model in models if "gpt" in model.lower()]
        return sorted(gpt_models)
