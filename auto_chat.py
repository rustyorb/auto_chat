#!/usr/bin/env python3
"""
auto_chat.py - Auto Chat Studio

A single-window studio for AI-to-AI conversations. Turn-based conversations
between two or more AI personas using different LLM providers (Ollama,
LM Studio, OpenAI, OpenRouter).

Features:
- Persistent studio layout: cast sidebar + live conversation stage
- Incremental, flicker-free rendering (streams at up to 30fps)
- Multi-persona conversations with round-robin/random turn order
- Templates, conversation history, in-conversation search
- Live token & cost tracking, usage dashboard
- Keyboard-driven workflow
"""

import os
import sys
import json
import time
import logging
import threading
import random
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import requests
from dotenv import load_dotenv
from api_clients import APIClient, OllamaClient, LMStudioClient, OpenRouterClient, OpenAIClient
from persona import Persona
from conversation_history import ConversationHistory
from utils.config_utils import load_json_with_comments
from utils.analytics import summarize_conversation
from utils.usage_tracker import get_tracker
from utils.export_formats import export_conversation
from conversation_templates import (
    ConversationTemplate,
    initialize_templates,
    list_templates,
    save_template,
    delete_template
)
from exceptions import (
    APIException,
    APIKeyMissingError,
    ModelNotSetError,
    APIRequestError
)

# Tkinter imports
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog, filedialog
import ttkbootstrap as tkb
from ttkbootstrap.constants import *  # For constants like NORMAL, DISABLED etc.

# Load environment variables from .env file (for API keys)
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="[%X]",
)
log = logging.getLogger("auto_chat")

# Import configuration constants
from config import (
    LOG_FILE,
    PERSONAS_FILE,
    CONFIG_FILE,
    DEFAULT_MAX_TURNS,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_TOPIC,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    DEFAULT_THEME
)

# --- Studio palette -------------------------------------------------------

STAGE_BG = "#1a1d21"          # conversation canvas
STAGE_FG = "#e8eaed"          # primary text
SIDEBAR_BG = "#22262b"        # sidebar panel
CARD_BG = "#2a2f36"           # cast card
CARD_BG_ACTIVE = "#343b44"    # selected cast card
MUTED_FG = "#8a919c"          # secondary text
HAIRLINE = "#31363d"          # separators

PERSONA_COLORS = [
    "#4cc9f0",  # cyan
    "#f72585",  # magenta
    "#ffd166",  # amber
    "#06d6a0",  # mint
    "#c77dff",  # violet
    "#ff8fab",  # rose
    "#80ffdb",  # aqua
    "#fca311",  # orange
    "#90e0ef",  # sky
    "#e5989b",  # blush
]

PROVIDERS_REQUIRING_KEY = ("openrouter", "openai")

BODY_FONT = ("Helvetica", 11)
NAME_FONT = ("Helvetica", 11, "bold")
TIME_FONT = ("Helvetica", 8)
SMALL_FONT = ("Helvetica", 9)
SECTION_FONT = ("Helvetica", 9, "bold")


# --- Configuration Loading/Saving -----------------------------------------

def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file allowing comments."""
    if os.path.exists(CONFIG_FILE):
        try:
            return load_json_with_comments(CONFIG_FILE)
        except Exception as e:
            log.error(f"Error loading config file {CONFIG_FILE}: {e}")
    return {}


def save_config(config_data: Dict[str, Any]):
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
    except IOError as e:
        log.error(f"Error saving config file {CONFIG_FILE}: {e}")


class ChatManager:
    """Manages the conversation logic, API interactions, and state."""

    def __init__(self, app: 'ChatApp'):
        self.app = app
        self.personas: List[Persona] = []
        self.api_clients: Dict[str, APIClient] = {
            "ollama": OllamaClient(),
            "lmstudio": LMStudioClient(),
            "openrouter": OpenRouterClient(api_key=""),
            "openai": OpenAIClient(api_key="")
        }
        self.selected_personas: List[Persona] = []
        self.selected_clients: List[APIClient] = []
        self.selected_models: List[str] = []
        self.conversation: List[Dict[str, str]] = []
        self.current_turn = 0
        self.max_turns = DEFAULT_MAX_TURNS
        self.conversation_theme = ""
        self.is_running = False
        self.is_paused = False
        self.chat_thread: Optional[threading.Thread] = None
        self.history_limit = DEFAULT_HISTORY_LIMIT  # Limit the history sent to the API
        self.history_manager = ConversationHistory()
        self.turn_order_strategy = "round-robin"  # Options: "round-robin", "random"

        # Initialize templates
        initialize_templates()

        # Initialize usage tracker
        self.usage_tracker = get_tracker()

    def load_personas(self):
        """Load personas from the JSON file."""
        try:
            if os.path.exists(PERSONAS_FILE):
                personas_data = load_json_with_comments(PERSONAS_FILE)
                if isinstance(personas_data, list):
                    self.personas = [Persona.from_dict(p) for p in personas_data]
                elif isinstance(personas_data, dict):
                    self.personas = [Persona.from_dict(p) for p in personas_data.get('personas', [])]
                else:
                    raise TypeError(
                        f"Unexpected data type loaded from {PERSONAS_FILE}: {type(personas_data)}"
                    )
                log.info(f"Loaded {len(self.personas)} personas from {PERSONAS_FILE}")
            else:
                log.warning(f"Personas file not found: {PERSONAS_FILE}. Creating default personas.")
                default_personas = [
                    Persona("Alice", "Curious and analytical AI", 1, "female"),
                    Persona("Bob", "Creative and slightly eccentric AI", 1, "male")
                ]
                self.personas = default_personas
                self.save_personas()
        except Exception as e:
            log.exception(f"Error loading personas: {e}")
            messagebox.showerror("Error", f"Failed to load personas from {PERSONAS_FILE}: {e}")
            self.personas = []

    def save_personas(self):
        """Save current personas to the JSON file."""
        try:
            with open(PERSONAS_FILE, 'w', encoding='utf-8') as f:
                json.dump([p.to_dict() for p in self.personas], f, indent=4)
            log.info(f"Saved {len(self.personas)} personas to {PERSONAS_FILE}")
        except Exception as e:
            log.exception(f"Error saving personas: {e}")
            messagebox.showerror("Error", f"Failed to save personas to {PERSONAS_FILE}: {e}")

    def save_conversation(self):
        """Save the current conversation log to a file."""
        if not self.conversation:
            self.app.toast("No conversation to save yet", "warning")
            return

        filepath = filedialog.asksaveasfilename(
            title="Save Conversation Log",
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("JSON files", "*.json"),
                ("Markdown files", "*.md"),
                ("HTML files", "*.html"),
                ("CSV files", "*.csv"),
                ("PDF files", "*.pdf"),
                ("All files", "*.*")
            ],
            parent=self.app
        )

        if not filepath:
            return  # User cancelled

        try:
            metadata = {
                'theme': self.conversation_theme,
                'persona1': self.selected_personas[0].name if len(self.selected_personas) > 0 else 'N/A',
                'persona2': self.selected_personas[1].name if len(self.selected_personas) > 1 else 'N/A',
                'model1': self.selected_models[0] if len(self.selected_models) > 0 else 'N/A',
                'model2': self.selected_models[1] if len(self.selected_models) > 1 else 'N/A',
            }

            file_ext = filepath.split('.')[-1].lower()

            if file_ext == 'json':
                with open(filepath, 'w', encoding='utf-8') as f:
                    export_data = {
                        'metadata': metadata,
                        'conversation': self.conversation
                    }
                    json.dump(export_data, f, indent=4)
            elif file_ext in ['md', 'html', 'csv', 'pdf']:
                export_conversation(self.conversation, metadata, filepath, file_ext)
            else:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"Conversation Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Theme: {self.conversation_theme}\n")
                    f.write(f"Personas: {metadata['persona1']} vs {metadata['persona2']}\n")
                    f.write(f"Models: {metadata['model1']} vs {metadata['model2']}\n")
                    f.write("-" * 20 + "\n\n")
                    for msg in self.conversation:
                        f.write(f"{msg['persona']} ({msg['role']}):\n{msg['content']}\n\n")

            log.info(f"Conversation saved to {filepath}")
            self.app.toast(f"Saved to {os.path.basename(filepath)}")
        except ImportError as e:
            log.exception(f"Missing dependency for export: {e}")
            messagebox.showerror(
                "Error",
                f"Missing required library: {e}\n\nFor PDF export, install: pip install reportlab",
                parent=self.app
            )
        except Exception as e:
            log.exception(f"Error saving conversation: {e}")
            messagebox.showerror("Error", f"Failed to save conversation: {e}", parent=self.app)

    def start_conversation(self, theme: str):
        """Start a new conversation in a separate thread."""
        if self.is_running:
            log.warning("Attempted to start conversation while already running.")
            return

        self.conversation = []
        self.current_turn = 0
        self.conversation_theme = theme
        self.is_running = True
        self.is_paused = False

        # Reset usage tracking for new conversation
        self.usage_tracker.reset_session_usage()

        # Ensure selected components are valid
        if len(self.selected_personas) < 2 or len(self.selected_clients) < 2:
            messagebox.showerror(
                "Error",
                "Setup incomplete. Please select at least two personas and their models.",
                parent=self.app
            )
            self.is_running = False
            return

        log.info(f"Starting conversation. Theme: '{theme}', Turn order: {self.turn_order_strategy}")
        for i, persona in enumerate(self.selected_personas):
            log.info(f"Persona {i+1}: {persona.name} ({self.selected_clients[i].name} - {self.selected_models[i]})")
        log.info(f"Max turns: {self.max_turns}")

        # Update GUI status
        self.app.after(0, self.app.update_status, "Conversation starting...")
        self.app.after(0, self.app.enable_controls, True)
        self.app.after(0, lambda: self.app.pause_button.config(text="Pause", bootstyle="warning"))
        self.app.after(0, lambda: self.app.narrator_button.config(state=DISABLED, bootstyle="secondary"))
        self.app.after(0, self.app.update_progress, 0, self.max_turns)

        # Start the conversation loop in a new thread
        self.chat_thread = threading.Thread(target=self._run_conversation_loop, daemon=True)
        self.chat_thread.start()

    def _run_conversation_loop(self):
        """The main loop where the conversation happens."""
        log.info("Conversation loop started.")
        try:
            last_message_content = "Let's start the conversation."  # Initial prompt for the first AI

            while self.is_running and self.current_turn < self.max_turns:
                # --- Pause Handling ---
                while self.is_paused and self.is_running:
                    time.sleep(0.1)
                    if not self.is_running:
                        break

                if not self.is_running:
                    break

                # --- Check for System Messages ---
                recent_system_messages = [
                    msg for msg in self.conversation[-3:]
                    if msg["role"] in ["system", "narrator"]
                ]

                # --- Determine Current Actor ---
                num_personas = len(self.selected_personas)
                if self.turn_order_strategy == "random":
                    actor_index = random.randint(0, num_personas - 1)
                else:  # round-robin
                    actor_index = self.current_turn % num_personas
                current_persona = self.selected_personas[actor_index]
                current_client = self.selected_clients[actor_index]

                self.app.after(0, self.app.update_status,
                               f"Turn {self.current_turn + 1}/{self.max_turns}: {current_persona.name} is thinking...")
                self.app.after(0, self.app.show_typing_indicator, current_persona.name, actor_index)
                log.debug(f"Turn {self.current_turn + 1}: '{current_persona.name}' is thinking...")

                # --- Prepare API Request ---
                try:
                    # Format conversation history for API
                    api_history = []
                    history_start_index = max(0, len(self.conversation) - self.history_limit)

                    for msg in self.conversation[history_start_index:]:
                        if msg["role"] == "system":
                            api_history.append({
                                "role": "system",
                                "content": f"IMPORTANT - MUST ACKNOWLEDGE AND REACT TO THIS IMMEDIATELY: {msg['content']}"
                            })
                        elif msg["role"] == "narrator":
                            api_history.append({
                                "role": "system",
                                "content": f"URGENT SCENE CHANGE - REACT TO THIS IMMEDIATELY: {msg['content']}"
                            })
                        elif msg["role"] in ("assistant", "user"):
                            role = "assistant" if msg["persona"] == current_persona.name else "user"
                            api_history.append({"role": role, "content": msg["content"]})
                        else:
                            api_history.append({"role": "user", "content": msg["content"]})

                    # Get base system prompt
                    system_prompt = current_persona.get_system_prompt(self.conversation_theme)

                    # Modify prompt if there are recent system messages
                    if recent_system_messages:
                        last_system = recent_system_messages[-1]
                        prompt = (
                            f"EMERGENCY ALERT - {last_system['content']}\n\n"
                            "You MUST acknowledge and react to this situation immediately before continuing "
                            "any previous conversation. How do you respond to this urgent situation?"
                        )
                        system_prompt = system_prompt + (
                            "\n\nCRITICAL INSTRUCTION: When you receive an emergency alert or system message, you MUST:"
                            "\n1. Immediately acknowledge and react to the situation"
                            "\n2. Show appropriate urgency and emotion in your response"
                            "\n3. Take appropriate action based on the emergency"
                            "\n4. Temporarily pause any ongoing conversation topics"
                            "\n5. Focus entirely on the current situation until it is resolved"
                        )
                    else:
                        prompt = last_message_content

                    log.info(f"Sending to API - System Prompt: {system_prompt[:100]}...")
                    log.info(f"Sending to API - Current Prompt: {prompt[:100]}...")
                    log.info(f"Sending to API - History Length: {len(api_history)}")

                    # --- Call API ---
                    start_time = time.time()
                    if self.app.streaming_var.get():
                        # --- Streaming Response ---
                        response_content = ""
                        new_role = "assistant" if actor_index == 0 else "user"

                        # Prepare the message placeholder
                        new_msg = {"role": new_role, "persona": current_persona.name, "content": ""}
                        self.conversation.append(new_msg)

                        stream = current_client.generate_streaming_response(
                            prompt=prompt, system=system_prompt, conversation_history=api_history
                        )

                        first_chunk = True
                        for chunk in stream:
                            if not self.is_running:
                                break
                            if first_chunk:
                                # First token arrived: swap the typing indicator for live text
                                self.app.after(0, self.app.hide_typing_indicator)
                                first_chunk = False
                            response_content += chunk
                            new_msg["content"] = self._clean_model_response(response_content)
                            self.app.after(0, self.app.update_conversation_display, True)

                        if not self.is_running:
                            break

                        # Finalize the streamed message (drops the cursor glyph)
                        self.app.after(0, self.app.update_conversation_display)
                    else:
                        # --- Non-Streaming Response ---
                        response_content = current_client.generate_response(
                            prompt=prompt,
                            system=system_prompt,
                            conversation_history=api_history
                        )
                        response_content = self._clean_model_response(response_content.strip())
                        new_role = "assistant" if actor_index == 0 else "user"
                        new_msg = {
                            "role": new_role,
                            "persona": current_persona.name,
                            "content": response_content,
                        }
                        self.conversation.append(new_msg)
                        self.app.after(0, self.app.hide_typing_indicator)
                        self.app.after(0, self.app.update_conversation_display)

                    end_time = time.time()
                    log.debug(f"'{current_persona.name}' generated response in {end_time - start_time:.2f} seconds.")

                    # Track token usage. Resolve the registry key for the
                    # client ("LM Studio" -> "lmstudio") so pricing lookups
                    # and grouping stay consistent.
                    usage = current_client.get_last_usage()
                    if usage.get("total_tokens", 0) > 0:
                        provider = next(
                            (k for k, v in self.api_clients.items() if v is current_client),
                            current_client.name.lower().replace(" ", "")
                        )
                        self.usage_tracker.record_usage(
                            provider=provider,
                            model=self.selected_models[actor_index],
                            persona=current_persona.name,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0)
                        )

                        session_usage = self.usage_tracker.get_session_usage()
                        usage_text = f"{session_usage['total_tokens']:,} tok  ·  ${session_usage['estimated_cost']:.4f}"
                        self.app.after(0, self.app.update_usage_display, usage_text)

                    if not self.is_running:
                        break

                    # Log the complete message
                    self._log_message(new_msg)
                    last_message_content = response_content
                    self.app.after(0, self.app.update_status,
                                   f"Turn {self.current_turn + 1}/{self.max_turns}: Waiting...")

                    # Increment turn
                    self.current_turn += 1
                    self.app.after(0, self.app.update_progress, self.current_turn, self.max_turns)

                    # Small delay between turns, but check is_running frequently
                    for _ in range(10):
                        if not self.is_running:
                            break
                        time.sleep(0.1)

                except APIKeyMissingError as e:
                    log.error(f"API key error during turn {self.current_turn + 1}: {e}")
                    self.app.after(0, self.app.hide_typing_indicator)
                    error_msg = f"API Key Error: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    self.app.after(0, messagebox.showerror, "API Key Error", str(e))
                    self.is_running = False
                    break
                except ModelNotSetError as e:
                    log.error(f"Model not set error during turn {self.current_turn + 1}: {e}")
                    self.app.after(0, self.app.hide_typing_indicator)
                    error_msg = f"Model Error: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    self.is_running = False
                    break
                except APIRequestError as e:
                    log.error(f"API request error during turn {self.current_turn + 1}: {e}")
                    self.app.after(0, self.app.hide_typing_indicator)
                    error_msg = f"API Request Error during {current_persona.name}'s turn: {str(e)}"

                    # Try fallback model if configured
                    if current_persona.fallback_provider and current_persona.fallback_model:
                        log.info(f"Attempting fallback to {current_persona.fallback_provider}/{current_persona.fallback_model}")
                        self.app.after(0, self.app.update_status, "Primary model failed. Trying fallback model...")

                        try:
                            fallback_client = self.api_clients.get(current_persona.fallback_provider.lower())
                            if fallback_client:
                                original_model = fallback_client.model
                                fallback_client.set_model(current_persona.fallback_model)

                                response_content = fallback_client.generate_response(
                                    prompt=prompt,
                                    system=system_prompt,
                                    conversation_history=api_history
                                )
                                response_content = self._clean_model_response(response_content.strip())

                                if original_model:
                                    fallback_client.set_model(original_model)

                                new_role = "assistant" if actor_index == 0 else "user"
                                new_msg = {
                                    "role": new_role,
                                    "persona": current_persona.name,
                                    "content": response_content
                                }
                                self.conversation.append(new_msg)
                                self._log_message(new_msg)
                                last_message_content = response_content

                                self.app.after(0, self.app.update_conversation_display)
                                self.app.after(0, self.app.update_status,
                                               f"Turn {self.current_turn + 1}/{self.max_turns}: Completed with fallback model")

                                self.current_turn += 1
                                self.app.after(0, self.app.update_progress, self.current_turn, self.max_turns)
                                continue
                            else:
                                log.error(f"Fallback client '{current_persona.fallback_provider}' not found")
                        except Exception as fallback_error:
                            log.error(f"Fallback model also failed: {fallback_error}")
                            self.app.after(0, self.app.update_status,
                                           f"Both primary and fallback models failed for {current_persona.name}")

                    # If we get here, no fallback or fallback failed
                    self.app.after(0, self.app.update_status, error_msg)
                    # Continue to next turn instead of stopping the conversation
                    self.current_turn += 1
                    self.app.after(0, self.app.update_progress, self.current_turn, self.max_turns)
                    continue
                except Exception as e:
                    log.exception(f"Unexpected error during turn {self.current_turn + 1}")
                    self.app.after(0, self.app.hide_typing_indicator)
                    error_msg = f"Unexpected error during {current_persona.name}'s turn: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    self.is_running = False
                    break

            # --- Conversation End ---
            final_status = "Conversation finished (max turns reached)" if self.current_turn >= self.max_turns else "Conversation stopped"
            log.info(final_status)

            self.app.after(0, self.app.update_status, final_status)
            self.app.after(0, self.app.enable_controls, False)
            self.app.after(0, lambda: self.app.pause_button.config(text="Pause", bootstyle="warning"))

        except Exception as e:
            log.exception("Fatal error in conversation loop")
            self.app.after(0, self.app.update_status, f"Fatal error: {str(e)}")
            self.app.after(0, self.app.enable_controls, False)
        finally:
            self.is_running = False
            self.app.after(0, self.app.hide_typing_indicator)
            summary = summarize_conversation(self.conversation)
            log.info("Conversation summary:\n" + summary)

            # Auto-save to history if conversation has content
            if len(self.conversation) > 1:
                try:
                    metadata = {
                        'theme': self.conversation_theme,
                        'persona1': self.selected_personas[0].name if self.selected_personas else 'N/A',
                        'persona2': self.selected_personas[1].name if len(self.selected_personas) > 1 else 'N/A',
                        'model1': self.selected_models[0] if self.selected_models else 'N/A',
                        'model2': self.selected_models[1] if len(self.selected_models) > 1 else 'N/A',
                    }
                    conversation_id = self.history_manager.save_conversation(self.conversation, metadata)
                    log.info(f"Conversation auto-saved to history with ID: {conversation_id}")
                    self.app.after(0, self.app.toast, "Saved to history", "info")
                except Exception as e:
                    log.error(f"Failed to auto-save conversation to history: {e}")

            log.info("Conversation loop finished.")

    def _clean_model_response(self, text: str) -> str:
        """Remove common UI instructions from model responses."""
        patterns = [
            "Click reply or enter to continue",
            "Click reply or enter after each message",
            "Press Enter to continue",
            "Type your response below",
            "Click to respond",
            "Please respond to continue our conversation",
            "Your turn to respond",
            "Click below to respond"
        ]

        cleaned_text = text
        for pattern in patterns:
            for variant in [pattern, pattern + ".", pattern + "!", pattern + ","]:
                cleaned_text = cleaned_text.replace(variant, "")
                cleaned_text = cleaned_text.replace(variant.lower(), "")
                cleaned_text = cleaned_text.replace(variant.upper(), "")

        return cleaned_text.strip()

    def add_narrator_message(self, message: str):
        """Add a narrator message to the conversation history."""
        if not message:
            return

        narrator_msg = {
            "role": "narrator",
            "persona": "Narrator",
            "content": message
        }
        self.conversation.append(narrator_msg)
        self._log_message(narrator_msg)
        self.app.after(0, self.app.update_conversation_display)
        log.info(f"Narrator message added: {message}")

    def add_system_instruction(self, instruction: str):
        """Add a system instruction to guide the conversation."""
        if not instruction:
            return

        system_msg = {
            "role": "system",
            "persona": "System",
            "content": instruction
        }

        self.conversation.append(system_msg)
        self._log_message(system_msg)

        self.app.after(0, self.app.update_conversation_display)
        log.info(f"System instruction added: {instruction}")

    def _log_message(self, msg_data: Dict[str, str]):
        """Append a message to the global log file."""
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
                f.write(f"{timestamp} {msg_data['persona']} ({msg_data['role']}): {msg_data['content']}\n")
        except Exception as e:
            log.error(f"Failed to write to log file {LOG_FILE}: {e}")


class ChatApp(tkb.Window):
    """Auto Chat Studio: single-window app with a persistent sidebar and stage."""

    def __init__(self):
        super().__init__(themename=DEFAULT_THEME)

        self.title("Auto Chat Studio")
        self.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        # Core state
        self.chat_manager = ChatManager(self)
        self.app_config = load_config()
        self.chat_manager.load_personas()

        # Cast/model selection state
        self.cast: List[str] = []                       # persona names in the conversation, in turn order
        self.persona_model_config: Dict[str, Tuple[str, str]] = {}
        self.selected_cast_member: Optional[str] = None
        self._model_cache: Dict[str, List[str]] = {}    # provider -> models
        self._model_fetch_seq = 0

        # Scene options (exist before any UI so ChatManager can read them)
        self.streaming_var = tkb.BooleanVar(value=True)
        self.topic_var = tkb.StringVar(value=DEFAULT_TOPIC)
        self.max_turns_var = tkb.IntVar(value=DEFAULT_MAX_TURNS)
        self.turn_order_var = tkb.StringVar(value="round-robin")
        self.template_var = tkb.StringVar(value="None")

        # Search state
        self.search_var = tkb.StringVar()
        self.case_sensitive_var = tkb.BooleanVar(value=False)
        self.regex_var = tkb.BooleanVar(value=False)
        self.search_matches: List[Tuple[str, str]] = []
        self.current_search_index = -1

        # Incremental-render state
        self._rendered_count = 0
        self._stream_active = False
        self._stream_tag = "p0_body"
        self._stream_dirty = False
        self._stream_flush_scheduled = False
        self._hero_visible = False

        # Typing indicator / toast state
        self._typing_job: Optional[str] = None
        self._typing_phase = 0
        self._toast_job: Optional[str] = None
        self._toast_widget: Optional[tk.Label] = None

        # Build UI
        self._build_menu()
        self._build_layout()
        self.bind_keyboard_shortcuts()

        # Seed cast with first two personas
        if len(self.chat_manager.personas) >= 2:
            self.cast = [self.chat_manager.personas[0].name, self.chat_manager.personas[1].name]
        elif self.chat_manager.personas:
            self.cast = [self.chat_manager.personas[0].name]
        for name in self.cast:
            self.persona_model_config.setdefault(name, ("ollama", ""))
        self._render_cast()
        if self.cast:
            self._select_cast_member(self.cast[0])

        self.refresh_templates()
        self._show_hero()
        self.update_status("Ready — assemble your cast and press Start")

    # ------------------------------------------------------------------ #
    #  Layout                                                             #
    # ------------------------------------------------------------------ #

    def _build_menu(self):
        menubar = tkb.Menu(self)

        file_menu = tkb.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Conversation", accelerator="Ctrl+N", command=self.new_conversation)
        file_menu.add_command(label="Save / Export…", accelerator="Ctrl+S", command=self.chat_manager.save_conversation)
        file_menu.add_separator()
        file_menu.add_command(label="Usage & Costs…", command=self.show_usage_dashboard)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        history_menu = tkb.Menu(menubar, tearoff=0)
        history_menu.add_command(label="Browse History…", command=self.show_history_browser)
        history_menu.add_command(label="Statistics…", command=self.show_history_stats)
        menubar.add_cascade(label="History", menu=history_menu)

        help_menu = tkb.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_stage()

    # --- Sidebar ---------------------------------------------------------

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=SIDEBAR_BG, width=320)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)  # cast list stretches
        self.sidebar = sidebar

        # Brand
        brand = tk.Frame(sidebar, bg=SIDEBAR_BG)
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        tk.Label(brand, text="⬢ AUTO CHAT", bg=SIDEBAR_BG, fg=STAGE_FG,
                 font=("Helvetica", 14, "bold")).pack(side=LEFT)
        tk.Label(brand, text="STUDIO", bg=SIDEBAR_BG, fg="#4cc9f0",
                 font=("Helvetica", 14, "bold")).pack(side=LEFT, padx=(6, 0))

        self._sidebar_section(sidebar, "CAST", row=1)

        # Cast list (scrollable canvas of cards)
        cast_holder = tk.Frame(sidebar, bg=SIDEBAR_BG)
        cast_holder.grid(row=2, column=0, sticky="nsew", padx=12)
        cast_holder.grid_columnconfigure(0, weight=1)
        cast_holder.grid_rowconfigure(0, weight=1)

        self.cast_canvas = tk.Canvas(cast_holder, bg=SIDEBAR_BG, highlightthickness=0, bd=0)
        cast_scroll = tkb.Scrollbar(cast_holder, orient="vertical", command=self.cast_canvas.yview,
                                    bootstyle="dark-round")
        self.cast_inner = tk.Frame(self.cast_canvas, bg=SIDEBAR_BG)
        self._cast_window = self.cast_canvas.create_window((0, 0), window=self.cast_inner, anchor="nw")
        self.cast_inner.bind("<Configure>",
                             lambda e: self.cast_canvas.configure(scrollregion=self.cast_canvas.bbox("all")))
        self.cast_canvas.bind("<Configure>",
                              lambda e: self.cast_canvas.itemconfigure(self._cast_window, width=e.width))
        self.cast_canvas.configure(yscrollcommand=cast_scroll.set)
        self.cast_canvas.grid(row=0, column=0, sticky="nsew")
        cast_scroll.grid(row=0, column=1, sticky="ns")

        # Cast toolbar
        cast_tools = tk.Frame(sidebar, bg=SIDEBAR_BG)
        cast_tools.grid(row=3, column=0, sticky="ew", padx=16, pady=(6, 4))
        tkb.Button(cast_tools, text="＋", width=3, command=self._add_cast_member,
                   bootstyle="success-outline").pack(side=LEFT, padx=(0, 4))
        tkb.Button(cast_tools, text="－", width=3, command=self._remove_cast_member,
                   bootstyle="danger-outline").pack(side=LEFT, padx=4)
        tkb.Button(cast_tools, text="↑", width=3, command=lambda: self._move_cast_member(-1),
                   bootstyle="secondary-outline").pack(side=LEFT, padx=4)
        tkb.Button(cast_tools, text="↓", width=3, command=lambda: self._move_cast_member(1),
                   bootstyle="secondary-outline").pack(side=LEFT, padx=4)
        tkb.Button(cast_tools, text="Library…", command=self.show_persona_library,
                   bootstyle="info-link").pack(side=RIGHT)

        # Model panel for selected cast member
        self._sidebar_section(sidebar, "MODEL", row=4)
        model_panel = tk.Frame(sidebar, bg=SIDEBAR_BG)
        model_panel.grid(row=5, column=0, sticky="ew", padx=16)
        model_panel.grid_columnconfigure(1, weight=1)

        self.model_panel_title = tk.Label(model_panel, text="No cast member selected",
                                          bg=SIDEBAR_BG, fg=MUTED_FG, font=SMALL_FONT, anchor="w")
        self.model_panel_title.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))

        tk.Label(model_panel, text="Provider", bg=SIDEBAR_BG, fg=MUTED_FG,
                 font=SMALL_FONT).grid(row=1, column=0, sticky="w", pady=2)
        self.provider_var = tkb.StringVar(value="ollama")
        self.provider_combo = tkb.Combobox(model_panel, textvariable=self.provider_var,
                                           values=list(self.chat_manager.api_clients.keys()),
                                           state="readonly", width=12)
        self.provider_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        self.api_key_button = tkb.Button(model_panel, text="🔑", width=3,
                                         command=self._prompt_api_key, bootstyle="warning-outline")
        # gridded on demand in _load_models

        tk.Label(model_panel, text="Model", bg=SIDEBAR_BG, fg=MUTED_FG,
                 font=SMALL_FONT).grid(row=2, column=0, sticky="w", pady=2)
        self.model_var = tkb.StringVar()
        self.model_combo = tkb.Combobox(model_panel, textvariable=self.model_var, width=12)
        self.model_combo.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=2)
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)

        self.model_refresh_btn = tkb.Button(model_panel, text="↻", width=3,
                                            command=lambda: self._load_models(self.provider_var.get(), force=True),
                                            bootstyle="secondary-outline")
        self.model_refresh_btn.grid(row=2, column=2, padx=(6, 0), pady=2)
        self.model_panel = model_panel

        # Scene panel
        self._sidebar_section(sidebar, "SCENE", row=6)
        scene = tk.Frame(sidebar, bg=SIDEBAR_BG)
        scene.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 4))
        scene.grid_columnconfigure(1, weight=1)

        tk.Label(scene, text="Topic", bg=SIDEBAR_BG, fg=MUTED_FG,
                 font=SMALL_FONT).grid(row=0, column=0, sticky="w", pady=2)
        self.topic_entry = tkb.Entry(scene, textvariable=self.topic_var)
        self.topic_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2)

        tk.Label(scene, text="Template", bg=SIDEBAR_BG, fg=MUTED_FG,
                 font=SMALL_FONT).grid(row=1, column=0, sticky="w", pady=2)
        self.template_combo = tkb.Combobox(scene, textvariable=self.template_var, state="readonly", width=12)
        self.template_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)
        tkb.Button(scene, text="💾", width=3, command=self.save_current_as_template,
                   bootstyle="secondary-outline").grid(row=1, column=2, padx=(6, 0), pady=2)

        tk.Label(scene, text="Turns", bg=SIDEBAR_BG, fg=MUTED_FG,
                 font=SMALL_FONT).grid(row=2, column=0, sticky="w", pady=2)
        turns_row = tk.Frame(scene, bg=SIDEBAR_BG)
        turns_row.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=2)
        tkb.Spinbox(turns_row, from_=2, to=200, textvariable=self.max_turns_var,
                    width=5).pack(side=LEFT)
        tkb.Combobox(turns_row, textvariable=self.turn_order_var,
                     values=["round-robin", "random"], state="readonly",
                     width=11).pack(side=LEFT, padx=(8, 0))

        tkb.Checkbutton(scene, text="Stream responses", variable=self.streaming_var,
                        bootstyle="info-round-toggle").grid(row=3, column=0, columnspan=3,
                                                            sticky="w", pady=(8, 2))

        # Start button
        self.start_button = tkb.Button(sidebar, text="▶  Start Conversation",
                                       command=self.start_conversation, bootstyle="success")
        self.start_button.grid(row=8, column=0, sticky="ew", padx=16, pady=14, ipady=6)

    def _sidebar_section(self, parent, title, row):
        holder = tk.Frame(parent, bg=SIDEBAR_BG)
        holder.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 4))
        tk.Label(holder, text=title, bg=SIDEBAR_BG, fg=MUTED_FG,
                 font=SECTION_FONT).pack(side=LEFT)
        tk.Frame(holder, bg=HAIRLINE, height=1).pack(side=LEFT, fill=X, expand=True, padx=(8, 0), pady=1)

    # --- Stage (main area) -------------------------------------------------

    def _build_stage(self):
        main = tk.Frame(self, bg=STAGE_BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        # Header
        header = tk.Frame(main, bg=STAGE_BG)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 6))
        header.grid_columnconfigure(1, weight=1)

        self.status_dot = tk.Canvas(header, width=12, height=12, bg=STAGE_BG, highlightthickness=0)
        self._status_dot_item = self.status_dot.create_oval(2, 2, 11, 11, fill="#5b6470", outline="")
        self.status_dot.grid(row=0, column=0, padx=(0, 8))

        self.header_topic = tk.Label(header, text="No conversation yet", bg=STAGE_BG, fg=STAGE_FG,
                                     font=("Helvetica", 12, "bold"), anchor="w")
        self.header_topic.grid(row=0, column=1, sticky="ew")

        self.progress_label = tk.Label(header, text="", bg=STAGE_BG, fg=MUTED_FG, font=SMALL_FONT)
        self.progress_label.grid(row=0, column=2, padx=(8, 8))
        self.progress_bar = tkb.Progressbar(header, length=140, maximum=100, value=0,
                                            bootstyle="info-striped")
        self.progress_bar.grid(row=0, column=3)

        self.usage_var = tkb.StringVar(value="0 tok  ·  $0.0000")
        tk.Label(header, textvariable=self.usage_var, bg=STAGE_BG, fg="#ffd166",
                 font=SMALL_FONT).grid(row=0, column=4, padx=(14, 6))

        tkb.Button(header, text="🔍", width=3, command=self.toggle_search_bar,
                   bootstyle="secondary-outline").grid(row=0, column=5)

        # Search bar (hidden until toggled)
        self.search_frame = tk.Frame(main, bg=STAGE_BG)
        self.search_frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 4))
        self.search_frame.grid_remove()

        self.search_entry = tkb.Entry(self.search_frame, textvariable=self.search_var, width=28)
        self.search_entry.pack(side=LEFT, padx=(0, 4))
        self.search_entry.bind("<Return>", lambda e: self.search_conversation())
        tkb.Button(self.search_frame, text="Find", command=self.search_conversation,
                   bootstyle="info-outline").pack(side=LEFT, padx=2)
        tkb.Button(self.search_frame, text="◀", width=2, command=self.search_prev,
                   bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        tkb.Button(self.search_frame, text="▶", width=2, command=self.search_next,
                   bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        tkb.Checkbutton(self.search_frame, text="Aa", variable=self.case_sensitive_var,
                        bootstyle="info-round-toggle").pack(side=LEFT, padx=6)
        tkb.Checkbutton(self.search_frame, text=".*", variable=self.regex_var,
                        bootstyle="info-round-toggle").pack(side=LEFT, padx=2)
        self.search_result_label = tk.Label(self.search_frame, text="", bg=STAGE_BG, fg=MUTED_FG,
                                            font=SMALL_FONT)
        self.search_result_label.pack(side=LEFT, padx=8)
        tkb.Button(self.search_frame, text="✕", width=2, command=self.toggle_search_bar,
                   bootstyle="secondary-link").pack(side=RIGHT)

        # Conversation display
        stage_holder = tk.Frame(main, bg=STAGE_BG)
        stage_holder.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 0))
        stage_holder.grid_columnconfigure(0, weight=1)
        stage_holder.grid_rowconfigure(0, weight=1)

        self.conversation_display = tk.Text(
            stage_holder, wrap="word", bg=STAGE_BG, fg=STAGE_FG,
            insertbackground=STAGE_FG, selectbackground="#3a4a5c",
            relief="flat", bd=0, highlightthickness=0,
            font=BODY_FONT, padx=10, pady=8, cursor="arrow",
        )
        stage_scroll = tkb.Scrollbar(stage_holder, orient="vertical",
                                     command=self.conversation_display.yview, bootstyle="dark-round")
        self.conversation_display.configure(yscrollcommand=stage_scroll.set)
        self.conversation_display.grid(row=0, column=0, sticky="nsew")
        stage_scroll.grid(row=0, column=1, sticky="ns")
        self.conversation_display.config(state=DISABLED)
        self._configure_stage_tags()

        # Typing indicator
        typing_row = tk.Frame(main, bg=STAGE_BG, height=24)
        typing_row.grid(row=3, column=0, sticky="ew", padx=26, pady=(2, 2))
        self.typing_dot = tk.Canvas(typing_row, width=10, height=10, bg=STAGE_BG, highlightthickness=0)
        self._typing_dot_item = self.typing_dot.create_oval(1, 1, 9, 9, fill="#4cc9f0", outline="")
        self.typing_label = tk.Label(typing_row, text="", bg=STAGE_BG, fg=MUTED_FG,
                                     font=("Helvetica", 9, "italic"), anchor="w")
        # (dot + label packed on demand by show_typing_indicator)
        self._typing_row = typing_row

        # Control bar
        controls = tk.Frame(main, bg=STAGE_BG)
        controls.grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 6))

        self.pause_button = tkb.Button(controls, text="Pause", command=self.toggle_pause,
                                       bootstyle="warning", state=DISABLED, width=10)
        self.pause_button.pack(side=LEFT, padx=(0, 6))
        self.stop_button = tkb.Button(controls, text="Stop", command=self.stop_conversation,
                                      bootstyle="danger", state=DISABLED, width=10)
        self.stop_button.pack(side=LEFT, padx=6)

        self.narrator_button = tkb.Menubutton(controls, text="Interject ▾", bootstyle="secondary",
                                              state=DISABLED)
        interject_menu = tkb.Menu(self.narrator_button, tearoff=0)
        interject_menu.add_command(label="New Topic…  (Ctrl+T)", command=self.add_new_topic)
        interject_menu.add_command(label="System Message…", command=self.add_narrator_message)
        self.narrator_button["menu"] = interject_menu
        self.narrator_button.pack(side=LEFT, padx=6)
        self.new_topic_button = self.narrator_button  # single interject control covers both

        tkb.Button(controls, text="Export", command=self.chat_manager.save_conversation,
                   bootstyle="info-outline", width=9).pack(side=RIGHT)

        # Footer status
        footer = tk.Frame(main, bg="#15181c")
        footer.grid(row=5, column=0, sticky="ew")
        self.status_var = tkb.StringVar()
        tk.Label(footer, textvariable=self.status_var, bg="#15181c", fg=MUTED_FG,
                 font=SMALL_FONT, anchor="w", padx=18, pady=4).pack(fill=X)

        self.stage_main = main

    def _configure_stage_tags(self):
        d = self.conversation_display
        for idx, color in enumerate(PERSONA_COLORS):
            d.tag_configure(f"p{idx}_name", foreground=color, font=NAME_FONT,
                            spacing1=14, lmargin1=6)
            d.tag_configure(f"p{idx}_body", foreground=STAGE_FG, font=BODY_FONT,
                            lmargin1=24, lmargin2=24, spacing3=4, rmargin=18)
        d.tag_configure("msg_time", foreground="#5b6470", font=TIME_FONT)
        d.tag_configure("sys_line", foreground=MUTED_FG, font=("Helvetica", 9, "italic"),
                        justify="center", spacing1=10, spacing3=10)
        d.tag_configure("hero_title", foreground=STAGE_FG, font=("Helvetica", 20, "bold"),
                        justify="center", spacing1=60)
        d.tag_configure("hero_sub", foreground=MUTED_FG, font=("Helvetica", 11),
                        justify="center", spacing1=8)
        d.tag_configure("hero_kbd", foreground="#4cc9f0", font=("Helvetica", 10),
                        justify="center", spacing1=4)
        d.tag_configure("search_highlight", background="#8a6d1a", foreground="#ffffff")
        d.tag_configure("current_match", background="#fca311", foreground="#1a1d21")

    # ------------------------------------------------------------------ #
    #  Hero / empty state                                                 #
    # ------------------------------------------------------------------ #

    def _show_hero(self):
        d = self.conversation_display
        d.config(state=NORMAL)
        d.delete("1.0", END)
        d.insert(END, "⬢ Auto Chat Studio\n", "hero_title")
        d.insert(END, "Assemble a cast, set the scene, and watch AI personas talk.\n\n", "hero_sub")
        d.insert(END, "▶ Start        Space Pause/Resume        Ctrl+Q Stop\n", "hero_kbd")
        d.insert(END, "Ctrl+F Search        Ctrl+S Export        Ctrl+T Interject topic\n", "hero_kbd")
        d.config(state=DISABLED)
        self._hero_visible = True
        self._rendered_count = 0
        self._stream_active = False

    # ------------------------------------------------------------------ #
    #  Cast management                                                    #
    # ------------------------------------------------------------------ #

    def _cast_color(self, name: str) -> str:
        try:
            idx = self.cast.index(name)
        except ValueError:
            idx = 0
        return PERSONA_COLORS[idx % len(PERSONA_COLORS)]

    def _render_cast(self):
        for w in self.cast_inner.winfo_children():
            w.destroy()

        if not self.cast:
            tk.Label(self.cast_inner, text="No cast yet — press ＋ to add personas",
                     bg=SIDEBAR_BG, fg=MUTED_FG, font=SMALL_FONT).pack(pady=12)
            return

        for i, name in enumerate(self.cast):
            selected = (name == self.selected_cast_member)
            bg = CARD_BG_ACTIVE if selected else CARD_BG
            card = tk.Frame(self.cast_inner, bg=bg, padx=10, pady=7,
                            highlightthickness=1,
                            highlightbackground=self._cast_color(name) if selected else HAIRLINE)
            card.pack(fill=X, pady=3, padx=2)

            top = tk.Frame(card, bg=bg)
            top.pack(fill=X)
            dot = tk.Canvas(top, width=10, height=10, bg=bg, highlightthickness=0)
            dot.create_oval(1, 1, 9, 9, fill=self._cast_color(name), outline="")
            dot.pack(side=LEFT, padx=(0, 7))
            tk.Label(top, text=name, bg=bg, fg=STAGE_FG,
                     font=("Helvetica", 10, "bold"), anchor="w").pack(side=LEFT)
            tk.Label(top, text=f"#{i + 1}", bg=bg, fg=MUTED_FG,
                     font=TIME_FONT).pack(side=RIGHT)

            provider, model = self.persona_model_config.get(name, ("ollama", ""))
            sub = model if model else "no model selected"
            tk.Label(card, text=f"{provider} · {sub}", bg=bg, fg=MUTED_FG,
                     font=SMALL_FONT, anchor="w").pack(fill=X, padx=(17, 0))

            for widget in (card, top, *card.winfo_children(), *top.winfo_children()):
                widget.bind("<Button-1>", lambda e, n=name: self._select_cast_member(n))

    def _select_cast_member(self, name: str):
        self.selected_cast_member = name
        self._render_cast()

        provider, model = self.persona_model_config.get(name, ("ollama", ""))
        self.model_panel_title.config(text=f"Configuring:  {name}", fg=self._cast_color(name))
        self.provider_var.set(provider)
        self.model_var.set(model)
        self._load_models(provider)

    def _add_cast_member(self):
        available = [p.name for p in self.chat_manager.personas if p.name not in self.cast]
        if not available:
            self.toast("Everyone in the library is already on stage", "warning")
            return
        if len(self.cast) >= 10:
            self.toast("Cast is full (max 10)", "warning")
            return

        menu = tkb.Menu(self, tearoff=0)
        for name in available:
            menu.add_command(label=name, command=lambda n=name: self._do_add_cast_member(n))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _do_add_cast_member(self, name: str):
        self.cast.append(name)
        self.persona_model_config.setdefault(name, ("ollama", ""))
        self._select_cast_member(name)

    def _remove_cast_member(self):
        if not self.selected_cast_member:
            return
        name = self.selected_cast_member
        self.cast.remove(name)
        self.selected_cast_member = self.cast[0] if self.cast else None
        self._render_cast()
        if self.selected_cast_member:
            self._select_cast_member(self.selected_cast_member)
        else:
            self.model_panel_title.config(text="No cast member selected", fg=MUTED_FG)

    def _move_cast_member(self, delta: int):
        if not self.selected_cast_member:
            return
        i = self.cast.index(self.selected_cast_member)
        j = i + delta
        if 0 <= j < len(self.cast):
            self.cast[i], self.cast[j] = self.cast[j], self.cast[i]
            self._render_cast()

    # ------------------------------------------------------------------ #
    #  Model selection                                                    #
    # ------------------------------------------------------------------ #

    def _on_provider_changed(self, event=None):
        provider = self.provider_var.get()
        if self.selected_cast_member:
            self.persona_model_config[self.selected_cast_member] = (provider, "")
        self.model_var.set("")
        self._load_models(provider)
        self._render_cast()

    def _on_model_changed(self, event=None):
        model = self.model_var.get()
        provider = self.provider_var.get()
        if not model or model.startswith(("Error", "Loading", "No models", "API key")):
            return
        if self.selected_cast_member:
            self.persona_model_config[self.selected_cast_member] = (provider, model)
        self.app_config[f"last_model_{provider.lower().replace(' ', '')}"] = model
        save_config(self.app_config)
        self._render_cast()

    def _load_models(self, provider: str, force: bool = False):
        provider_key = provider.lower()
        client = self.chat_manager.api_clients.get(provider_key)
        if not client:
            self.model_combo['values'] = ["Error: unknown provider"]
            return

        # API key handling
        if provider_key in PROVIDERS_REQUIRING_KEY:
            client.api_key = self.app_config.get(f"{provider_key}_api_key", "")
            client.update_headers()
            if not client.api_key:
                self.model_combo['values'] = ["API key required"]
                self.model_combo.set("API key required")
                self.api_key_button.grid(row=1, column=2, padx=(6, 0), pady=2)
                return
        self.api_key_button.grid_remove()

        # Serve from cache when possible
        if not force and provider_key in self._model_cache:
            self._apply_model_list(provider_key, self._model_cache[provider_key])
            return

        self.model_combo['values'] = ["Loading…"]
        if not self.model_var.get():
            self.model_combo.set("Loading…")

        self._model_fetch_seq += 1
        seq = self._model_fetch_seq

        def fetch():
            try:
                models = client.get_available_models()
                self.after(0, lambda: self._on_models_fetched(seq, provider_key, models, None))
            except Exception as e:
                log.exception(f"Error fetching models for {provider_key}")
                self.after(0, lambda: self._on_models_fetched(seq, provider_key, None, str(e)))

        threading.Thread(target=fetch, daemon=True).start()

    def _on_models_fetched(self, seq, provider_key, models, error):
        if seq != self._model_fetch_seq:
            return  # a newer fetch superseded this one
        if error or not models:
            self.model_combo['values'] = [f"Error: {error}" if error else "No models found"]
            self.model_combo.current(0)
            return
        self._model_cache[provider_key] = models
        self._apply_model_list(provider_key, models)

    def _apply_model_list(self, provider_key, models):
        self.model_combo['values'] = models
        current = ""
        if self.selected_cast_member:
            prov, model = self.persona_model_config.get(self.selected_cast_member, ("", ""))
            if prov.lower() == provider_key and model in models:
                current = model
        if not current:
            saved = self.app_config.get(f"last_model_{provider_key.replace(' ', '')}")
            current = saved if saved in models else models[0]
        self.model_var.set(current)
        if self.selected_cast_member:
            self.persona_model_config[self.selected_cast_member] = (provider_key, current)
        self._render_cast()

    def _prompt_api_key(self):
        provider_key = self.provider_var.get().lower()
        key = simpledialog.askstring(
            "API Key", f"Enter API key for {provider_key}:", parent=self, show="*")
        if key:
            self.app_config[f"{provider_key}_api_key"] = key
            save_config(self.app_config)
            client = self.chat_manager.api_clients.get(provider_key)
            if client:
                client.api_key = key
                client.update_headers()
            self.toast(f"API key saved for {provider_key}")
            self._load_models(provider_key, force=True)

    # ------------------------------------------------------------------ #
    #  Keyboard shortcuts                                                 #
    # ------------------------------------------------------------------ #

    def bind_keyboard_shortcuts(self):
        """Bind keyboard shortcuts for the application."""
        self.bind_all("<Control-n>", lambda e: self.new_conversation())
        self.bind_all("<Control-s>", lambda e: self.chat_manager.save_conversation())
        self.bind_all("<Control-e>", lambda e: self.chat_manager.save_conversation())

        self.bind_all("<space>", self._handle_space_pause)
        self.bind_all("<Control-q>", lambda e: self._handle_stop_shortcut())
        self.bind_all("<Control-t>", lambda e: self._handle_topic_shortcut())
        self.bind_all("<Control-f>", lambda e: self.toggle_search_bar(focus=True))
        self.bind_all("<Escape>", lambda e: self._handle_escape())

        log.info("Keyboard shortcuts bound successfully")

    def _widget_accepts_text(self, widget) -> bool:
        try:
            return widget.winfo_class() in ("Entry", "TEntry", "Text", "TCombobox", "TSpinbox", "Listbox")
        except Exception:
            return False

    def _handle_space_pause(self, event):
        """Space toggles pause — but never while typing in a text widget."""
        if self.chat_manager.is_running and not self._widget_accepts_text(event.widget):
            self.toggle_pause()

    def _handle_stop_shortcut(self):
        if self.chat_manager.is_running:
            self.stop_conversation()

    def _handle_topic_shortcut(self):
        if self.chat_manager.is_running and self.chat_manager.is_paused:
            self.add_new_topic()

    def _handle_escape(self):
        if self.search_frame.winfo_ismapped():
            self.clear_search()
            self.toggle_search_bar()

    # ------------------------------------------------------------------ #
    #  Conversation lifecycle                                             #
    # ------------------------------------------------------------------ #

    def new_conversation(self):
        """Reset the stage for a fresh conversation."""
        if self.chat_manager.is_running:
            if not messagebox.askyesno("New Conversation",
                                       "A conversation is running. Stop it and start fresh?"):
                return
            self.chat_manager.is_running = False

        self.chat_manager.conversation = []
        self._show_hero()
        self.update_progress(0, self.max_turns_var.get())
        self.usage_var.set("0 tok  ·  $0.0000")
        self.header_topic.config(text="No conversation yet")
        self._set_status_dot("idle")
        self.update_status("Ready — assemble your cast and press Start")

    def start_conversation(self):
        """Validate the setup and launch the conversation."""
        if self.chat_manager.is_running:
            return
        if not self.validate_selections():
            return

        self.setup_chat_manager()

        # Reset stage
        d = self.conversation_display
        d.config(state=NORMAL)
        d.delete("1.0", END)
        d.config(state=DISABLED)
        self._hero_visible = False
        self._rendered_count = 0
        self._stream_active = False
        self.clear_search()

        topic = self.topic_var.get().strip() or DEFAULT_TOPIC
        self.header_topic.config(text=topic)
        self.usage_var.set("0 tok  ·  $0.0000")

        self.chat_manager.start_conversation(topic)

    def validate_selections(self) -> bool:
        if len(self.cast) < 2:
            self.toast("Add at least 2 personas to the cast", "danger")
            return False

        for name in self.cast:
            provider, model = self.persona_model_config.get(name, ("", ""))
            if (not model or model.startswith(("Error", "Loading", "No models", "API key"))):
                self.toast(f"Pick a model for {name}", "danger")
                self._select_cast_member(name)
                return False
        return True

    def setup_chat_manager(self):
        """Wire the chat manager to the current cast/model configuration."""
        selected_personas = []
        selected_clients = []
        selected_models = []

        for name in self.cast:
            persona = next((p for p in self.chat_manager.personas if p.name == name), None)
            if persona:
                selected_personas.append(persona)

            provider_key, model = self.persona_model_config[name]
            client = self.chat_manager.api_clients[provider_key.lower()]

            if provider_key.lower() in PROVIDERS_REQUIRING_KEY:
                client.api_key = self.app_config.get(f"{provider_key.lower()}_api_key", "")
                client.update_headers()

            client.set_model(model)
            selected_clients.append(client)
            selected_models.append(model)

        self.chat_manager.selected_personas = selected_personas
        self.chat_manager.selected_clients = selected_clients
        self.chat_manager.selected_models = selected_models
        self.chat_manager.max_turns = self.max_turns_var.get()
        self.chat_manager.turn_order_strategy = self.turn_order_var.get()

    def toggle_pause(self):
        """Toggle the pause state of the conversation."""
        try:
            if not self.chat_manager.is_running:
                return

            self.chat_manager.is_paused = not self.chat_manager.is_paused
            is_paused = self.chat_manager.is_paused

            def update_ui():
                if is_paused:
                    self.pause_button.config(text="Resume", bootstyle="success")
                    self.narrator_button.config(state=NORMAL)
                    self._set_status_dot("paused")
                    self.update_status("Paused — interject or resume with Space")
                else:
                    self.pause_button.config(text="Pause", bootstyle="warning")
                    self.narrator_button.config(state=DISABLED)
                    self._set_status_dot("running")
                    self.update_status("Conversation resumed")

            if self.winfo_exists():
                self.after_idle(update_ui)

        except Exception as e:
            log.exception("Error toggling pause state")
            self.after_idle(lambda: self.update_status(f"Error toggling pause: {str(e)}"))

    def stop_conversation(self):
        """Stop the current conversation (stage stays put — no screen swap)."""
        self.chat_manager.is_running = False
        self.update_status("Stopping conversation...")
        self.enable_controls(False)

    def enable_controls(self, enabled: bool):
        """Toggle run-state controls. enabled=True means a conversation is live."""
        state = NORMAL if enabled else DISABLED
        self.pause_button.config(state=state)
        self.stop_button.config(state=state)
        self.narrator_button.config(
            state=NORMAL if enabled and self.chat_manager.is_paused else DISABLED)
        self.start_button.config(state=DISABLED if enabled else NORMAL,
                                 text="●  Conversation live…" if enabled else "▶  Start Conversation")
        self._set_status_dot("running" if enabled else "idle")

    def _set_status_dot(self, mode: str):
        colors = {"idle": "#5b6470", "running": "#00bc8c", "paused": "#f39c12", "error": "#e74c3c"}
        self.status_dot.itemconfigure(self._status_dot_item, fill=colors.get(mode, "#5b6470"))

    # ------------------------------------------------------------------ #
    #  Incremental conversation rendering                                 #
    #                                                                     #
    #  The old implementation deleted and re-inserted the ENTIRE          #
    #  transcript on every streaming token (O(n²) work + flicker).        #
    #  This renderer appends only new messages, patches only the          #
    #  in-flight streamed message body, and coalesces stream updates      #
    #  to at most ~30 fps.                                                #
    # ------------------------------------------------------------------ #

    def update_conversation_display(self, is_streaming: bool = False):
        try:
            if not self.winfo_exists():
                return
            if is_streaming:
                self._stream_dirty = True
                if not self._stream_flush_scheduled:
                    self._stream_flush_scheduled = True
                    self.after(33, self._flush_stream_update)
            else:
                self._render_conversation(False)
        except Exception as e:
            log.exception("Error updating conversation display")
            self.update_status(f"Error updating display: {str(e)}")

    def _flush_stream_update(self):
        self._stream_flush_scheduled = False
        if self._stream_dirty:
            self._stream_dirty = False
            try:
                self._render_conversation(True)
            except Exception:
                log.exception("Error during stream render")

    def _render_conversation(self, is_streaming: bool):
        conv = self.chat_manager.conversation
        d = self.conversation_display
        n = len(conv)

        if self._hero_visible or n < self._rendered_count:
            d.config(state=NORMAL)
            d.delete("1.0", END)
            d.config(state=DISABLED)
            self._hero_visible = False
            self._rendered_count = 0
            self._stream_active = False

        if n == 0:
            return

        at_bottom = d.yview()[1] >= 0.98
        d.config(state=NORMAL)

        complete = n - 1 if is_streaming else n

        # An open stream either gets an in-place body patch or is finalized.
        if self._stream_active:
            if is_streaming and self._rendered_count == n - 1:
                self._patch_stream_body(conv[n - 1]["content"], cursor=True)
                d.config(state=DISABLED)
                if at_bottom:
                    d.see(END)
                return
            if self._rendered_count < n:
                self._patch_stream_body(conv[self._rendered_count]["content"], cursor=False)
                self._rendered_count += 1
            self._stream_active = False

        # Append any new complete messages.
        for i in range(self._rendered_count, complete):
            self._append_message(conv[i])
        self._rendered_count = max(self._rendered_count, complete)

        # Open a stream body for the in-flight message.
        if is_streaming and self._rendered_count == n - 1:
            self._append_message_header(conv[n - 1])
            d.mark_set("stream_start", "end-1c")
            d.mark_gravity("stream_start", "left")
            self._stream_tag = self._body_tag_for(conv[n - 1])
            self._stream_active = True
            self._patch_stream_body(conv[n - 1]["content"], cursor=True)

        d.config(state=DISABLED)
        if at_bottom:
            d.see(END)

    def _persona_index(self, msg) -> int:
        for j, p in enumerate(self.chat_manager.selected_personas):
            if msg.get("persona") == p.name:
                return j
        return 0

    def _body_tag_for(self, msg) -> str:
        return f"p{self._persona_index(msg) % len(PERSONA_COLORS)}_body"

    def _append_message_header(self, msg):
        d = self.conversation_display
        idx = self._persona_index(msg) % len(PERSONA_COLORS)
        stamp = datetime.now().strftime("%H:%M")
        d.insert(END, f"{msg['persona']}", f"p{idx}_name")
        d.insert(END, f"   {stamp}\n", "msg_time")

    def _append_message(self, msg):
        d = self.conversation_display
        if msg["role"] in ("system", "narrator"):
            d.insert(END, f"—  {msg['persona']}: {msg['content']}  —\n", "sys_line")
            return
        self._append_message_header(msg)
        d.insert(END, f"{msg['content']}\n", self._body_tag_for(msg))

    def _patch_stream_body(self, content: str, cursor: bool):
        d = self.conversation_display
        d.delete("stream_start", "end-1c")
        d.insert("stream_start", content + ("▌" if cursor else "") + "\n", (self._stream_tag,))

    # ------------------------------------------------------------------ #
    #  Status / progress / usage / typing / toast                         #
    # ------------------------------------------------------------------ #

    def update_status(self, message: str):
        try:
            if self.winfo_exists():
                self.after_idle(lambda: self.status_var.set(message))
        except Exception:
            log.exception("Error updating status")

    def update_usage_display(self, usage_text: str):
        try:
            if self.winfo_exists():
                self.after_idle(lambda: self.usage_var.set(usage_text))
        except Exception:
            log.exception("Error updating usage display")

    def update_progress(self, current: int, maximum: int):
        try:
            if not self.winfo_exists():
                return
            maximum = max(1, maximum)
            self.progress_bar.configure(value=(current / maximum) * 100)
            self.progress_label.config(text=f"turn {current}/{maximum}")
        except Exception:
            log.exception("Error updating progress")

    def show_typing_indicator(self, persona_name: str, actor_index: int):
        try:
            color = PERSONA_COLORS[actor_index % len(PERSONA_COLORS)]
            self.typing_dot.itemconfigure(self._typing_dot_item, fill=color)
            self.typing_dot.pack(side=LEFT, padx=(0, 6))
            self.typing_label.config(text=f"{persona_name} is composing")
            self.typing_label.pack(side=LEFT)
            self._typing_phase = 0
            self._animate_typing(persona_name)
        except Exception:
            log.exception("Error showing typing indicator")

    def _animate_typing(self, persona_name: str):
        if self._typing_job:
            self.after_cancel(self._typing_job)
            self._typing_job = None
        if not self.typing_label.winfo_ismapped():
            return
        dots = "·" * (self._typing_phase % 4)
        self.typing_label.config(text=f"{persona_name} is composing {dots}")
        self._typing_phase += 1
        self._typing_job = self.after(350, lambda: self._animate_typing(persona_name))

    def hide_typing_indicator(self):
        try:
            if self._typing_job:
                self.after_cancel(self._typing_job)
                self._typing_job = None
            self.typing_dot.pack_forget()
            self.typing_label.pack_forget()
        except Exception:
            log.exception("Error hiding typing indicator")

    def toast(self, message: str, style: str = "success"):
        """Non-blocking notification that auto-dismisses (replaces popup spam)."""
        try:
            colors = {
                "success": ("#00bc8c", "#0c2b23"),
                "info": ("#3498db", "#0e2436"),
                "warning": ("#f39c12", "#33240a"),
                "danger": ("#e74c3c", "#360f0b"),
            }
            fg, bg = colors.get(style, colors["info"])
            if self._toast_widget is not None:
                self._toast_widget.destroy()
            if self._toast_job:
                self.after_cancel(self._toast_job)

            lbl = tk.Label(self, text=f"  {message}  ", bg=bg, fg=fg,
                           font=("Helvetica", 10, "bold"), padx=10, pady=8,
                           highlightthickness=1, highlightbackground=fg)
            lbl.place(relx=0.985, rely=0.94, anchor="se")
            self._toast_widget = lbl
            self._toast_job = self.after(2600, self._dismiss_toast)
        except Exception:
            log.exception("Error showing toast")

    def _dismiss_toast(self):
        if self._toast_widget is not None:
            self._toast_widget.destroy()
            self._toast_widget = None
        self._toast_job = None

    # ------------------------------------------------------------------ #
    #  Interjections                                                      #
    # ------------------------------------------------------------------ #

    def add_narrator_message(self):
        """Add a system message to the conversation (while paused)."""
        if not self.chat_manager.is_paused:
            self.toast("Pause the conversation first", "warning")
            return

        message = simpledialog.askstring("System Message", "Enter system message:", parent=self)
        if message:
            system_msg = {"role": "system", "persona": "System", "content": message}
            self.chat_manager.conversation.append(system_msg)
            self.chat_manager._log_message(system_msg)
            self.update_status("System message queued — resume to see the reaction")
            self.update_conversation_display()
            log.info(f"System instruction added: {message}")

    def add_new_topic(self):
        """Steer the conversation to a new topic (while paused)."""
        if not self.chat_manager.is_paused:
            self.toast("Pause the conversation first", "warning")
            return

        dialog = tkb.Toplevel(self)
        dialog.title("New Topic")
        dialog.geometry("420x220")
        dialog.transient(self)
        dialog.grab_set()

        tkb.Label(dialog, text="Steer the conversation toward:").pack(padx=10, pady=(12, 6))
        topic_entry = scrolledtext.ScrolledText(dialog, height=5, width=44)
        topic_entry.pack(padx=10, pady=5)
        topic_entry.focus_set()

        button_frame = tkb.Frame(dialog)
        button_frame.pack(pady=10)

        def submit():
            new_topic = topic_entry.get("1.0", END).strip()
            if new_topic:
                system_msg = {
                    "role": "system",
                    "persona": "System",
                    "content": (
                        f"NEW TOPIC: The conversation should now shift to discussing '{new_topic}'. "
                        "Both participants should acknowledge this topic change naturally and start "
                        "discussing this new topic."
                    )
                }
                self.chat_manager.conversation.append(system_msg)
                self.chat_manager._log_message(system_msg)
                self.header_topic.config(text=new_topic)
                self.update_status("New topic queued — resume to see the shift")
                self.update_conversation_display()
                dialog.destroy()

        tkb.Button(button_frame, text="Steer", command=submit, bootstyle="success").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

    # ------------------------------------------------------------------ #
    #  Persona library                                                    #
    # ------------------------------------------------------------------ #

    def show_persona_library(self):
        """Manage the persona library: add, edit, delete."""
        dialog = tkb.Toplevel(self)
        dialog.title("Persona Library")
        dialog.geometry("560x420")
        dialog.transient(self)

        main = tkb.Frame(dialog, padding="12")
        main.pack(fill=BOTH, expand=True)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        listbox = tk.Listbox(main, bg=CARD_BG, fg=STAGE_FG, selectbackground="#3a4a5c",
                             relief="flat", highlightthickness=0, font=("Helvetica", 10))
        listbox.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        details = scrolledtext.ScrolledText(main, wrap="word", height=14, relief="flat",
                                            bg=STAGE_BG, fg=STAGE_FG, font=SMALL_FONT)
        details.grid(row=0, column=1, sticky="nsew")
        details.config(state=DISABLED)

        def refresh():
            listbox.delete(0, END)
            for p in self.chat_manager.personas:
                listbox.insert(END, p.name)

        def show_details(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            p = self.chat_manager.personas[sel[0]]
            details.config(state=NORMAL)
            details.delete("1.0", END)
            text = f"{p.name}\nAge {p.age} · {p.gender}\n\n{p.personality}"
            if p.fallback_provider:
                text += f"\n\nFallback: {p.fallback_provider} / {p.fallback_model}"
            details.insert(END, text)
            details.config(state=DISABLED)

        listbox.bind("<<ListboxSelect>>", show_details)

        btns = tkb.Frame(main)
        btns.grid(row=1, column=0, columnspan=2, pady=(10, 0))

        def selected_persona():
            sel = listbox.curselection()
            return self.chat_manager.personas[sel[0]] if sel else None

        tkb.Button(btns, text="New", bootstyle="success-outline",
                   command=lambda: self._persona_form(dialog, None, refresh)).pack(side=LEFT, padx=4)
        tkb.Button(btns, text="Edit", bootstyle="info-outline",
                   command=lambda: self._persona_form(dialog, selected_persona(), refresh)).pack(side=LEFT, padx=4)

        def delete():
            p = selected_persona()
            if not p:
                return
            if messagebox.askyesno("Confirm", f"Delete {p.name}?", parent=dialog):
                self.chat_manager.personas = [x for x in self.chat_manager.personas if x.name != p.name]
                self.chat_manager.save_personas()
                if p.name in self.cast:
                    self.cast.remove(p.name)
                    if self.selected_cast_member == p.name:
                        self.selected_cast_member = self.cast[0] if self.cast else None
                    self._render_cast()
                refresh()
                self.toast(f"Deleted {p.name}", "warning")

        tkb.Button(btns, text="Delete", bootstyle="danger-outline", command=delete).pack(side=LEFT, padx=4)
        tkb.Button(btns, text="Close", bootstyle="secondary",
                   command=dialog.destroy).pack(side=RIGHT, padx=4)

        refresh()

    def _persona_form(self, parent, persona: Optional[Persona], on_saved):
        """Shared add/edit persona form (includes fallback model fields)."""
        dialog = tkb.Toplevel(parent)
        dialog.title(f"Edit Persona: {persona.name}" if persona else "New Persona")
        dialog.geometry("520x480")
        dialog.transient(parent)
        dialog.grab_set()

        form = tkb.Frame(dialog, padding="12")
        form.pack(fill=BOTH, expand=True)
        form.grid_columnconfigure(1, weight=1)

        tkb.Label(form, text="Name:").grid(row=0, column=0, sticky="w", pady=4)
        name_entry = tkb.Entry(form)
        name_entry.grid(row=0, column=1, sticky="ew", pady=4)

        tkb.Label(form, text="Age:").grid(row=1, column=0, sticky="w", pady=4)
        age_entry = tkb.Spinbox(form, from_=1, to=150, width=6)
        age_entry.grid(row=1, column=1, sticky="w", pady=4)

        tkb.Label(form, text="Gender:").grid(row=2, column=0, sticky="w", pady=4)
        gender_entry = tkb.Entry(form)
        gender_entry.grid(row=2, column=1, sticky="ew", pady=4)

        tkb.Label(form, text="Personality:").grid(row=3, column=0, sticky="nw", pady=4)
        personality_text = scrolledtext.ScrolledText(form, height=8, width=40)
        personality_text.grid(row=3, column=1, sticky="ew", pady=4)

        tkb.Label(form, text="Fallback provider:").grid(row=4, column=0, sticky="w", pady=4)
        fb_provider_var = tkb.StringVar(value=persona.fallback_provider or "" if persona else "")
        fb_provider = tkb.Combobox(form, textvariable=fb_provider_var,
                                   values=[""] + list(self.chat_manager.api_clients.keys()),
                                   state="readonly", width=14)
        fb_provider.grid(row=4, column=1, sticky="w", pady=4)

        tkb.Label(form, text="Fallback model:").grid(row=5, column=0, sticky="w", pady=4)
        fb_model_entry = tkb.Entry(form)
        fb_model_entry.grid(row=5, column=1, sticky="ew", pady=4)

        if persona:
            name_entry.insert(0, persona.name)
            age_entry.set(persona.age)
            gender_entry.insert(0, persona.gender)
            personality_text.insert("1.0", persona.personality)
            if persona.fallback_model:
                fb_model_entry.insert(0, persona.fallback_model)
        else:
            age_entry.set(25)

        def submit():
            name = name_entry.get().strip()
            gender = gender_entry.get().strip()
            personality = personality_text.get("1.0", END).strip()
            try:
                age = int(age_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Age must be a number.", parent=dialog)
                return
            if not (name and gender and personality):
                messagebox.showerror("Error", "Please fill in name, gender and personality.", parent=dialog)
                return

            fb_prov = fb_provider_var.get().strip() or None
            fb_model = fb_model_entry.get().strip() or None

            if persona:
                old_name = persona.name
                persona.name = name
                persona.age = age
                persona.gender = gender
                persona.personality = personality
                persona.fallback_provider = fb_prov
                persona.fallback_model = fb_model
                if old_name != name:
                    if old_name in self.cast:
                        self.cast[self.cast.index(old_name)] = name
                    if old_name in self.persona_model_config:
                        self.persona_model_config[name] = self.persona_model_config.pop(old_name)
                    if self.selected_cast_member == old_name:
                        self.selected_cast_member = name
                self.toast(f"Updated {name}")
            else:
                self.chat_manager.personas.append(
                    Persona(name, personality, age, gender, fb_prov, fb_model))
                self.toast(f"Added {name} to the library")

            self.chat_manager.save_personas()
            self._render_cast()
            on_saved()
            dialog.destroy()

        btns = tkb.Frame(form)
        btns.grid(row=6, column=0, columnspan=2, pady=12)
        tkb.Button(btns, text="Save", command=submit, bootstyle="success").pack(side=LEFT, padx=5)
        tkb.Button(btns, text="Cancel", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

    # ------------------------------------------------------------------ #
    #  Templates                                                          #
    # ------------------------------------------------------------------ #

    def refresh_templates(self):
        try:
            templates = list_templates()
            self.template_combo['values'] = ["None"] + [t.name for t in templates]
        except Exception as e:
            log.error(f"Error refreshing templates: {e}")
            self.template_combo['values'] = ["None"]

    def _on_template_selected(self, event=None):
        name = self.template_var.get()
        if name == "None":
            return
        templates = list_templates()
        template = next((t for t in templates if t.name == name), None)
        if not template:
            self.toast(f"Template '{name}' not found", "danger")
            return

        self.topic_var.set(template.initial_topic)
        self.max_turns_var.set(template.max_turns)

        # Adopt template personas when they exist in the library
        library = {p.name for p in self.chat_manager.personas}
        wanted = [template.persona1_name, template.persona2_name]
        if all(w in library for w in wanted):
            self.cast = list(wanted)
            for n in self.cast:
                self.persona_model_config.setdefault(n, ("ollama", ""))
            self._select_cast_member(self.cast[0])

        self.toast(f"Template applied: {name}", "info")

    def save_current_as_template(self):
        if len(self.cast) < 2:
            self.toast("Need at least 2 cast members to save a template", "warning")
            return

        dialog = tkb.Toplevel(self)
        dialog.title("Save Template")
        dialog.geometry("400x320")
        dialog.transient(self)
        dialog.grab_set()

        tkb.Label(dialog, text="Template Name:").pack(padx=10, pady=(12, 2))
        name_entry = tkb.Entry(dialog, width=40)
        name_entry.pack(padx=10, pady=4)

        tkb.Label(dialog, text="Description:").pack(padx=10, pady=2)
        desc_text = scrolledtext.ScrolledText(dialog, height=4, width=40)
        desc_text.pack(padx=10, pady=4)

        tkb.Label(dialog, text="Category:").pack(padx=10, pady=2)
        category_var = tkb.StringVar(value="custom")
        tkb.Combobox(dialog, textvariable=category_var,
                     values=["custom", "debate", "interview", "brainstorming",
                             "tutoring", "storytelling"]).pack(padx=10, pady=4)

        def save():
            name = name_entry.get().strip()
            description = desc_text.get("1.0", END).strip()
            if not name or not description:
                messagebox.showerror("Error", "Please provide name and description.", parent=dialog)
                return
            template = ConversationTemplate(
                name=name,
                description=description,
                persona1_name=self.cast[0],
                persona2_name=self.cast[1],
                initial_topic=self.topic_var.get(),
                max_turns=self.max_turns_var.get(),
                category=category_var.get()
            )
            if save_template(template):
                self.refresh_templates()
                self.toast(f"Template saved: {name}")
                dialog.destroy()
            else:
                messagebox.showerror("Error", "Failed to save template.", parent=dialog)

        btns = tkb.Frame(dialog)
        btns.pack(pady=10)
        tkb.Button(btns, text="Save", command=save, bootstyle="success").pack(side=LEFT, padx=5)
        tkb.Button(btns, text="Cancel", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

    # ------------------------------------------------------------------ #
    #  In-conversation search                                             #
    # ------------------------------------------------------------------ #

    def toggle_search_bar(self, focus: bool = False):
        if self.search_frame.winfo_ismapped():
            self.search_frame.grid_remove()
        else:
            self.search_frame.grid()
            if focus or True:
                self.search_entry.focus_set()

    def search_conversation(self):
        """Search for text in the conversation display."""
        query = self.search_var.get()
        if not query:
            return

        self.conversation_display.tag_remove("search_highlight", "1.0", END)
        self.conversation_display.tag_remove("current_match", "1.0", END)
        self.search_matches = []
        self.current_search_index = -1

        use_regex = self.regex_var.get()
        case_sensitive = self.case_sensitive_var.get()

        start_pos = "1.0"
        while True:
            pos = self.conversation_display.search(
                query, start_pos, END,
                regexp=use_regex,
                nocase=not case_sensitive
            )
            if not pos:
                break
            end_pos = f"{pos}+{len(query)}c"
            self.search_matches.append((pos, end_pos))
            self.conversation_display.tag_add("search_highlight", pos, end_pos)
            start_pos = end_pos

        if self.search_matches:
            self.current_search_index = 0
            self._highlight_current_match()
        else:
            self.search_result_label.config(text="No matches")

    def search_next(self):
        if not self.search_matches:
            return
        self.current_search_index = (self.current_search_index + 1) % len(self.search_matches)
        self._highlight_current_match()

    def search_prev(self):
        if not self.search_matches:
            return
        self.current_search_index = (self.current_search_index - 1) % len(self.search_matches)
        self._highlight_current_match()

    def _highlight_current_match(self):
        if not self.search_matches or self.current_search_index < 0:
            return
        self.conversation_display.tag_remove("current_match", "1.0", END)
        pos, end_pos = self.search_matches[self.current_search_index]
        self.conversation_display.tag_add("current_match", pos, end_pos)
        self.conversation_display.see(pos)
        self.search_result_label.config(
            text=f"{self.current_search_index + 1} of {len(self.search_matches)}")

    def clear_search(self):
        self.conversation_display.tag_remove("search_highlight", "1.0", END)
        self.conversation_display.tag_remove("current_match", "1.0", END)
        self.search_matches = []
        self.current_search_index = -1
        self.search_var.set("")
        self.search_result_label.config(text="")

    # ------------------------------------------------------------------ #
    #  History browser & stats                                            #
    # ------------------------------------------------------------------ #

    def show_history_browser(self):
        """Show the conversation history browser."""
        dialog = tkb.Toplevel(self)
        dialog.title("Conversation History")
        dialog.geometry("900x600")
        dialog.transient(self)

        main_frame = tkb.Frame(dialog, padding="10")
        main_frame.pack(fill=BOTH, expand=True)

        search_frame = tkb.Frame(main_frame)
        search_frame.pack(fill=X, pady=(0, 10))

        tkb.Label(search_frame, text="Search:").pack(side=LEFT, padx=5)
        search_var = tkb.StringVar()
        search_entry = tkb.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side=LEFT, fill=X, expand=True, padx=5)

        favorites_var = tkb.BooleanVar(value=False)
        tkb.Checkbutton(search_frame, text="Favorites Only", variable=favorites_var).pack(side=LEFT, padx=5)

        def refresh_list():
            for item in tree.get_children():
                tree.delete(item)
            conversations = self.chat_manager.history_manager.list_conversations(
                limit=100,
                search_query=search_var.get() if search_var.get() else None,
                favorites_only=favorites_var.get()
            )
            for conv in conversations:
                timestamp = datetime.fromisoformat(conv['timestamp']).strftime('%Y-%m-%d %H:%M')
                favorite_icon = "★" if conv['is_favorite'] else ""
                tree.insert('', 'end', iid=conv['id'], values=(
                    conv['id'], timestamp, conv['theme'],
                    f"{conv['persona1']} vs {conv['persona2']}",
                    conv['turn_count'], favorite_icon
                ))

        tkb.Button(search_frame, text="Search", command=refresh_list, bootstyle="info").pack(side=LEFT, padx=5)
        tkb.Button(search_frame, text="Refresh", command=refresh_list, bootstyle="secondary").pack(side=LEFT, padx=5)
        search_entry.bind("<Return>", lambda e: refresh_list())

        tree_frame = tkb.Frame(main_frame)
        tree_frame.pack(fill=BOTH, expand=True)

        columns = ('ID', 'Date', 'Theme', 'Participants', 'Turns', 'Fav')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        for col, width in zip(columns, (50, 130, 200, 200, 80, 50)):
            tree.heading(col, text=col)
            tree.column(col, width=width)

        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        button_frame = tkb.Frame(main_frame)
        button_frame.pack(fill=X, pady=(10, 0))

        def view_conversation():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("Info", "Please select a conversation to view.", parent=dialog)
                return
            conv_id = int(selection[0])
            conv_data = self.chat_manager.history_manager.get_conversation(conv_id)
            if not conv_data:
                messagebox.showerror("Error", "Failed to load conversation.", parent=dialog)
                return

            viewer = tkb.Toplevel(dialog)
            viewer.title(f"Conversation #{conv_id} - {conv_data['metadata']['theme']}")
            viewer.geometry("800x600")

            meta_frame = tkb.LabelFrame(viewer, text="Metadata", padding="10")
            meta_frame.pack(fill=X, padx=10, pady=10)

            meta_text = f"Date: {datetime.fromisoformat(conv_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            meta_text += f"Theme: {conv_data['metadata']['theme']}\n"
            meta_text += f"Participants: {conv_data['metadata']['persona1']} vs {conv_data['metadata']['persona2']}\n"
            meta_text += f"Models: {conv_data['metadata']['model1']} vs {conv_data['metadata']['model2']}\n"
            meta_text += f"Turns: {conv_data['metadata']['turn_count']}"
            tkb.Label(meta_frame, text=meta_text, justify=LEFT).pack()

            conv_frame = tkb.LabelFrame(viewer, text="Conversation", padding="10")
            conv_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

            conv_text = scrolledtext.ScrolledText(conv_frame, wrap="word", height=20)
            conv_text.pack(fill=BOTH, expand=True)
            for msg in conv_data['conversation']:
                conv_text.insert(END, f"{msg['persona']} ({msg['role']}):\n{msg['content']}\n\n")
            conv_text.config(state=DISABLED)

            tkb.Button(viewer, text="Close", command=viewer.destroy, bootstyle="secondary").pack(pady=10)

        def toggle_favorite():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("Info", "Please select a conversation.", parent=dialog)
                return
            self.chat_manager.history_manager.toggle_favorite(int(selection[0]))
            refresh_list()

        def delete_conversation():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("Info", "Please select a conversation to delete.", parent=dialog)
                return
            conv_id = int(selection[0])
            if messagebox.askyesno("Confirm", f"Delete conversation #{conv_id}?", parent=dialog):
                self.chat_manager.history_manager.delete_conversation(conv_id)
                refresh_list()

        tkb.Button(button_frame, text="View", command=view_conversation, bootstyle="info").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Toggle Favorite", command=toggle_favorite, bootstyle="warning").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Delete", command=delete_conversation, bootstyle="danger").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Close", command=dialog.destroy, bootstyle="secondary").pack(side=RIGHT, padx=5)

        refresh_list()

    def show_history_stats(self):
        """Show conversation history statistics."""
        stats = self.chat_manager.history_manager.get_statistics()

        stats_text = "Conversation History Statistics\n"
        stats_text += "=" * 40 + "\n\n"
        stats_text += f"Total Conversations: {stats['total_conversations']}\n"
        stats_text += f"Total Messages: {stats['total_messages']}\n"
        stats_text += f"Favorite Conversations: {stats['favorite_count']}\n\n"
        stats_text += "Top Personas:\n"
        for persona, count in stats['top_personas'][:5]:
            stats_text += f"  - {persona}: {count} conversations\n"

        messagebox.showinfo("History Statistics", stats_text, parent=self)

    # ------------------------------------------------------------------ #
    #  Usage dashboard                                                    #
    # ------------------------------------------------------------------ #

    def show_usage_dashboard(self):
        """Token/cost breakdown per provider and model, with CSV export."""
        dialog = tkb.Toplevel(self)
        dialog.title("Usage & Costs")
        dialog.geometry("640x420")
        dialog.transient(self)

        main = tkb.Frame(dialog, padding="12")
        main.pack(fill=BOTH, expand=True)

        totals = self.chat_manager.usage_tracker.get_total_usage()
        header = (f"All time:  {totals['call_count']} calls · "
                  f"{totals['total_tokens']:,} tokens · ${totals['estimated_cost']:.4f}")
        tkb.Label(main, text=header, font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(0, 8))

        columns = ('Provider', 'Model', 'Calls', 'Tokens', 'Cost')
        tree = ttk.Treeview(main, columns=columns, show='headings', height=12)
        for col, width in zip(columns, (100, 220, 70, 100, 90)):
            tree.heading(col, text=col)
            tree.column(col, width=width)
        tree.pack(fill=BOTH, expand=True)

        for row in self.chat_manager.usage_tracker.get_usage_by_model():
            tree.insert('', 'end', values=(
                row['provider'], row['model'], row['call_count'],
                f"{row['total_tokens']:,}", f"${row['estimated_cost']:.4f}"
            ))

        btns = tkb.Frame(main)
        btns.pack(fill=X, pady=(10, 0))

        def export_csv():
            filepath = filedialog.asksaveasfilename(
                title="Export Usage CSV", defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")], parent=dialog)
            if filepath:
                if self.chat_manager.usage_tracker.export_usage_to_csv(filepath):
                    self.toast(f"Usage exported to {os.path.basename(filepath)}")
                else:
                    messagebox.showerror("Error", "Failed to export usage data.", parent=dialog)

        tkb.Button(btns, text="Export CSV", command=export_csv, bootstyle="info-outline").pack(side=LEFT)
        tkb.Button(btns, text="Close", command=dialog.destroy, bootstyle="secondary").pack(side=RIGHT)

    # ------------------------------------------------------------------ #
    #  Help                                                               #
    # ------------------------------------------------------------------ #

    def show_shortcuts(self):
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "Ctrl+N\tNew conversation\n"
            "Ctrl+S / Ctrl+E\tSave / Export\n"
            "Space\tPause / Resume\n"
            "Ctrl+Q\tStop conversation\n"
            "Ctrl+T\tInterject new topic (while paused)\n"
            "Ctrl+F\tSearch in conversation\n"
            "Escape\tClose search",
            parent=self
        )

    def show_about(self):
        messagebox.showinfo(
            "About Auto Chat Studio",
            "Auto Chat Studio\n\n"
            "A single-window studio for AI-to-AI conversations across "
            "Ollama, LM Studio, OpenAI and OpenRouter.",
            parent=self
        )


def main():
    """Main entry point for the application."""
    app = ChatApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nChat session terminated by user")
        sys.exit(0)
    except Exception as e:
        log.exception("Unhandled exception")
        messagebox.showerror("Error", f"Unhandled error: {str(e)}")
        sys.exit(1)
