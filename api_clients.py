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
    DEFAULT_FREQUENCY_PENALTY,
    DEFAULT_PRESENCE_PENALTY,
    OLLAMA_REPEAT_PENALTY,
    OLLAMA_DEFAULT_URL,
    LMSTUDIO_DEFAULT_URL,
    OPENROUTER_API_URL,
    OPENAI_API_URL,
    VENICE_API_URL,
    XAI_API_URL,
    ANTHROPIC_API_URL,
    ANTHROPIC_VERSION,
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
        # Optional sampling overrides; None = provider default
        self.temperature: Optional[float] = None
        self.max_tokens: Optional[int] = None
        # Reasoning ("thinking") text captured from the last call, for models
        # that report it separately from the reply content.
        self.last_reasoning: str = ""
        self.last_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

    def set_model(self, model_name: str) -> None:
        """Set the model to use for generation."""
        self.model = model_name

    def get_last_usage(self) -> Dict[str, int]:
        """Get token usage from the last API call."""
        return self.last_usage.copy()

    def _reset_usage(self) -> None:
        """Zero out usage before a call so responses without usage data never
        inherit the previous call's token counts."""
        self.last_reasoning = ""
        self.last_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

    def _sampling_params(self) -> Dict[str, Any]:
        """Optional temperature/max_tokens for OpenAI-style payloads."""
        params: Dict[str, Any] = {}
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        return params

    def _anti_repeat_params(self) -> Dict[str, Any]:
        """Mild frequency/presence penalties for OpenAI-style endpoints to
        curb the repetition loops common in AI-vs-AI chats. Unsupported
        endpoints ignore unknown fields."""
        return {
            "frequency_penalty": DEFAULT_FREQUENCY_PENALTY,
            "presence_penalty": DEFAULT_PRESENCE_PENALTY,
        }

    def generate_response(self, prompt: str, system: str,
                         conversation_history: List[Dict[str, str]]) -> str:
        """Generate a response from the LLM API."""
        raise NotImplementedError("Subclasses must implement this method")

    def generate_streaming_response(
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]],
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> Iterator[str]:
        """Generate a streaming response from the LLM API.

        on_reasoning, when given, receives incremental reasoning ("thinking")
        text for models that stream it separately from the reply.
        """
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

        self._reset_usage()
        messages = self._build_messages(prompt, system, conversation_history)

        try:
            payload = {"model": self.model, "messages": messages, "stream": False}
            options = {"repeat_penalty": OLLAMA_REPEAT_PENALTY}
            if self.temperature is not None:
                options["temperature"] = self.temperature
            if self.max_tokens is not None:
                options["num_predict"] = self.max_tokens
            payload["options"] = options
            response = requests.post(
                f"{self.api_url}/chat",
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()

            # Extract token usage if available
            if "prompt_eval_count" in result and "eval_count" in result:
                self.last_usage = {
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                }

            self.last_reasoning = result.get("message", {}).get("thinking", "") or ""
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
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]],
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> Iterator[str]:
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        self._reset_usage()
        messages = self._build_messages(prompt, system, conversation_history)

        try:
            payload = {"model": self.model, "messages": messages, "stream": True}
            options = {"repeat_penalty": OLLAMA_REPEAT_PENALTY}
            if self.temperature is not None:
                options["temperature"] = self.temperature
            if self.max_tokens is not None:
                options["num_predict"] = self.max_tokens
            payload["options"] = options
            response = requests.post(
                f"{self.api_url}/chat",
                json=payload,
                stream=True,
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    thinking = chunk.get("message", {}).get("thinking")
                    if thinking:
                        self.last_reasoning += thinking
                        if on_reasoning:
                            on_reasoning(thinking)
                    if "content" in chunk.get("message", {}):
                        yield chunk["message"]["content"]
                    if chunk.get("done"):
                        # Ollama reports token counts on the final chunk
                        if "prompt_eval_count" in chunk or "eval_count" in chunk:
                            self.last_usage = {
                                "input_tokens": chunk.get("prompt_eval_count", 0),
                                "output_tokens": chunk.get("eval_count", 0),
                                "total_tokens": chunk.get("prompt_eval_count", 0) + chunk.get("eval_count", 0),
                            }
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

        self._reset_usage()
        messages = self._build_messages(prompt, system, conversation_history)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    **self._anti_repeat_params(),
                    **self._sampling_params(),
                },
                timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()

            # Extract token usage if available
            if "usage" in result:
                usage = result["usage"]
                self.last_usage = {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }

            message = result["choices"][0]["message"]
            self.last_reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
            return message["content"]
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
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]],
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> Iterator[str]:
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        self._reset_usage()
        messages = self._build_messages(prompt, system, conversation_history)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={"model": self.model, "messages": messages, "stream": True,
                      **self._anti_repeat_params(), **self._sampling_params()},
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
                        if "usage" in chunk and chunk["usage"]:
                            usage = chunk["usage"]
                            self.last_usage = {
                                "input_tokens": usage.get("prompt_tokens", 0),
                                "output_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                            if reasoning:
                                self.last_reasoning += reasoning
                                if on_reasoning:
                                    on_reasoning(reasoning)
                            content = delta.get("content")
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
            self._reset_usage()
            messages = self._build_messages(prompt, system, conversation_history)

            data = {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
                "max_tokens": DEFAULT_MAX_TOKENS,
                **self._anti_repeat_params(),
                **self._sampling_params(),
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

            # Extract token usage if available
            if "usage" in result:
                usage = result["usage"]
                self.last_usage = {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }

            message = result['choices'][0]['message']
            self.last_reasoning = message.get('reasoning_content') or message.get('reasoning') or ""
            return message['content'].strip()
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
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]],
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> Iterator[str]:
        if not self.api_key:
            raise APIKeyMissingError(f"{self.name} API key not set")
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")

        self._reset_usage()
        messages = self._build_messages(prompt, system, conversation_history)
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            **self._anti_repeat_params(),
            **self._sampling_params(),
            "stream": True,
            # Ask OpenAI-compatible endpoints to report token usage on the
            # final stream chunk so cost tracking works in streaming mode.
            "stream_options": {"include_usage": True},
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
                        if "usage" in chunk and chunk["usage"]:
                            usage = chunk["usage"]
                            self.last_usage = {
                                "input_tokens": usage.get("prompt_tokens", 0),
                                "output_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                            if reasoning:
                                self.last_reasoning += reasoning
                                if on_reasoning:
                                    on_reasoning(reasoning)
                            content = delta.get("content")
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
        """Get available chat/reasoning models from OpenAI, hiding non-chat
        models (embeddings, audio, image, moderation)."""
        models = super().get_available_models()
        skip = ("embedding", "whisper", "tts", "dall-e", "moderation",
                "audio", "image", "realtime", "transcribe", "search")
        chat = [m for m in models if not any(s in m.lower() for s in skip)]
        return sorted(chat)


class VeniceClient(OpenAICompatibleClient):
    """Client for Venice AI (OpenAI-compatible, privacy-focused, uncensored)."""

    def __init__(self, api_key: str = ""):
        super().__init__("Venice AI", VENICE_API_URL, api_key)


class GrokClient(OpenAICompatibleClient):
    """Client for xAI Grok (OpenAI-compatible)."""

    def __init__(self, api_key: str = ""):
        super().__init__("Grok", XAI_API_URL, api_key)


class AnthropicClient(APIClient):
    """Client for Anthropic's Messages API (Claude models)."""

    def __init__(self, api_key: str = ""):
        super().__init__("Anthropic")
        self.api_key = api_key
        self.base_url = ANTHROPIC_API_URL
        self.update_headers()

    def update_headers(self) -> None:
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _anthropic_messages(self, prompt: str, system: str,
                            conversation_history: List[Dict[str, str]]):
        """Map our (system-in-history) format onto Anthropic's shape: a
        separate system string plus a user/assistant messages array that must
        begin with a user turn and carry non-empty content."""
        system_parts = [system] if system else []
        messages: List[Dict[str, str]] = []
        for msg in conversation_history:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                messages.append({"role": "assistant", "content": content})
            elif role == "user":
                messages.append({"role": "user", "content": content})
            else:  # system / narrator injected mid-history
                messages.append({"role": "user", "content": f"[Note] {content}"})
        if prompt and prompt.strip():
            messages.append({"role": "user", "content": prompt.strip()})
        # Anthropic requires the first message to be a user turn.
        if not messages or messages[0]["role"] != "user":
            messages.insert(0, {"role": "user", "content": "(Continue the conversation.)"})
        return "\n\n".join(system_parts), messages

    def _payload(self, prompt, system, history, stream):
        sys_str, messages = self._anthropic_messages(prompt, system, history)
        data = {
            "model": self.model,
            "max_tokens": self.max_tokens or DEFAULT_MAX_TOKENS,
            "messages": messages,
            "temperature": self.temperature if self.temperature is not None else DEFAULT_TEMPERATURE,
            "stream": stream,
        }
        if sys_str:
            data["system"] = sys_str
        return data

    @retry_with_backoff()
    def generate_response(self, prompt: str, system: str,
                          conversation_history: List[Dict[str, str]]) -> str:
        if not self.api_key:
            raise APIKeyMissingError("Anthropic API key not set")
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")
        self._reset_usage()
        try:
            response = requests.post(
                f"{self.base_url}/messages", headers=self.headers,
                json=self._payload(prompt, system, conversation_history, False),
                timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            usage = result.get("usage", {})
            self.last_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }
            texts, thoughts = [], []
            for block in result.get("content", []):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "thinking":
                    thoughts.append(block.get("thinking", ""))
            self.last_reasoning = "".join(thoughts)
            return "".join(texts)
        except requests.HTTPError as e:
            body = e.response.text if e.response is not None else ""
            log.error(f"[Anthropic] HTTP error: {e} {body}")
            raise APIRequestError(f"Anthropic API request failed: {body or e}",
                                  status_code=e.response.status_code if e.response is not None else None,
                                  response_text=body)
        except requests.RequestException as e:
            log.error(f"[Anthropic] Request error: {e}")
            raise APIRequestError(f"Anthropic API request failed: {str(e)}")

    def generate_streaming_response(
        self, prompt: str, system: str, conversation_history: List[Dict[str, str]],
        on_reasoning: Optional[Callable[[str], None]] = None,
    ) -> Iterator[str]:
        if not self.api_key:
            raise APIKeyMissingError("Anthropic API key not set")
        if not self.model:
            raise ModelNotSetError("Model must be set before generating responses")
        self._reset_usage()
        try:
            response = requests.post(
                f"{self.base_url}/messages", headers=self.headers,
                json=self._payload(prompt, system, conversation_history, True),
                stream=True, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                s = line.decode("utf-8").strip()
                if not s.startswith("data:"):
                    continue
                s = s[5:].strip()
                try:
                    ev = json.loads(s)
                except json.JSONDecodeError:
                    continue
                etype = ev.get("type")
                if etype == "message_start":
                    u = ev.get("message", {}).get("usage", {})
                    self.last_usage["input_tokens"] = u.get("input_tokens", 0)
                elif etype == "content_block_delta":
                    delta = ev.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield text
                    elif delta.get("type") == "thinking_delta":
                        think = delta.get("thinking", "")
                        if think:
                            self.last_reasoning += think
                            if on_reasoning:
                                on_reasoning(think)
                elif etype == "message_delta":
                    u = ev.get("usage", {})
                    if "output_tokens" in u:
                        self.last_usage["output_tokens"] = u["output_tokens"]
            self.last_usage["total_tokens"] = (
                self.last_usage["input_tokens"] + self.last_usage["output_tokens"])
        except requests.HTTPError as e:
            body = e.response.text if e.response is not None else ""
            log.error(f"[Anthropic] HTTP error: {e} {body}")
            raise APIRequestError(f"Anthropic API request failed: {body or e}",
                                  status_code=e.response.status_code if e.response is not None else None,
                                  response_text=body)
        except requests.RequestException as e:
            log.error(f"[Anthropic] Request error: {e}")
            raise APIRequestError(f"Anthropic API request failed: {str(e)}")

    def get_available_models(self) -> List[str]:
        if not self.api_key:
            log.error("Anthropic API key not set")
            return []
        try:
            response = requests.get(f"{self.base_url}/models", headers=self.headers,
                                    timeout=MODEL_LIST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            log.error(f"Error fetching Anthropic models: {str(e)}")
            return []
