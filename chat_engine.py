#!/usr/bin/env python3
"""
chat_engine.py - UI-agnostic conversation engine for Auto Chat

Runs the multi-persona conversation loop on a worker thread and reports
everything through an event callback, so any frontend (web, CLI, desktop)
can drive it. Each cast member gets its OWN client instance, so multiple
personas can share a provider while using different models.

Events emitted (dicts, always with a "type" key):
    status            {text}
    turn              {current, max}
    typing            {persona, index}
    typing_end        {}
    message_start     {index, persona, role, color_index}
    message_chunk     {index, content}            # full content so far
    message_complete  {index, persona, role, content, color_index}
    usage             {tokens, cost, input_tokens, output_tokens}
    error             {text}
    done              {reason, turns}
"""

import os
import json
import time
import random
import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any

from api_clients import OllamaClient, LMStudioClient, OpenRouterClient, OpenAIClient
from persona import Persona
from conversation_history import ConversationHistory
from utils.usage_tracker import get_tracker
from utils.config_utils import load_json_with_comments
from exceptions import APIKeyMissingError, ModelNotSetError, APIRequestError
from config import (
    LOG_FILE,
    PERSONAS_FILE,
    CONFIG_FILE,
    DEFAULT_MAX_TURNS,
    DEFAULT_HISTORY_LIMIT,
)

log = logging.getLogger("chat_engine")

CLIENT_FACTORIES = {
    "ollama": lambda: OllamaClient(),
    "lmstudio": lambda: LMStudioClient(),
    "openrouter": lambda: OpenRouterClient(api_key=""),
    "openai": lambda: OpenAIClient(api_key=""),
}

PROVIDERS_REQUIRING_KEY = ("openrouter", "openai")


# --- Persona persistence (shared with any frontend) ------------------------

def load_personas() -> List[Persona]:
    """Load personas from the JSON file, creating defaults if missing."""
    try:
        if os.path.exists(PERSONAS_FILE):
            data = load_json_with_comments(PERSONAS_FILE)
            if isinstance(data, dict):
                data = data.get("personas", [])
            return [Persona.from_dict(p) for p in data]
        defaults = [
            Persona("Alice", "Curious and analytical AI", 1, "female"),
            Persona("Bob", "Creative and slightly eccentric AI", 1, "male"),
        ]
        save_personas(defaults)
        return defaults
    except Exception:
        log.exception("Error loading personas")
        return []


def save_personas(personas: List[Persona]) -> bool:
    try:
        with open(PERSONAS_FILE, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in personas], f, indent=4)
        return True
    except Exception:
        log.exception("Error saving personas")
        return False


def load_app_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            return load_json_with_comments(CONFIG_FILE)
        except Exception:
            log.exception("Error loading config")
    return {}


def save_app_config(cfg: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception:
        log.exception("Error saving config")


def normalize_provider_url(provider: str, url: str) -> str:
    """Normalize a user-entered base URL for a local provider."""
    url = url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    if provider == "lmstudio" and url and not url.endswith("/v1"):
        url += "/v1"
    if provider == "ollama" and url.endswith("/api"):
        url = url[:-4]
    return url


def make_client(provider: str, app_config: Optional[Dict[str, Any]] = None):
    """Create a fresh client for a provider, wiring in any saved API key and
    custom base URL (e.g. LM Studio on another machine).

    A fresh instance per cast member lets several personas share a provider
    while running different models.
    """
    provider = provider.lower()
    if provider not in CLIENT_FACTORIES:
        raise ValueError(f"Unknown provider: {provider}")
    cfg = app_config if app_config is not None else load_app_config()

    custom_url = cfg.get(f"{provider}_url", "")
    if provider == "ollama" and custom_url:
        client = OllamaClient(base_url=normalize_provider_url(provider, custom_url))
    elif provider == "lmstudio" and custom_url:
        client = LMStudioClient(base_url=normalize_provider_url(provider, custom_url))
    else:
        client = CLIENT_FACTORIES[provider]()

    if provider in PROVIDERS_REQUIRING_KEY:
        client.api_key = cfg.get(f"{provider}_api_key", "")
        client.update_headers()
    return client


class CastMember:
    """A persona bound to its own provider client and model."""

    def __init__(self, persona: Persona, provider: str, model: str,
                 app_config: Optional[Dict[str, Any]] = None):
        self.persona = persona
        self.provider = provider.lower()
        self.model = model
        self.client = make_client(provider, app_config)
        self.client.set_model(model)


class ConversationEngine:
    """Runs one conversation at a time; emits events via callback."""

    def __init__(self, emit: Callable[[Dict[str, Any]], None]):
        self._emit_cb = emit
        self.cast: List[CastMember] = []
        self.conversation: List[Dict[str, str]] = []
        self.topic = ""
        self.max_turns = DEFAULT_MAX_TURNS
        self.turn_order = "round-robin"
        self.streaming = True
        self.history_limit = DEFAULT_HISTORY_LIMIT
        self.current_turn = 0
        self.is_running = False
        self.is_paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.history_manager = ConversationHistory()
        self.usage_tracker = get_tracker()

    # --- event helper ---------------------------------------------------

    def _emit(self, event: Dict[str, Any]) -> None:
        try:
            self._emit_cb(event)
        except Exception:
            log.exception("Event emit failed")

    # --- public control -------------------------------------------------

    def configure(self, cast: List[CastMember], topic: str, max_turns: int,
                  turn_order: str, streaming: bool) -> None:
        if self.is_running:
            raise RuntimeError("Conversation already running")
        if len(cast) < 2:
            raise ValueError("Need at least 2 cast members")
        self.cast = cast
        self.topic = topic
        self.max_turns = max_turns
        self.turn_order = turn_order
        self.streaming = streaming

    def start(self) -> None:
        if self.is_running:
            raise RuntimeError("Conversation already running")
        self.conversation = []
        self.current_turn = 0
        self.is_running = True
        self.is_paused = False
        self.usage_tracker.reset_session_usage()
        self._emit({"type": "status", "text": "Conversation starting..."})
        self._emit({"type": "turn", "current": 0, "max": self.max_turns})
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self.is_running:
            self.is_paused = True
            self._emit({"type": "status", "text": "Paused"})

    def resume(self) -> None:
        if self.is_running:
            self.is_paused = False
            self._emit({"type": "status", "text": "Resumed"})

    def stop(self) -> None:
        self.is_running = False

    def interject_topic(self, topic: str) -> None:
        self._append_message({
            "role": "system", "persona": "System",
            "content": (
                f"NEW TOPIC: The conversation should now shift to discussing '{topic}'. "
                "All participants should acknowledge this topic change naturally and start "
                "discussing this new topic."
            )
        })
        self.topic = topic

    def interject_system(self, content: str) -> None:
        self._append_message({"role": "system", "persona": "System", "content": content})

    def interject_narrator(self, content: str) -> None:
        self._append_message({"role": "narrator", "persona": "Narrator", "content": content})

    def snapshot(self) -> Dict[str, Any]:
        """Current state for clients that (re)connect mid-conversation."""
        return {
            "type": "snapshot",
            "running": self.is_running,
            "paused": self.is_paused,
            "topic": self.topic,
            "turn": {"current": self.current_turn, "max": self.max_turns},
            "cast": [
                {"persona": m.persona.name, "provider": m.provider, "model": m.model}
                for m in self.cast
            ],
            "messages": [
                {**msg, "color_index": self._color_index(msg)}
                for msg in self.conversation
            ],
            "usage": self.usage_tracker.get_session_usage(),
        }

    # --- internals --------------------------------------------------------

    def _color_index(self, msg: Dict[str, str]) -> int:
        for i, m in enumerate(self.cast):
            if msg.get("persona") == m.persona.name:
                return i
        return -1  # system / narrator

    def _append_message(self, msg: Dict[str, str]) -> None:
        with self._lock:
            self.conversation.append(msg)
            index = len(self.conversation) - 1
        self._log_message(msg)
        self._emit({"type": "message_complete", "index": index,
                    "persona": msg["persona"], "role": msg["role"],
                    "content": msg["content"],
                    "color_index": self._color_index(msg)})

    def _log_message(self, msg: Dict[str, str]) -> None:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                stamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                f.write(f"{stamp} {msg['persona']} ({msg['role']}): {msg['content']}\n")
        except Exception as e:
            log.error(f"Failed to write log file: {e}")

    def _clean_response(self, text: str) -> str:
        patterns = [
            "Click reply or enter to continue",
            "Click reply or enter after each message",
            "Press Enter to continue",
            "Type your response below",
            "Click to respond",
            "Please respond to continue our conversation",
            "Your turn to respond",
            "Click below to respond",
        ]
        cleaned = text
        for pattern in patterns:
            for variant in (pattern, pattern + ".", pattern + "!", pattern + ","):
                cleaned = cleaned.replace(variant, "")
                cleaned = cleaned.replace(variant.lower(), "")
                cleaned = cleaned.replace(variant.upper(), "")
        return cleaned.strip()

    def _build_api_history(self, current_name: str) -> List[Dict[str, str]]:
        history = []
        start = max(0, len(self.conversation) - self.history_limit)
        for msg in self.conversation[start:]:
            if msg["role"] == "system":
                history.append({
                    "role": "system",
                    "content": f"IMPORTANT - MUST ACKNOWLEDGE AND REACT TO THIS IMMEDIATELY: {msg['content']}"
                })
            elif msg["role"] == "narrator":
                history.append({
                    "role": "system",
                    "content": f"URGENT SCENE CHANGE - REACT TO THIS IMMEDIATELY: {msg['content']}"
                })
            elif msg["role"] in ("assistant", "user"):
                role = "assistant" if msg["persona"] == current_name else "user"
                history.append({"role": role, "content": msg["content"]})
            else:
                history.append({"role": "user", "content": msg["content"]})
        return history

    def _run_loop(self) -> None:
        log.info("Conversation loop started")
        last_content = "Let's start the conversation."
        try:
            while self.is_running and self.current_turn < self.max_turns:
                while self.is_paused and self.is_running:
                    time.sleep(0.1)
                if not self.is_running:
                    break

                recent_system = [m for m in self.conversation[-3:]
                                 if m["role"] in ("system", "narrator")]

                if self.turn_order == "random":
                    actor_index = random.randint(0, len(self.cast) - 1)
                else:
                    actor_index = self.current_turn % len(self.cast)
                member = self.cast[actor_index]
                name = member.persona.name

                self._emit({"type": "status",
                            "text": f"Turn {self.current_turn + 1}/{self.max_turns}: {name} is thinking..."})
                self._emit({"type": "typing", "persona": name, "index": actor_index})

                placeholder_index = None
                try:
                    api_history = self._build_api_history(name)
                    system_prompt = member.persona.get_system_prompt(self.topic)

                    if recent_system:
                        last_system = recent_system[-1]
                        prompt = (
                            f"EMERGENCY ALERT - {last_system['content']}\n\n"
                            "You MUST acknowledge and react to this situation immediately before "
                            "continuing any previous conversation. How do you respond to this urgent situation?"
                        )
                        system_prompt += (
                            "\n\nCRITICAL INSTRUCTION: When you receive an emergency alert or system "
                            "message, you MUST:\n1. Immediately acknowledge and react to the situation"
                            "\n2. Show appropriate urgency and emotion in your response"
                            "\n3. Take appropriate action based on the emergency"
                            "\n4. Temporarily pause any ongoing conversation topics"
                            "\n5. Focus entirely on the current situation until it is resolved"
                        )
                    else:
                        prompt = last_content

                    new_role = "assistant" if actor_index == 0 else "user"
                    new_msg = {"role": new_role, "persona": name, "content": ""}

                    if self.streaming:
                        with self._lock:
                            self.conversation.append(new_msg)
                            index = len(self.conversation) - 1
                        placeholder_index = index
                        started = False
                        content = ""
                        stream = member.client.generate_streaming_response(
                            prompt=prompt, system=system_prompt,
                            conversation_history=api_history)
                        for chunk in stream:
                            if not self.is_running:
                                break
                            if not started:
                                self._emit({"type": "typing_end"})
                                self._emit({"type": "message_start", "index": index,
                                            "persona": name, "role": new_role,
                                            "color_index": actor_index})
                                started = True
                            content += chunk
                            new_msg["content"] = self._clean_response(content)
                            self._emit({"type": "message_chunk", "index": index,
                                        "content": new_msg["content"]})
                        if not self.is_running:
                            break
                        # Thinking models occasionally spend the whole turn in
                        # reasoning and stream no content — retry instead of
                        # posting a blank message.
                        for attempt in range(2):
                            if new_msg["content"] or not self.is_running:
                                break
                            log.warning(f"{name} produced an empty turn, retrying ({attempt + 1}/2)")
                            content = member.client.generate_response(
                                prompt=prompt + "\n\n(Give your spoken reply now, in character.)",
                                system=system_prompt,
                                conversation_history=api_history)
                            new_msg["content"] = self._clean_response(content.strip())
                            self._emit({"type": "message_chunk", "index": index,
                                        "content": new_msg["content"]})
                        if not new_msg["content"]:
                            log.error(f"{name}'s turn stayed empty after retries")
                        self._emit({"type": "message_complete", "index": index,
                                    "persona": name, "role": new_role,
                                    "content": new_msg["content"],
                                    "color_index": actor_index})
                        self._log_message(new_msg)
                    else:
                        content = member.client.generate_response(
                            prompt=prompt, system=system_prompt,
                            conversation_history=api_history)
                        new_msg["content"] = self._clean_response(content.strip())
                        for attempt in range(2):
                            if new_msg["content"] or not self.is_running:
                                break
                            log.warning(f"{name} produced an empty turn, retrying ({attempt + 1}/2)")
                            content = member.client.generate_response(
                                prompt=prompt + "\n\n(Give your spoken reply now, in character.)",
                                system=system_prompt,
                                conversation_history=api_history)
                            new_msg["content"] = self._clean_response(content.strip())
                        self._emit({"type": "typing_end"})
                        self._append_message(new_msg)

                    if new_msg["content"]:
                        last_content = new_msg["content"]

                    # Usage tracking (per cast member's own client)
                    usage = member.client.get_last_usage()
                    if usage.get("total_tokens", 0) > 0:
                        self.usage_tracker.record_usage(
                            provider=member.provider, model=member.model,
                            persona=name,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0))
                        session = self.usage_tracker.get_session_usage()
                        self._emit({"type": "usage",
                                    "tokens": session["total_tokens"],
                                    "cost": session["estimated_cost"],
                                    "input_tokens": session["input_tokens"],
                                    "output_tokens": session["output_tokens"]})

                    self.current_turn += 1
                    self._emit({"type": "turn", "current": self.current_turn,
                                "max": self.max_turns})

                    for _ in range(10):
                        if not self.is_running:
                            break
                        time.sleep(0.1)

                except (APIKeyMissingError, ModelNotSetError) as e:
                    log.error(f"Configuration error on turn {self.current_turn + 1}: {e}")
                    self._emit({"type": "typing_end"})
                    self._emit({"type": "error", "text": str(e)})
                    self.is_running = False
                    break
                except APIRequestError as e:
                    log.error(f"API error on turn {self.current_turn + 1}: {e}")
                    self._emit({"type": "typing_end"})
                    # Drop the streaming placeholder if it never got content,
                    # so a failed turn doesn't leave a blank message behind.
                    with self._lock:
                        if (placeholder_index is not None
                                and placeholder_index == len(self.conversation) - 1
                                and not self.conversation[placeholder_index]["content"]):
                            self.conversation.pop(placeholder_index)

                    # Fallback model support
                    fb_prov = member.persona.fallback_provider
                    fb_model = member.persona.fallback_model
                    if fb_prov and fb_model:
                        self._emit({"type": "status",
                                    "text": f"{name}'s model failed — trying fallback {fb_prov}/{fb_model}"})
                        try:
                            fb_client = make_client(fb_prov)
                            fb_client.set_model(fb_model)
                            content = fb_client.generate_response(
                                prompt=prompt, system=system_prompt,
                                conversation_history=api_history)
                            new_msg = {
                                "role": "assistant" if actor_index == 0 else "user",
                                "persona": name,
                                "content": self._clean_response(content.strip()),
                            }
                            self._append_message(new_msg)
                            last_content = new_msg["content"]
                            self.current_turn += 1
                            self._emit({"type": "turn", "current": self.current_turn,
                                        "max": self.max_turns})
                            continue
                        except Exception as fb_err:
                            log.error(f"Fallback also failed: {fb_err}")

                    self._emit({"type": "error",
                                "text": f"{name}'s turn failed: {e} — skipping turn"})
                    self.current_turn += 1
                    self._emit({"type": "turn", "current": self.current_turn,
                                "max": self.max_turns})
                    continue
                except Exception as e:
                    log.exception("Unexpected error in turn")
                    self._emit({"type": "typing_end"})
                    self._emit({"type": "error", "text": f"Unexpected error: {e}"})
                    self.is_running = False
                    break

            reason = "max_turns" if self.current_turn >= self.max_turns else "stopped"
        except Exception as e:
            log.exception("Fatal error in conversation loop")
            reason = "fatal"
            self._emit({"type": "error", "text": f"Fatal error: {e}"})
        finally:
            self.is_running = False
            self._emit({"type": "typing_end"})

            # Auto-save to history
            if len(self.conversation) > 1:
                try:
                    names = [m.persona.name for m in self.cast]
                    models = [m.model for m in self.cast]
                    metadata = {
                        "theme": self.topic,
                        "persona1": names[0] if names else "N/A",
                        "persona2": names[1] if len(names) > 1 else "N/A",
                        "model1": models[0] if models else "N/A",
                        "model2": models[1] if len(models) > 1 else "N/A",
                    }
                    conv_id = self.history_manager.save_conversation(self.conversation, metadata)
                    log.info(f"Conversation auto-saved to history id={conv_id}")
                except Exception:
                    log.exception("Failed to auto-save conversation")

            self._emit({"type": "done", "reason": reason, "turns": self.current_turn})
            log.info("Conversation loop finished")
