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

from api_clients import (
    OllamaClient, LMStudioClient, OpenRouterClient, OpenAIClient,
    VeniceClient, GrokClient, AnthropicClient,
)
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
    "openai": lambda: OpenAIClient(api_key=""),
    "anthropic": lambda: AnthropicClient(api_key=""),
    "openrouter": lambda: OpenRouterClient(api_key=""),
    "venice": lambda: VeniceClient(api_key=""),
    "grok": lambda: GrokClient(api_key=""),
}

PROVIDERS_REQUIRING_KEY = ("openrouter", "openai", "anthropic", "venice", "grok")


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
                 app_config: Optional[Dict[str, Any]] = None,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None):
        self.persona = persona
        self.provider = provider.lower()
        self.model = model
        self.client = make_client(provider, app_config)
        self.client.set_model(model)
        self.client.temperature = temperature
        self.client.max_tokens = max_tokens


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
        self.turn_delay = 1.0
        self.director = False
        self.director_every = 4
        self._director_client = None
        self.endless = False
        self.history_limit = DEFAULT_HISTORY_LIMIT
        self.current_turn = 0
        self.run_target = DEFAULT_MAX_TURNS  # turn count the loop runs until
        self._history_id: Optional[int] = None  # auto-save row for this conversation
        self.is_running = False
        self.is_paused = False
        self._thread: Optional[threading.Thread] = None
        # Monotonic id for each worker run. A stale worker (e.g. one still
        # unwinding a blocked API call after stop()) checks this before doing
        # any teardown, so it can't clobber a run that started after it.
        self._run_id = 0
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
                  turn_order: str, streaming: bool,
                  turn_delay: float = 1.0,
                  director: bool = False, director_every: int = 4,
                  endless: bool = False) -> None:
        if self.is_running:
            raise RuntimeError("Conversation already running")
        if len(cast) < 2:
            raise ValueError("Need at least 2 cast members")
        self.cast = cast
        self.topic = topic
        self.endless = endless
        # max_turns == 0 is the "endless" sentinel the UI renders as ∞.
        self.max_turns = 0 if endless else max_turns
        self.turn_order = turn_order
        self.streaming = streaming
        self.turn_delay = max(0.0, min(30.0, turn_delay))
        self.director = director
        self.director_every = max(2, min(50, director_every))
        # The Director narrates twists using a copy of the first cast
        # member's provider/model, so it never disturbs a persona's client.
        self._director_client = None
        if director and cast:
            try:
                lead = cast[0]
                self._director_client = make_client(lead.provider)
                self._director_client.set_model(lead.model)
            except Exception:
                log.exception("Could not build Director client; disabling Director")
                self.director = False

    def start(self) -> None:
        if self.is_running:
            raise RuntimeError("Conversation already running")
        self.conversation = []
        self.current_turn = 0
        # Endless runs until stopped; effectively unbounded target.
        self.run_target = 1_000_000_000 if self.endless else self.max_turns
        self._history_id = None
        self.usage_tracker.reset_session_usage()
        self._start_thread("Conversation starting...")

    def clear(self) -> None:
        """Reset the stage after a finished conversation. Keeps the cast and
        scene settings; wipes the transcript so the next run starts fresh."""
        if self.is_running:
            raise RuntimeError("Stop the conversation before clearing")
        with self._lock:
            self.conversation = []
        self.current_turn = 0
        self.run_target = 0
        self.topic = ""
        self._history_id = None
        self._emit(self.snapshot())

    def continue_run(self, extra_turns: int) -> None:
        """Extend a finished/stopped conversation by extra_turns more turns."""
        if self.is_running:
            raise RuntimeError("Conversation already running")
        if not self.cast:
            raise RuntimeError("No conversation configured")
        if not 1 <= extra_turns <= 200:
            raise ValueError("extra_turns must be between 1 and 200")
        self.run_target = self.current_turn + extra_turns
        self.max_turns = max(self.max_turns, self.run_target)
        self._start_thread(f"Continuing for {extra_turns} more turns...")

    def regenerate_last(self) -> None:
        """Redo the most recent cast turn with a fresh generation."""
        if self.is_running:
            raise RuntimeError("Conversation already running")
        if not self.cast:
            raise RuntimeError("No conversation configured")
        with self._lock:
            if not self.conversation or self.conversation[-1]["role"] not in ("assistant", "user"):
                raise RuntimeError("No cast message to regenerate")
            index = len(self.conversation) - 1
            self.conversation.pop(index)
        self._emit({"type": "message_remove", "index": index})
        self.current_turn = max(0, self.current_turn - 1)
        self.run_target = self.current_turn + 1
        self._start_thread("Regenerating last turn...")

    def load_conversation(self, messages: List[Dict[str, str]], cast: List[CastMember],
                          topic: str, history_id: Optional[int] = None) -> None:
        """Load a past conversation so it can be continued with continue_run()."""
        if self.is_running:
            raise RuntimeError("Conversation already running")
        if len(cast) < 2:
            raise ValueError("Need at least 2 cast members")
        self.cast = cast
        self.topic = topic
        self.conversation = [dict(m) for m in messages]
        self.current_turn = sum(
            1 for m in self.conversation if m.get("role") in ("assistant", "user"))
        self.max_turns = self.current_turn
        self.run_target = self.current_turn
        self.is_paused = False
        # Continuing replaces the original history row rather than duplicating it.
        self._history_id = history_id
        self.usage_tracker.reset_session_usage()
        self._emit(self.snapshot())

    def _start_thread(self, status_text: str) -> None:
        self._run_id += 1
        run_id = self._run_id
        self.is_running = True
        self.is_paused = False
        self._emit({"type": "run_state", "running": True})
        self._emit({"type": "status", "text": status_text})
        self._emit({"type": "turn", "current": self.current_turn, "max": self.max_turns})
        self._thread = threading.Thread(target=self._run_loop, args=(run_id,), daemon=True)
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
                f"The topic is now '{topic}'. Ease into it naturally from where "
                "the conversation is."
            )
        })
        self.topic = topic

    def interject_system(self, content: str) -> None:
        self._append_message({"role": "system", "persona": "System", "content": content})

    def interject_narrator(self, content: str) -> None:
        self._append_message({"role": "narrator", "persona": "Narrator", "content": content})

    def messages_copy(self) -> List[Dict[str, str]]:
        """A stable snapshot of the conversation, safe to read while the worker
        thread is mutating the live list."""
        with self._lock:
            return [dict(m) for m in self.conversation]

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
                for msg in self.messages_copy()
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
                    "thinking": msg.get("thinking", ""),
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

    def _build_api_history(self, current_name: str,
                           drop_last: bool = False) -> List[Dict[str, str]]:
        history = []
        messages = self.conversation
        # The caller echoes the most recent message as the turn's `prompt`;
        # dropping it here prevents that message appearing twice in a row
        # (the classic cause of models parroting and looping).
        if drop_last and messages and messages[-1]["role"] in ("assistant", "user"):
            messages = messages[:-1]
        start = max(0, len(messages) - self.history_limit)
        for msg in messages[start:]:
            # Scene notes ride along as bracketed user messages: many local
            # chat templates (and some providers) reject a "system" role in
            # the middle of the conversation with a 400.
            if msg["role"] == "system":
                history.append({
                    "role": "user",
                    "content": f"[Scene update — respond to this in character]: {msg['content']}"
                })
            elif msg["role"] == "narrator":
                history.append({
                    "role": "user",
                    "content": f"[Scene / narration]: {msg['content']}"
                })
            elif msg["role"] in ("assistant", "user"):
                role = "assistant" if msg["persona"] == current_name else "user"
                history.append({"role": role, "content": msg["content"]})
            else:
                history.append({"role": "user", "content": msg["content"]})
        return history

    def _retry_turn(self, member: CastMember, prompt: str, system_prompt: str,
                    api_history: List[Dict[str, str]]) -> str:
        """Re-generate an empty turn. Thinking models can burn a small
        max_tokens budget entirely on reasoning — if that happened, lift the
        cap for the retry so the reply itself has room."""
        original_cap = member.client.max_tokens
        if original_cap and member.client.last_reasoning:
            log.warning(f"{member.persona.name}: reasoning consumed the "
                        f"max_tokens budget ({original_cap}); retrying uncapped")
            member.client.max_tokens = None
        try:
            return member.client.generate_response(
                prompt=prompt + "\n\n(Give your spoken reply now, in character.)",
                system=system_prompt,
                conversation_history=api_history)
        finally:
            member.client.max_tokens = original_cap

    def _generate_title(self) -> Optional[str]:
        """A short, catchy title for the history list. Best-effort; on any
        failure we return None and the UI falls back to the topic."""
        if not self.cast:
            return None
        recent = [m for m in self.conversation
                  if m.get("role") in ("assistant", "user") and m.get("content")]
        if len(recent) < 2:
            return None
        transcript = "\n".join(f"{m['persona']}: {m['content']}" for m in recent[:6])
        transcript = transcript[:3000]
        try:
            client = self.cast[0].client
            raw = client.generate_response(
                prompt=(f"Topic: {self.topic}\n\nOpening of the conversation:\n"
                        f"{transcript}\n\nGive a punchy title (3-6 words)."),
                system=("You name conversations. Reply with ONLY a short, evocative "
                        "title of 3-6 words — no quotes, no punctuation at the end, "
                        "no preamble."),
                conversation_history=[])
        except Exception:
            log.exception("Title generation failed")
            return None
        title = self._clean_response(raw.strip()).strip('"\'').splitlines()[0].strip()
        return title[:80] or None

    def _run_director_event(self) -> None:
        """Ask the Director model for one brief scene twist and inject it as a
        narrator note. Failures are swallowed — the show goes on."""
        if not self._director_client:
            return
        recent = [m for m in self.messages_copy()
                  if m.get("role") in ("assistant", "user") and m.get("content")]
        transcript = "\n".join(f"{m['persona']}: {m['content']}" for m in recent[-8:])
        transcript = transcript[-4000:]
        cast_names = ", ".join(m.persona.name for m in self.cast)
        system = (
            "You are the unseen Director of an improvised scene. You never speak "
            "as any character. When called, you introduce ONE short, unexpected "
            "development — a complication, a new arrival, a shift in the "
            "environment, a revelation, a change of stakes — to keep the scene "
            "alive and pull it somewhere new. Write it as 1–2 vivid sentences of "
            "stage narration in the present tense. No preamble, no quotation "
            "marks, just the event."
        )
        prompt = (
            f"The scene is about: {self.topic}\n"
            f"The characters present: {cast_names}\n\n"
            f"Recent moments:\n{transcript}\n\n"
            "Introduce the next twist now."
        )
        self._emit({"type": "status", "text": "The Director is setting up a twist…"})
        try:
            twist = self._director_client.generate_response(
                prompt=prompt, system=system, conversation_history=[])
        except Exception:
            log.exception("Director event generation failed")
            return
        twist = self._clean_response(twist.strip())
        if twist:
            self.interject_narrator(twist)

    def _run_loop(self, run_id: int = 0) -> None:
        log.info("Conversation loop started")
        # When resuming/continuing, pick up from the last real message.
        last_content = next(
            (m["content"] for m in reversed(self.conversation)
             if m["role"] in ("assistant", "user") and m["content"]),
            "Let's start the conversation.")
        try:
            while (self.is_running and self._run_id == run_id
                   and self.current_turn < self.run_target):
                while self.is_paused and self.is_running:
                    time.sleep(0.1)
                if not self.is_running:
                    break

                # Only the turn immediately after an interjection reacts to it
                # as the prompt; after that the scene carries on normally.
                recent_system = ([self.conversation[-1]]
                                 if self.conversation
                                 and self.conversation[-1]["role"] in ("system", "narrator")
                                 else [])

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
                    # In a normal turn the previous message is echoed as the
                    # prompt, so exclude it from history to avoid duplication.
                    # In a system-injection turn the prompt is a fresh alert and
                    # the injected message belongs in history, so keep it.
                    api_history = self._build_api_history(
                        name, drop_last=not recent_system)
                    system_prompt = member.persona.get_system_prompt(self.topic)

                    if recent_system:
                        last_system = recent_system[-1]
                        prompt = (
                            f"{last_system['content']}\n\n"
                            "Respond in character, weaving this into your reply naturally "
                            "before carrying on."
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

                        def on_reasoning(delta, _msg=new_msg, _index=index,
                                         _name=name, _role=new_role, _ci=actor_index):
                            _msg["thinking"] = _msg.get("thinking", "") + delta
                            self._emit({"type": "thinking_chunk", "index": _index,
                                        "persona": _name, "role": _role,
                                        "color_index": _ci,
                                        "content": _msg["thinking"]})

                        stream = member.client.generate_streaming_response(
                            prompt=prompt, system=system_prompt,
                            conversation_history=api_history,
                            on_reasoning=on_reasoning)
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
                            # Stopped mid-turn: drop the placeholder if it never
                            # got content, so we don't save/serve a blank message
                            # or desync indices against the frontend.
                            with self._lock:
                                if (placeholder_index is not None
                                        and placeholder_index == len(self.conversation) - 1
                                        and not self.conversation[placeholder_index]["content"]):
                                    self.conversation.pop(placeholder_index)
                                    self._emit({"type": "message_remove", "index": placeholder_index})
                            break
                        # Thinking models occasionally spend the whole turn in
                        # reasoning and stream no content — retry instead of
                        # posting a blank message.
                        for attempt in range(2):
                            if new_msg["content"] or not self.is_running:
                                break
                            log.warning(f"{name} produced an empty turn, retrying ({attempt + 1}/2)")
                            content = self._retry_turn(member, prompt, system_prompt, api_history)
                            new_msg["content"] = self._clean_response(content.strip())
                            if member.client.last_reasoning:
                                new_msg["thinking"] = member.client.last_reasoning
                            self._emit({"type": "message_chunk", "index": index,
                                        "content": new_msg["content"]})
                        if not new_msg["content"]:
                            log.error(f"{name}'s turn stayed empty after retries")
                        self._emit({"type": "message_complete", "index": index,
                                    "persona": name, "role": new_role,
                                    "content": new_msg["content"],
                                    "thinking": new_msg.get("thinking", ""),
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
                            content = self._retry_turn(member, prompt, system_prompt, api_history)
                            new_msg["content"] = self._clean_response(content.strip())
                        if member.client.last_reasoning:
                            new_msg["thinking"] = member.client.last_reasoning
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

                    # Auto-Director: every N turns, drop in a narrated twist so
                    # unattended runs keep evolving. Injected as a narrator note
                    # the next speaker reacts to.
                    if (self.director and self.is_running
                            and self.current_turn < self.run_target
                            and self.current_turn % self.director_every == 0):
                        self._run_director_event()

                    # Pause between turns (interruptible)
                    for _ in range(int(self.turn_delay * 10)):
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
                    # Drop the streaming placeholder (even if it got partial
                    # content) so a failed turn leaves no blank/stuck bubble and
                    # the fallback below can't produce a duplicate or index drift.
                    with self._lock:
                        if (placeholder_index is not None
                                and placeholder_index == len(self.conversation) - 1
                                and self.conversation[placeholder_index]["role"] in ("assistant", "user")):
                            self.conversation.pop(placeholder_index)
                            self._emit({"type": "message_remove", "index": placeholder_index})

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

            reason = "max_turns" if self.current_turn >= self.run_target else "stopped"
        except Exception as e:
            log.exception("Fatal error in conversation loop")
            reason = "fatal"
            self._emit({"type": "error", "text": f"Fatal error: {e}"})
        finally:
            # If a newer run has started (this thread was superseded after a
            # stop→start), do NO teardown — otherwise we'd clobber the new run's
            # state, emit a spurious 'done', and mis-save its conversation.
            if self._run_id != run_id:
                log.info(f"Stale conversation loop {run_id} exiting quietly")
                return

            self.is_running = False
            self._emit({"type": "typing_end"})

            # Auto-save to history
            if len(self.conversation) > 1:
                try:
                    names = [m.persona.name for m in self.cast]
                    models = [m.model for m in self.cast]
                    metadata = {
                        "theme": self.topic,
                        "title": self._generate_title(),
                        "persona1": names[0] if names else "N/A",
                        "persona2": names[1] if len(names) > 1 else "N/A",
                        "model1": models[0] if models else "N/A",
                        "model2": models[1] if len(models) > 1 else "N/A",
                    }
                    # A continued/regenerated run re-saves the same conversation:
                    # replace the previous auto-save instead of duplicating it.
                    if self._history_id is not None:
                        try:
                            self.history_manager.delete_conversation(self._history_id)
                        except Exception:
                            log.exception("Failed to replace previous history entry")
                    self._history_id = self.history_manager.save_conversation(
                        self.conversation, metadata)
                    log.info(f"Conversation auto-saved to history id={self._history_id}")
                except Exception:
                    log.exception("Failed to auto-save conversation")

            self._emit({"type": "done", "reason": reason, "turns": self.current_turn})
            log.info("Conversation loop finished")
