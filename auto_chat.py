#!/usr/bin/env python3
"""
tkinter_chat.py - A GUI application for AI-to-AI conversations

Enables turn-based conversations between two AI personas using different
Large Language Models (LLMs) via APIs like Ollama, LM Studio, and
OpenAI-compatible endpoints.

Features:
- Dual AI conversation with different models
- Multiple LLM API support
- Persona management
- Tkinter GUI interface
- Conversation logging and export
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
from utils.config_utils import load_jsonc
from utils.analytics import summarize_conversation
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
from ttkbootstrap.constants import * # For constants like tk.NORMAL, tk.DISABLED etc.

# Load environment variables from .env file (for API keys)
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="[%X]",
)
log = logging.getLogger("tkinter_chat")

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

# --- Configuration Loading/Saving ---

def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file allowing comments."""
    if os.path.exists(CONFIG_FILE):
        try:
            return load_jsonc(CONFIG_FILE)
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
            "openai": OpenAIClient(api_key="")  # Add OpenAI client
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
        self.turn_order_strategy = "round-robin"  # Options: "round-robin", "random"
        self.use_streaming = True  # Enable response streaming by default

    def load_personas(self):
        """Load personas from the JSON file."""
        try:
            if os.path.exists(PERSONAS_FILE):
                personas_data = load_jsonc(PERSONAS_FILE)
                # Check if the loaded data is a list or a dictionary
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
                self.save_personas()  # Save defaults
        except Exception as e:
            log.exception(f"Error loading personas: {e}")
            messagebox.showerror("Error", f"Failed to load personas from {PERSONAS_FILE}: {e}")
            self.personas = [] # Ensure personas list is empty on error

    def save_personas(self):
        """Save current personas to the JSON file."""
        try:
            with open(PERSONAS_FILE, 'w', encoding='utf-8') as f:
                json.dump([p.to_dict() for p in self.personas], f, indent=4)
            log.info(f"Saved {len(self.personas)} personas to {PERSONAS_FILE}")
        except Exception as e:
            log.exception(f"Error saving personas: {e}")
            messagebox.showerror("Error", f"Failed to save personas to {PERSONAS_FILE}: {e}")

    # --- Methods to be implemented later --- 
    def save_conversation(self):
        """Save the current conversation log to a file."""
        if not self.conversation:
            messagebox.showinfo("Info", "No conversation to save.", parent=self.app)
            return

        filepath = filedialog.asksaveasfilename(
            title="Save Conversation Log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("JSON files", "*.json"), ("All files", "*.*")],
            parent=self.app
        )

        if not filepath:
            return # User cancelled

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                if filepath.endswith(".json"):
                    json.dump(self.conversation, f, indent=4)
                else:
                    # Save as plain text
                    f.write(f"Conversation Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Theme: {self.conversation_theme}\n")
                    f.write(f"Personas: {', '.join([p.name for p in self.selected_personas])}\n")
                    f.write(f"Models: {', '.join(self.selected_models)}\n")
                    f.write(f"Turn Order: {self.turn_order_strategy}\n")
                    f.write("-" * 20 + "\n\n")
                    for msg in self.conversation:
                        f.write(f"{msg['persona']} ({msg['role']}):\n{msg['content']}\n\n")
            log.info(f"Conversation saved to {filepath}")
            messagebox.showinfo("Success", f"Conversation saved to {filepath}", parent=self.app)
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

        # Ensure selected components are valid
        if len(self.selected_personas) < 2 or len(self.selected_clients) < 2:
            messagebox.showerror("Error", "Setup incomplete. Please select at least two personas and their models.", parent=self.app)
            self.is_running = False
            return

        if len(self.selected_personas) != len(self.selected_clients):
            messagebox.showerror("Error", "Number of personas and clients must match.", parent=self.app)
            self.is_running = False
            return

        log.info(f"Starting conversation. Theme: '{theme}'")
        log.info(f"Turn order strategy: {self.turn_order_strategy}")
        for i, persona in enumerate(self.selected_personas):
            log.info(f"Persona {i+1}: {persona.name} ({self.selected_clients[i].name} - {self.selected_models[i]})")
        log.info(f"Max turns: {self.max_turns}")

        # Update GUI status
        self.app.after(0, self.app.update_status, "Conversation starting...")
        self.app.after(0, self.app.enable_controls, True)
        # Use lambdas for config calls via after
        self.app.after(0, lambda: self.app.pause_button.config(text="Pause", bootstyle="warning")) 
        self.app.after(0, lambda: self.app.narrator_button.config(state=DISABLED, bootstyle="secondary-disabled"))

        # Start the conversation loop in a new thread
        self.chat_thread = threading.Thread(target=self._run_conversation_loop, daemon=True)
        self.chat_thread.start()

    def _run_conversation_loop(self):
        """The main loop where the conversation happens."""
        log.info("Conversation loop started.")
        try:
            last_message_content = "Let's start the conversation." # Initial prompt for the first AI
            system_message_added = False

            while self.is_running and self.current_turn < self.max_turns:
                # --- Pause Handling ---
                while self.is_paused and self.is_running:
                    time.sleep(0.1) # Reduced sleep time for more responsive pause
                    if not self.is_running: # Check if stopped while paused
                         break
                
                if not self.is_running: # Exit loop if stopped
                    break
                    
                # --- Check for System Messages ---
                recent_system_messages = [
                    msg for msg in self.conversation[-3:] 
                    if msg["role"] in ["system", "narrator"]
                ]
                
                # --- Determine Current Actor ---
                if self.turn_order_strategy == "random":
                    actor_index = random.randint(0, len(self.selected_personas) - 1)
                else:  # round-robin (default)
                    actor_index = self.current_turn % len(self.selected_personas)

                current_persona = self.selected_personas[actor_index]
                current_client = self.selected_clients[actor_index]
                
                # Update status on main thread
                self.app.after(0, self.app.update_status, f"Turn {self.current_turn + 1}/{self.max_turns}: {current_persona.name} is thinking...")
                log.debug(f"Turn {self.current_turn + 1}: '{current_persona.name}' is thinking...")

                # --- Prepare API Request --- 
                try:
                    # Format conversation history for API
                    api_history = []
                    history_start_index = max(0, len(self.conversation) - self.history_limit)
                    
                    for msg in self.conversation[history_start_index:]:
                        if msg["role"] == "system":
                            # Add system messages with emphasis
                            api_history.append({
                                "role": "system",
                                "content": f"IMPORTANT - MUST ACKNOWLEDGE AND REACT TO THIS IMMEDIATELY: {msg['content']}"
                            })
                        elif msg["role"] == "narrator":
                            # Add narrator messages as urgent system messages
                            api_history.append({
                                "role": "system",
                                "content": f"URGENT SCENE CHANGE - REACT TO THIS IMMEDIATELY: {msg['content']}"
                            })
                        elif msg["role"] in ("assistant", "user"):
                            # Map messages from the current persona as 'assistant' and the other as 'user'
                            role = "assistant" if msg["persona"] == current_persona.name else "user"
                            api_history.append({"role": role, "content": msg["content"]})
                        else:
                            api_history.append({"role": "user", "content": msg["content"]})

                    # Get base system prompt
                    system_prompt = current_persona.get_system_prompt(self.conversation_theme)
                    
                    # Modify prompt if there are recent system messages
                    if recent_system_messages:
                        last_system = recent_system_messages[-1]
                        # Inject the system message directly into the prompt
                        prompt = f"EMERGENCY ALERT - {last_system['content']}\n\nYou MUST acknowledge and react to this situation immediately before continuing any previous conversation. How do you respond to this urgent situation?"
                        
                        # Add emphasis to system prompt
                        system_prompt = system_prompt + "\n\nCRITICAL INSTRUCTION: When you receive an emergency alert or system message, you MUST:\n1. Immediately acknowledge and react to the situation\n2. Show appropriate urgency and emotion in your response\n3. Take appropriate action based on the emergency\n4. Temporarily pause any ongoing conversation topics\n5. Focus entirely on the current situation until it is resolved"
                    else:
                        prompt = last_message_content
                    
                    # Log what's being sent to the API
                    log.info(f"Sending to API - System Prompt: {system_prompt[:100]}...")
                    log.info(f"Sending to API - Current Prompt: {prompt[:100]}...")
                    log.info(f"Sending to API - History Length: {len(api_history)}")
                    
                    # --- Call API (with streaming if enabled) ---
                    start_time = time.time()

                    if self.use_streaming:
                        # Use streaming API
                        response_content = ""
                        try:
                            # Create placeholder message
                            new_role = "assistant" if actor_index == 0 else "user"
                            new_msg = {
                                "role": new_role,
                                "persona": current_persona.name,
                                "content": ""
                            }
                            self.conversation.append(new_msg)

                            # Stream the response
                            for chunk in current_client.generate_response_stream(
                                prompt=prompt,
                                system=system_prompt,
                                conversation_history=api_history
                            ):
                                if not self.is_running:
                                    break

                                response_content += chunk
                                # Update the message content
                                new_msg["content"] = response_content

                                # Update GUI periodically (every chunk)
                                self.app.after(0, self.app.update_conversation_display)

                            # Clean the final response
                            response_content = response_content.strip()
                            response_content = self._clean_model_response(response_content)
                            new_msg["content"] = response_content

                        except Exception as stream_error:
                            log.warning(f"Streaming failed, falling back to non-streaming: {stream_error}")
                            # Remove placeholder message
                            if new_msg in self.conversation:
                                self.conversation.remove(new_msg)

                            # Fall back to non-streaming
                            response_content = current_client.generate_response(
                                prompt=prompt,
                                system=system_prompt,
                                conversation_history=api_history
                            )
                            response_content = response_content.strip()
                            response_content = self._clean_model_response(response_content)

                            # Create and add message
                            new_msg = {
                                "role": new_role,
                                "persona": current_persona.name,
                                "content": response_content
                            }
                            self.conversation.append(new_msg)

                    else:
                        # Use non-streaming API
                        response_content = current_client.generate_response(
                            prompt=prompt,
                            system=system_prompt,
                            conversation_history=api_history
                        )
                        response_content = response_content.strip()
                        response_content = self._clean_model_response(response_content)

                        # Create and add new message
                        new_role = "assistant" if actor_index == 0 else "user"
                        new_msg = {
                            "role": new_role,
                            "persona": current_persona.name,
                            "content": response_content
                        }
                        self.conversation.append(new_msg)

                    end_time = time.time()
                    log.debug(f"'{current_persona.name}' generated response in {end_time - start_time:.2f} seconds.")

                    if not self.is_running: # Check if stopped during API call
                        break

                    # Log the message
                    self._log_message(new_msg)
                    last_message_content = response_content

                    # Update GUI on main thread
                    self.app.after(0, self.app.update_conversation_display)
                    self.app.after(0, self.app.update_status, f"Turn {self.current_turn + 1}/{self.max_turns}: Waiting...")

                    # Increment turn
                    self.current_turn += 1

                    # Small delay between turns, but check is_running frequently
                    for _ in range(10):  # Split 1 second delay into 10 parts
                        if not self.is_running:
                            break
                        time.sleep(0.1)

                except APIKeyMissingError as e:
                    log.error(f"API key error during turn {self.current_turn + 1}: {e}")
                    error_msg = f"API Key Error: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    self.app.after(0, messagebox.showerror, "API Key Error", str(e))
                    self.is_running = False
                    break
                except ModelNotSetError as e:
                    log.error(f"Model not set error during turn {self.current_turn + 1}: {e}")
                    error_msg = f"Model Error: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    self.is_running = False
                    break
                except APIRequestError as e:
                    log.error(f"API request error during turn {self.current_turn + 1}: {e}")
                    error_msg = f"API Request Error during {current_persona.name}'s turn: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    # Continue to next turn instead of stopping the conversation
                    self.current_turn += 1
                    continue
                except Exception as e:
                    log.exception(f"Unexpected error during turn {self.current_turn + 1}")
                    error_msg = f"Unexpected error during {current_persona.name}'s turn: {str(e)}"
                    self.app.after(0, self.app.update_status, error_msg)
                    self.is_running = False
                    break

            # --- Conversation End --- 
            final_status = "Conversation finished (Max turns reached)." if self.current_turn >= self.max_turns else "Conversation stopped."
            log.info(final_status)
            
            # Schedule final UI updates on main thread
            self.app.after(0, self.app.update_status, final_status)
            self.app.after(0, self.app.enable_controls, False)
            self.app.after(0, lambda: self.app.pause_button.config(text="Pause", bootstyle="warning"))

        except Exception as e:
            log.exception("Fatal error in conversation loop")
            self.app.after(0, self.app.update_status, f"Fatal error: {str(e)}")
            self.app.after(0, self.app.enable_controls, False)
        finally:
            self.is_running = False
            summary = summarize_conversation(self.conversation)
            log.info("Conversation summary:\n" + summary)
            log.info("Conversation loop finished.")

    def _clean_model_response(self, text: str) -> str:
        """Remove common UI instructions from model responses."""
        # List of patterns to remove
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
        
        # Check for each pattern case-insensitively and remove it
        cleaned_text = text
        for pattern in patterns:
            # Try with variations of separators and punctuation
            for variant in [pattern, pattern + ".", pattern + "!", pattern + ","]:
                cleaned_text = cleaned_text.replace(variant, "")
                cleaned_text = cleaned_text.replace(variant.lower(), "")
                cleaned_text = cleaned_text.replace(variant.upper(), "")
        
        # Remove any trailing whitespace, newlines, etc. that might be left
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text

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
        self.app.after(0, self.app.update_conversation_display) # Update GUI from main thread
        log.info(f"Narrator message added: {message}")

    def add_system_instruction(self, instruction: str):
        """Add a system instruction to guide the conversation."""
        if not instruction:
            return
            
        # Create system instruction message
        system_msg = {
            "role": "system",
            "persona": "System",
            "content": instruction
        }
        
        # Add to conversation
        self.conversation.append(system_msg)
        self._log_message(system_msg)
        
        # Update GUI
        self.app.after(0, self.app.update_conversation_display)
        log.info(f"System instruction added: {instruction}")
        
        # If conversation is paused, this will be picked up when resumed
        # If running, it will affect the next turn

    def _log_message(self, msg_data: Dict[str, str]):
        """Append a message to the global log file."""
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
                f.write(f"{timestamp} {msg_data['persona']} ({msg_data['role']}): {msg_data['content']}\n")
        except Exception as e:
            log.error(f"Failed to write to log file {LOG_FILE}: {e}")


class ChatApp(tkb.Window):
    """Main application window for the chat interface using ttkbootstrap."""

    def __init__(self):
        # Initialize with a dark theme
        super().__init__(themename=DEFAULT_THEME)

        # Configure the main window
        self.title("AI Chat - ttkbootstrap Edition")
        self.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        
        # Initialize the chat manager
        self.chat_manager = ChatManager(self)
        
        # Load config early for model defaults
        self.app_config = load_config()
        
        # Configure the grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Create main frame with padding
        self.main_frame = tkb.Frame(self, padding="20")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # Create menu
        self.create_menu()
        
        # Start with setup screen
        self.show_setup_screen()
    
    def create_menu(self):
        """Create the application menu."""
        menubar = tkb.Menu(self)
        
        # File menu
        file_menu = tkb.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Conversation", command=self.show_setup_screen)
        file_menu.add_command(label="Save Conversation", command=self.chat_manager.save_conversation)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Help menu
        help_menu = tkb.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.config(menu=menubar)
    
    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About AI Chat",
            "AI Chat - ttkbootstrap Edition\n\n"
            "A GUI application for AI-to-AI conversations using different LLM APIs."
        )
    
    def show_setup_screen(self):
        """Show the initial setup screen for selecting personas and models."""
        # Clear the main frame
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        
        # Create setup frame with padding
        setup_frame = tkb.Frame(self.main_frame, padding="20")
        setup_frame.grid(row=0, column=0, sticky="nsew")
        setup_frame.grid_columnconfigure(0, weight=1)
        
        # Title with larger font
        title_label = tkb.Label(
            setup_frame, 
            text="AI Chat Setup", 
            font=("-size 16 -weight bold") # ttkbootstrap font syntax
        )
        title_label.grid(row=0, column=0, pady=20)
        
        # Create a notebook for tabbed interface with padding
        notebook = tkb.Notebook(setup_frame, padding="10")
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Personas tab
        personas_frame = tkb.Frame(notebook, padding="10")
        notebook.add(personas_frame, text="Select Personas")
        
        # Models tab
        models_frame = tkb.Frame(notebook, padding="10")
        notebook.add(models_frame, text="Select Models")
        
        # Options tab
        options_frame = tkb.Frame(notebook, padding="10")
        notebook.add(options_frame, text="Options")
        
        # Set up personas selection
        self.setup_personas_tab(personas_frame)
        
        # Set up models selection
        self.setup_models_tab(models_frame)
        
        # Set up options
        self.setup_options_tab(options_frame)
        
        # Start button at the bottom with accent color
        start_button = tkb.Button(
            setup_frame, 
            text="Start Conversation", 
            command=self.start_conversation,
            bootstyle="success-lg" # Use bootstyle for appearance
        )
        start_button.grid(row=2, column=0, pady=20)
        
    def setup_personas_tab(self, parent):
        """Set up the personas selection tab with support for multiple personas."""
        # Load personas if not already loaded
        if not self.chat_manager.personas:
            self.chat_manager.load_personas()

        # Configure grid
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        # Left side: Available personas
        available_frame = tkb.LabelFrame(parent, text="Available Personas", padding="10")
        available_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Listbox for available personas
        available_scroll = tkb.Scrollbar(available_frame)
        available_scroll.pack(side=RIGHT, fill=tkb.Y)

        self.available_personas_list = tk.Listbox(available_frame, yscrollcommand=available_scroll.set, height=10)
        self.available_personas_list.pack(side=LEFT, fill=tkb.BOTH, expand=True)
        available_scroll.config(command=self.available_personas_list.yview)

        # Populate available personas
        for persona in self.chat_manager.personas:
            self.available_personas_list.insert(END, persona.name)

        # Management buttons
        management_frame = tkb.Frame(parent)
        management_frame.grid(row=1, column=0, pady=10)

        tkb.Button(management_frame, text="Add New", command=self.add_persona, bootstyle="info-outline").pack(side=LEFT, padx=5)
        tkb.Button(management_frame, text="Edit Sel.", command=self.edit_persona, bootstyle="secondary-outline").pack(side=LEFT, padx=5)
        tkb.Button(management_frame, text="Delete Sel.", command=self.delete_persona, bootstyle="danger-outline").pack(side=LEFT, padx=5)

        # Right side: Selected personas for conversation
        selected_frame = tkb.LabelFrame(parent, text="Selected for Conversation (2-10)", padding="10")
        selected_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        # Listbox for selected personas
        selected_scroll = tkb.Scrollbar(selected_frame)
        selected_scroll.pack(side=RIGHT, fill=tkb.Y)

        self.selected_personas_list = tk.Listbox(selected_frame, yscrollcommand=selected_scroll.set, height=10)
        self.selected_personas_list.pack(side=LEFT, fill=tkb.BOTH, expand=True)
        selected_scroll.config(command=self.selected_personas_list.yview)

        # Add/Remove buttons
        buttons_frame = tkb.Frame(parent)
        buttons_frame.grid(row=1, column=1, pady=10)

        tkb.Button(buttons_frame, text="Add >>", command=self.add_persona_to_conversation, bootstyle="success-outline").pack(side=LEFT, padx=5)
        tkb.Button(buttons_frame, text="<< Remove", command=self.remove_persona_from_conversation, bootstyle="danger-outline").pack(side=LEFT, padx=5)
        tkb.Button(buttons_frame, text="Move Up", command=self.move_persona_up, bootstyle="info-outline").pack(side=LEFT, padx=5)
        tkb.Button(buttons_frame, text="Move Down", command=self.move_persona_down, bootstyle="info-outline").pack(side=LEFT, padx=5)

        # Initialize with 2 default personas if available
        self.conversation_personas = []
        if len(self.chat_manager.personas) >= 2:
            self.conversation_personas = [
                self.chat_manager.personas[0].name,
                self.chat_manager.personas[1].name
            ]
            self.update_selected_personas_list()
    
    def update_selected_personas_list(self):
        """Update the selected personas listbox."""
        self.selected_personas_list.delete(0, END)
        for persona_name in self.conversation_personas:
            self.selected_personas_list.insert(END, persona_name)

    def add_persona_to_conversation(self):
        """Add selected persona from available list to conversation."""
        selection = self.available_personas_list.curselection()
        if not selection:
            messagebox.showinfo("Info", "Please select a persona to add.")
            return

        persona_name = self.available_personas_list.get(selection[0])

        # Check if already added
        if persona_name in self.conversation_personas:
            messagebox.showinfo("Info", f"{persona_name} is already in the conversation.")
            return

        # Check max limit
        if len(self.conversation_personas) >= 10:
            messagebox.showinfo("Info", "Maximum 10 personas allowed in a conversation.")
            return

        self.conversation_personas.append(persona_name)
        self.update_selected_personas_list()

    def remove_persona_from_conversation(self):
        """Remove selected persona from conversation."""
        selection = self.selected_personas_list.curselection()
        if not selection:
            messagebox.showinfo("Info", "Please select a persona to remove.")
            return

        index = selection[0]
        del self.conversation_personas[index]
        self.update_selected_personas_list()

    def move_persona_up(self):
        """Move selected persona up in the conversation order."""
        selection = self.selected_personas_list.curselection()
        if not selection:
            messagebox.showinfo("Info", "Please select a persona to move.")
            return

        index = selection[0]
        if index == 0:
            return  # Already at top

        # Swap with previous
        self.conversation_personas[index], self.conversation_personas[index-1] = \
            self.conversation_personas[index-1], self.conversation_personas[index]

        self.update_selected_personas_list()
        self.selected_personas_list.selection_set(index-1)

    def move_persona_down(self):
        """Move selected persona down in the conversation order."""
        selection = self.selected_personas_list.curselection()
        if not selection:
            messagebox.showinfo("Info", "Please select a persona to move.")
            return

        index = selection[0]
        if index == len(self.conversation_personas) - 1:
            return  # Already at bottom

        # Swap with next
        self.conversation_personas[index], self.conversation_personas[index+1] = \
            self.conversation_personas[index+1], self.conversation_personas[index]

        self.update_selected_personas_list()
        self.selected_personas_list.selection_set(index+1)

    def update_persona_details(self, persona_name, details_widget):
        """Update the details display for a selected persona."""
        # Find the persona by name
        persona = next((p for p in self.chat_manager.personas if p.name == persona_name), None)

        # Update details widget
        details_widget.config(state=NORMAL)
        details_widget.delete(1.0, END)

        if persona:
            details = f"Name: {persona.name}\n"
            details += f"Age: {persona.age}\n"
            details += f"Gender: {persona.gender}\n\n"
            details += f"Personality:\n{persona.personality}"
            details_widget.insert(END, details)

        details_widget.config(state=DISABLED)
    
    def add_persona(self):
        """Add a new persona to the available personas list."""
        dialog = tkb.Toplevel(self)
        dialog.title("Add New Persona")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        form_frame = tkb.Frame(dialog, padding="10")
        form_frame.pack(fill=tkb.BOTH, expand=True)

        tkb.Label(form_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=5)
        name_entry = tkb.Entry(form_frame, width=40)
        name_entry.grid(row=0, column=1, sticky="ew", pady=5)

        tkb.Label(form_frame, text="Age:").grid(row=1, column=0, sticky="w", pady=5)
        age_entry = tkb.Spinbox(form_frame, from_=1, to=150, width=5)
        age_entry.grid(row=1, column=1, sticky="w", pady=5)

        tkb.Label(form_frame, text="Gender:").grid(row=2, column=0, sticky="w", pady=5)
        gender_entry = tkb.Entry(form_frame, width=40)
        gender_entry.grid(row=2, column=1, sticky="ew", pady=5)

        tkb.Label(form_frame, text="Personality:").grid(row=3, column=0, sticky="w", pady=5)
        personality_text = scrolledtext.ScrolledText(form_frame, height=10, width=40)
        personality_text.grid(row=3, column=1, sticky="ew", pady=5)

        button_frame = tkb.Frame(form_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        def submit():
            name = name_entry.get().strip()
            age = int(age_entry.get())
            gender = gender_entry.get().strip()
            personality = personality_text.get("1.0", END).strip()

            if name and gender and personality:
                new_persona = Persona(name, personality, age, gender)
                self.chat_manager.personas.append(new_persona)
                self.chat_manager.save_personas()

                # Update available personas list
                self.available_personas_list.insert(END, name)
                dialog.destroy()
            else:
                messagebox.showerror("Error", "Please fill in all fields.", parent=dialog)

        tkb.Button(button_frame, text="Add", command=submit, bootstyle="success").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)
    
    def edit_persona(self):
        """Edit a selected persona from the available list."""
        selection = self.available_personas_list.curselection()
        if not selection:
            messagebox.showinfo("Info", "Please select a persona to edit.")
            return

        selected_name = self.available_personas_list.get(selection[0])
        persona = next((p for p in self.chat_manager.personas if p.name == selected_name), None)
        if not persona:
            return

        dialog = tkb.Toplevel(self)
        dialog.title(f"Edit Persona: {persona.name}")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()

        form_frame = tkb.Frame(dialog, padding="10")
        form_frame.pack(fill=tkb.BOTH, expand=True)

        tkb.Label(form_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=5)
        name_entry = tkb.Entry(form_frame, width=40)
        name_entry.insert(0, persona.name)
        name_entry.grid(row=0, column=1, sticky="ew", pady=5)

        tkb.Label(form_frame, text="Age:").grid(row=1, column=0, sticky="w", pady=5)
        age_entry = tkb.Spinbox(form_frame, from_=1, to=150, width=5)
        age_entry.set(persona.age)
        age_entry.grid(row=1, column=1, sticky="w", pady=5)

        tkb.Label(form_frame, text="Gender:").grid(row=2, column=0, sticky="w", pady=5)
        gender_entry = tkb.Entry(form_frame, width=40)
        gender_entry.insert(0, persona.gender)
        gender_entry.grid(row=2, column=1, sticky="ew", pady=5)

        tkb.Label(form_frame, text="Personality:").grid(row=3, column=0, sticky="w", pady=5)
        personality_text = scrolledtext.ScrolledText(form_frame, height=10, width=40)
        personality_text.insert("1.0", persona.personality)
        personality_text.grid(row=3, column=1, sticky="ew", pady=5)

        def submit():
            old_name = persona.name
            name = name_entry.get().strip()
            age = int(age_entry.get())
            gender = gender_entry.get().strip()
            personality = personality_text.get("1.0", END).strip()

            if name and gender and personality:
                persona.name = name
                persona.age = age
                persona.gender = gender
                persona.personality = personality

                self.chat_manager.save_personas()

                # Update both lists
                self.available_personas_list.delete(0, END)
                for p in self.chat_manager.personas:
                    self.available_personas_list.insert(END, p.name)

                # Update conversation personas list if name changed
                if old_name != name and old_name in self.conversation_personas:
                    idx = self.conversation_personas.index(old_name)
                    self.conversation_personas[idx] = name
                    self.update_selected_personas_list()

                dialog.destroy()
            else:
                messagebox.showerror("Error", "Please fill in all fields.", parent=dialog)

        button_frame = tkb.Frame(form_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        tkb.Button(button_frame, text="Save", command=submit, bootstyle="success").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

    def delete_persona(self):
        """Delete a selected persona from the available list."""
        selection = self.available_personas_list.curselection()
        if not selection:
            messagebox.showinfo("Info", "Please select a persona to delete.")
            return

        selected_name = self.available_personas_list.get(selection[0])

        if messagebox.askyesno("Confirm", f"Are you sure you want to delete {selected_name}?"):
            self.chat_manager.personas = [p for p in self.chat_manager.personas if p.name != selected_name]
            self.chat_manager.save_personas()

            # Remove from both lists
            self.available_personas_list.delete(selection[0])
            if selected_name in self.conversation_personas:
                self.conversation_personas.remove(selected_name)
                self.update_selected_personas_list()
    
    def setup_models_tab(self, parent):
        """Set up the models selection tab for multiple personas."""
        # Initialize persona_models dictionary
        self.persona_models = {}

        # Create a scrollable frame for model selection
        canvas = tk.Canvas(parent)
        scrollbar = tkb.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.models_scrollable_frame = tkb.Frame(canvas)

        self.models_scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.models_scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Add a button to refresh model selections based on selected personas
        refresh_frame = tkb.Frame(parent)
        refresh_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        tkb.Button(
            refresh_frame,
            text="Configure Models for Selected Personas",
            command=self.update_models_tab,
            bootstyle="info"
        ).pack()

        # Initial update
        self.update_models_tab()

    def update_models_tab(self):
        """Update the models tab based on selected personas."""
        # Clear existing widgets
        for widget in self.models_scrollable_frame.winfo_children():
            widget.destroy()

        if not self.conversation_personas:
            tkb.Label(
                self.models_scrollable_frame,
                text="Please select personas in the 'Select Personas' tab first.",
                font=("-size 12")
            ).pack(padx=20, pady=20)
            return

        # Create model selection for each persona
        for i, persona_name in enumerate(self.conversation_personas):
            frame = tkb.LabelFrame(
                self.models_scrollable_frame,
                text=f"{persona_name}'s Model",
                padding="10"
            )
            frame.pack(fill="x", padx=10, pady=5)

            # Provider selection
            tkb.Label(frame, text="Provider:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
            provider_var = tkb.StringVar(value="ollama")
            provider_combo = tkb.Combobox(
                frame,
                textvariable=provider_var,
                values=list(self.chat_manager.api_clients.keys()),
                state="readonly"
            )
            provider_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

            # Model selection
            tkb.Label(frame, text="Model:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
            model_var = tkb.StringVar()
            model_combo = tkb.Combobox(frame, textvariable=model_var)
            model_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

            # Refresh button
            refresh_btn = tkb.Button(
                frame,
                text="Refresh Models",
                command=lambda pv=provider_var, mc=model_combo: self.refresh_models(pv.get(), mc),
                bootstyle="info-outline"
            )
            refresh_btn.grid(row=2, column=0, columnspan=2, padx=5, pady=5)

            # Bind provider change
            provider_combo.bind(
                "<<ComboboxSelected>>",
                lambda e, pv=provider_var, mc=model_combo: self.refresh_models(pv.get(), mc)
            )

            # Store references
            if not hasattr(self, 'persona_model_widgets'):
                self.persona_model_widgets = {}

            self.persona_model_widgets[persona_name] = {
                'provider_var': provider_var,
                'provider_combo': provider_combo,
                'model_var': model_var,
                'model_combo': model_combo
            }

            # Initialize persona_models entry if exists
            if persona_name in self.persona_models:
                provider, model = self.persona_models[persona_name]
                provider_var.set(provider)
                model_var.set(model)
            else:
                # Initialize with default
                self.persona_models[persona_name] = ("ollama", "")

            # Bind model selection to save
            model_combo.bind(
                "<<ComboboxSelected>>",
                lambda e, pn=persona_name, pv=provider_var, mv=model_var: self.save_persona_model_selection(pn, pv.get(), mv.get())
            )

            # Initial model refresh
            self.refresh_models(provider_var.get(), model_combo)

    def save_persona_model_selection(self, persona_name, provider, model):
        """Save the model selection for a persona."""
        self.persona_models[persona_name] = (provider, model)
        log.info(f"Saved model selection for {persona_name}: {provider} - {model}")

    def refresh_models(self, provider_name, model_combo, saved_model=None):
        """Refresh the list of available models for a provider."""
        provider_key = provider_name.lower()
        providers_requiring_key = ["openrouter", "openai"]
        
        # If called due to provider change, load the saved model for the *new* provider
        if saved_model is None:
            config_key = f"last_model_{provider_key.replace(' ', '')}"
            saved_model = self.app_config.get(config_key)
            
        # Show loading indicator
        model_combo['values'] = ["Loading..."]
        model_combo.current(0)
        
        # Get the client
        client = self.chat_manager.api_clients.get(provider_key)
        
        if not client:
            log.error(f"Client not found for {provider_name}. Available clients: {list(self.chat_manager.api_clients.keys())}")
            messagebox.showerror("Error", f"No client found for provider: {provider_name}")
            model_combo['values'] = ["Error: No client found"]
            model_combo.current(0)
            return

        # API key handling for this specific provider
        if provider_key in providers_requiring_key:
            # Load from config
            config_key = f"{provider_key}_api_key"
            client.api_key = self.app_config.get(config_key, "")

            client.update_headers()

            # Check if we have a key for this provider
            if not client.api_key:
                model_combo['values'] = ["Enter API key in config"]
                model_combo.current(0)
                return
        
        # Use a thread to avoid blocking the UI
        def fetch_models():
            try:
                log.info(f"Getting models from {provider_name}...")
                models = client.get_available_models()
                
                # Update the combobox in the main thread
                self.after(0, lambda: self._update_model_combo(model_combo, models, saved_model))
            except Exception as e:
                log.exception(f"Error fetching models: {str(e)}")
                self.after(0, lambda: self._show_model_error(model_combo, str(e)))
        
        threading.Thread(target=fetch_models, daemon=True).start()
    
    def _update_model_combo(self, model_combo, models, saved_model=None):
        """Update the model combobox with fetched models."""
        if not models:
            model_combo['values'] = ["No models found"]
            model_combo.current(0)
            return
            
        model_combo['values'] = models
        
        # Try to set the saved model if it exists
        if saved_model and saved_model in models:
            model_combo.set(saved_model)
        else:
            model_combo.current(0)
    
    def _show_model_error(self, model_combo, error_message):
        """Show error in model combobox."""
        model_combo['values'] = [f"Error: {error_message}"]
        model_combo.current(0)
        messagebox.showerror("Error", f"Failed to get models: {error_message}")

    def setup_options_tab(self, parent):
        """Set up the options tab."""
        tkb.Label(parent, text="Max Turns:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.max_turns_var = tkb.IntVar(value=DEFAULT_MAX_TURNS)
        max_turns_spinbox = tkb.Spinbox(parent, from_=2, to=100, textvariable=self.max_turns_var, width=5)
        max_turns_spinbox.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        tkb.Label(parent, text="Topic:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.topic_var = tkb.StringVar(value=DEFAULT_TOPIC)
        topic_entry = tkb.Entry(parent, textvariable=self.topic_var, width=50)
        topic_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        tkb.Label(parent, text="Turn Order:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.turn_order_var = tkb.StringVar(value="round-robin")
        turn_order_combo = tkb.Combobox(parent, textvariable=self.turn_order_var, values=["round-robin", "random"], state="readonly", width=20)
        turn_order_combo.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # Add description label
        turn_order_desc = tkb.Label(parent, text="Round-robin: Personas speak in order\nRandom: Random persona selected each turn", font=("-size 9"))
        turn_order_desc.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        # Streaming option
        tkb.Label(parent, text="Response Streaming:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.streaming_var = tkb.BooleanVar(value=True)
        streaming_check = tkb.Checkbutton(
            parent,
            text="Enable real-time response streaming",
            variable=self.streaming_var,
            bootstyle="success-round-toggle"
        )
        streaming_check.grid(row=4, column=1, padx=5, pady=5, sticky="w")
    
    def start_conversation(self):
        """Start the conversation with selected personas and models."""
        # Validate selections
        if not self.validate_selections():
            return
        
        # Set up the chat manager with selections
        self.setup_chat_manager()
        
        # Show the chat interface
        self.show_chat_interface()
    
    def validate_selections(self) -> bool:
        """Validate that all necessary selections have been made."""
        # Check personas
        if len(self.conversation_personas) < 2:
            messagebox.showerror("Error", "Please select at least 2 personas for the conversation.")
            return False

        # Check if we have model selections for all personas
        if not hasattr(self, 'persona_models') or len(self.persona_models) != len(self.conversation_personas):
            messagebox.showerror("Error", "Please configure models for all selected personas in the Models tab.")
            return False

        # Validate all model selections
        for persona_name, (provider, model) in self.persona_models.items():
            if not model or model.startswith("Error") or model == "No models found" or model == "Loading...":
                messagebox.showerror("Error", f"Please select a valid model for {persona_name}.")
                return False

        return True
    
    def setup_chat_manager(self):
        """Set up the chat manager with the selected options."""
        # Set selected personas
        selected_persona_objs = []
        for persona_name in self.conversation_personas:
            persona = next((p for p in self.chat_manager.personas if p.name == persona_name), None)
            if persona:
                selected_persona_objs.append(persona)

        self.chat_manager.selected_personas = selected_persona_objs

        # Set selected clients and models for each persona
        providers_requiring_key = ["openrouter", "openai"]
        selected_clients = []
        selected_models = []

        for persona_name in self.conversation_personas:
            provider_key, model = self.persona_models[persona_name]
            provider = provider_key.lower()

            client = self.chat_manager.api_clients[provider]

            # Set API key *from config* if required
            if provider in providers_requiring_key:
                config_key = f"{provider}_api_key"
                api_key = self.app_config.get(config_key, "")
                if not api_key:
                    log.warning(f"API key for {provider} not found in config.")
                client.api_key = api_key
                client.update_headers()

            client.set_model(model)
            selected_clients.append(client)
            selected_models.append(model)

        self.chat_manager.selected_clients = selected_clients
        self.chat_manager.selected_models = selected_models

        # Set max turns
        self.chat_manager.max_turns = self.max_turns_var.get()

        # Set turn order strategy
        self.chat_manager.turn_order_strategy = self.turn_order_var.get()

        # Set streaming option
        self.chat_manager.use_streaming = self.streaming_var.get()
    
    def show_chat_interface(self):
        """Show the chat interface."""
        # Clear the main frame
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        
        # Create chat frame with padding
        chat_frame = tkb.Frame(self.main_frame, padding="20")
        chat_frame.grid(row=0, column=0, sticky="nsew")
        chat_frame.grid_columnconfigure(0, weight=1)
        chat_frame.grid_rowconfigure(0, weight=1)
        
        # Create conversation display with rounded corners
        conversation_frame = tkb.LabelFrame(chat_frame, text="Conversation", padding="10")
        conversation_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        conversation_frame.grid_columnconfigure(0, weight=1)
        conversation_frame.grid_rowconfigure(1, weight=1)  # Text area is now in row 1
        
        # Search frame
        search_frame = tkb.Frame(conversation_frame)
        search_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        tkb.Label(search_frame, text="Search:").pack(side=LEFT, padx=5)
        self.search_var = tkb.StringVar()
        self.search_entry = tkb.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=LEFT, padx=5)
        self.search_entry.bind("<Return>", lambda e: self.search_conversation())

        tkb.Button(search_frame, text="Find", command=self.search_conversation, bootstyle="info-outline").pack(side=LEFT, padx=2)
        tkb.Button(search_frame, text="Next", command=self.search_next, bootstyle="info-outline").pack(side=LEFT, padx=2)
        tkb.Button(search_frame, text="Prev", command=self.search_prev, bootstyle="info-outline").pack(side=LEFT, padx=2)
        tkb.Button(search_frame, text="Clear", command=self.clear_search, bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        self.case_sensitive_var = tkb.BooleanVar(value=False)
        self.case_check = tkb.Checkbutton(search_frame, text="Case", variable=self.case_sensitive_var, bootstyle="info-round-toggle")
        self.case_check.pack(side=LEFT, padx=5)

        self.regex_var = tkb.BooleanVar(value=False)
        self.regex_check = tkb.Checkbutton(search_frame, text="Regex", variable=self.regex_var, bootstyle="info-round-toggle")
        self.regex_check.pack(side=LEFT, padx=5)

        self.search_matches = []
        self.current_search_index = -1

        # Conversation text area with custom styling
        self.conversation_display = scrolledtext.ScrolledText(
            conversation_frame,
            wrap=WORD,
            width=80,
            height=20,
            font=("-size 11"), relief=FLAT, borderwidth=0 # Use ttkbootstrap font syntax
        )
        self.conversation_display.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.conversation_display.config(state=DISABLED)

        # Configure search highlight tag
        style = tkb.Style()
        self.conversation_display.tag_configure("search_highlight", background="yellow", foreground="black")
        self.conversation_display.tag_configure("current_search", background="orange", foreground="black")
        
        # Status bar with custom styling
        self.status_var = tkb.StringVar()
        status_bar = tkb.Label(
            chat_frame, 
            textvariable=self.status_var, 
            relief=SUNKEN, 
            anchor=W,
            padding=5,
            font=("-size 10")
        )
        status_bar.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        
        # Control buttons frame with padding
        control_frame = tkb.Frame(chat_frame, padding="10")
        control_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_columnconfigure(1, weight=1)
        control_frame.grid_columnconfigure(2, weight=1)
        control_frame.grid_columnconfigure(3, weight=1)
        
        # Control buttons with consistent styling
        button_style = {"padding": 8}
        
        self.pause_button = tkb.Button(
            control_frame, 
            text="Pause", 
            command=self.toggle_pause,
            bootstyle="warning"
        )
        self.pause_button.grid(row=0, column=0, padx=5, pady=5)
        
        self.stop_button = tkb.Button(
            control_frame, 
            text="Stop", 
            command=self.stop_conversation,
            bootstyle="danger"
        )
        self.stop_button.grid(row=0, column=1, padx=5, pady=5)
        
        self.new_topic_button = tkb.Button(
            control_frame, 
            text="New Topic", 
            command=self.add_new_topic,
            bootstyle="info"
        )
        self.new_topic_button.grid(row=0, column=2, padx=5, pady=5)
        
        self.narrator_button = tkb.Button(
            control_frame, 
            text="System Msg", 
            command=self.add_narrator_message,
            state=DISABLED,
            bootstyle="secondary"
        )
        self.narrator_button.grid(row=0, column=3, padx=5, pady=5)
        
        # Start the conversation
        self.chat_manager.start_conversation(self.topic_var.get())
    
    def update_conversation_display(self):
        """Update the conversation display with the current conversation."""
        try:
            # Batch all UI updates together
            updates = []

            # Prepare all the text and tag information first
            for msg in self.chat_manager.conversation:
                if msg["role"] == "system":
                    updates.append(("\nSYSTEM: ", "system_name"))
                    updates.append((f"{msg['content']}\n", "system_text"))
                else:
                    # Find persona index
                    persona_idx = 0
                    for i, persona in enumerate(self.chat_manager.selected_personas):
                        if msg["persona"] == persona.name:
                            persona_idx = i
                            break

                    name_tag = f"persona{persona_idx+1}_name"
                    text_tag = f"persona{persona_idx+1}_text"
                    updates.append((f"\n{msg['persona']}: ", name_tag))
                    updates.append((f"{msg['content']}\n", text_tag))

            # Do all UI updates in one batch
            def perform_update():
                self.conversation_display.config(state=NORMAL)
                self.conversation_display.delete(1.0, END)

                # Configure tags for all personas dynamically
                style = tkb.Style()

                # System messages
                self.conversation_display.tag_configure("system_name",
                    foreground=style.colors.secondary,
                    font=("-size 10 -weight bold"))
                self.conversation_display.tag_configure("system_text",
                    foreground=style.colors.secondary,
                    font=("-size 10"))

                # Persona colors - cycle through available colors
                persona_colors = [
                    style.colors.success,   # Green
                    style.colors.info,      # Blue
                    style.colors.warning,   # Orange
                    style.colors.danger,    # Red
                    style.colors.primary,   # Primary color
                    "#9b59b6",  # Purple
                    "#e74c3c",  # Crimson
                    "#3498db",  # Sky blue
                    "#2ecc71",  # Emerald
                    "#f39c12"   # Gold
                ]

                # Configure tags for each persona
                for i in range(len(self.chat_manager.selected_personas)):
                    color = persona_colors[i % len(persona_colors)]
                    self.conversation_display.tag_configure(f"persona{i+1}_name",
                        foreground=color,
                        font=("-size 10 -weight bold"))
                    self.conversation_display.tag_configure(f"persona{i+1}_text",
                        foreground=color,
                        font=("-size 10"))

                # Insert all text at once
                for text, tag in updates:
                    self.conversation_display.insert(END, text, tag)

                self.conversation_display.see(END)
                self.conversation_display.config(state=DISABLED)

            # Schedule the update on the main thread
            if self.winfo_exists():
                self.after_idle(perform_update)

        except Exception as e:
            log.exception("Error updating conversation display")
            self.after_idle(lambda: self.update_status(f"Error updating display: {str(e)}"))
    
    def update_status(self, message: str):
        """Update the status bar with a message."""
        try:
            if self.winfo_exists():
                self.after_idle(lambda: self.status_var.set(message))
        except Exception as e:
            log.exception("Error updating status")
    
    def toggle_pause(self):
        """Toggle the pause state of the conversation."""
        try:
            if not self.chat_manager.is_running:
                return
                
            self.chat_manager.is_paused = not self.chat_manager.is_paused
            
            def update_ui():
                if self.chat_manager.is_paused:
                    self.pause_button.config(text="Resume", bootstyle="success")
                    self.narrator_button.config(state=NORMAL)
                    self.update_status("Conversation paused")
                else:
                    self.pause_button.config(text="Pause", bootstyle="warning")
                    self.narrator_button.config(state=DISABLED)
                    self.update_status("Conversation resumed")
            
            # Schedule UI updates on main thread
            if self.winfo_exists():
                self.after_idle(update_ui)
                
        except Exception as e:
            log.exception("Error toggling pause state")
            self.after_idle(lambda: self.update_status(f"Error toggling pause: {str(e)}"))
    
    def stop_conversation(self):
        """Stop the current conversation."""
        self.chat_manager.is_running = False
        self.update_status("Stopping conversation...")
        
        # Disable controls until fully stopped
        self.enable_controls(False)
        
        # Wait for the chat thread to finish
        if self.chat_manager.chat_thread and self.chat_manager.chat_thread.is_alive():
            self.after(100, self.check_thread_stopped)
        else:
            self.show_setup_screen()
    
    def check_thread_stopped(self):
        """Check if the chat thread has stopped."""
        if self.chat_manager.chat_thread and self.chat_manager.chat_thread.is_alive():
            # Still running, check again later
            self.after(100, self.check_thread_stopped)
        else:
            # Thread stopped, show setup screen
            self.show_setup_screen()
    
    def enable_controls(self, enabled: bool):
        """Enable or disable control buttons."""
        state = NORMAL if enabled else DISABLED
        bootstyle_pause = "warning" if enabled else "warning-disabled"
        bootstyle_stop = "danger" if enabled else "danger-disabled"
        bootstyle_topic = "info" if enabled else "info-disabled"
        bootstyle_narrator = "secondary" if enabled and self.chat_manager.is_paused else "secondary-disabled"
        state_narrator = NORMAL if enabled and self.chat_manager.is_paused else DISABLED

        self.pause_button.config(state=state, bootstyle=bootstyle_pause)
        self.stop_button.config(state=state, bootstyle=bootstyle_stop)
        self.new_topic_button.config(state=state, bootstyle=bootstyle_topic)
        self.narrator_button.config(state=state_narrator, bootstyle=bootstyle_narrator)
        
    def add_narrator_message(self):
        """Add a system message to the conversation."""
        if not self.chat_manager.is_paused:
            messagebox.showinfo("Info", "Please pause the conversation first.")
            return
        
        message = simpledialog.askstring(
            "System Message", 
            "Enter system message:",
            parent=self
        )
        
        if message:
            # Use direct system message rather than add_system_instruction
            # Create system instruction message
            system_msg = {
                "role": "system",
                "persona": "System",
                "content": message
            }
            
            # Add to conversation
            self.chat_manager.conversation.append(system_msg)
            self.chat_manager._log_message(system_msg)
            
            # Update GUI
            self.update_status("System message added - Resume to see effect")
            self.update_conversation_display()
            log.info(f"System instruction added: {message}")
    
    def add_new_topic(self):
        """Add a new topic as a system instruction."""
        if not self.chat_manager.is_paused:
            messagebox.showinfo("Info", "Please pause the conversation first.")
            return
            
        dialog = tkb.Toplevel(self)
        dialog.title("New Topic")
        dialog.geometry("400x200")
        dialog.transient(self)  # Make dialog modal
        dialog.grab_set()  # Make dialog modal
        
        # Topic entry
        tkb.Label(dialog, text="Enter new topic:").pack(padx=10, pady=10)
        topic_entry = scrolledtext.ScrolledText(dialog, height=5, width=40)
        topic_entry.pack(padx=10, pady=5)
        
        # Buttons
        button_frame = tkb.Frame(dialog)
        button_frame.pack(pady=10)
        
        def submit():
            new_topic = topic_entry.get("1.0", END).strip()
            if new_topic:
                # Add new topic as a special system message with clear instruction
                system_msg = {
                    "role": "system",
                    "persona": "System",
                    "content": f"NEW TOPIC: The conversation should now shift to discussing '{new_topic}'. Both participants should acknowledge this topic change naturally and start discussing this new topic."
                }
                
                # Add to conversation
                self.chat_manager.conversation.append(system_msg)
                self.chat_manager._log_message(system_msg)
                
                # Update GUI
                self.update_status("New topic added - Resume to see effect")
                self.update_conversation_display()
                
                dialog.destroy()
        
        tkb.Button(button_frame, text="Submit", command=submit, bootstyle="success").pack(side=LEFT, padx=5)
        tkb.Button(button_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary").pack(side=LEFT, padx=5)

    def search_conversation(self):
        """Search for text in the conversation display."""
        query = self.search_var.get()
        if not query:
            return

        # Clear previous search results
        self.clear_search()

        # Get search options
        case_sensitive = self.case_sensitive_var.get()
        use_regex = self.regex_var.get()

        # Search the text widget
        self.conversation_display.config(state=NORMAL)
        start_pos = "1.0"

        while True:
            if use_regex:
                # Use regex search
                pos = self.conversation_display.search(query, start_pos, END, regexp=True, nocase=not case_sensitive)
            else:
                # Use literal search
                pos = self.conversation_display.search(query, start_pos, END, nocase=not case_sensitive)

            if not pos:
                break

            # Calculate end position
            end_pos = f"{pos}+{len(query)}c"

            # Add to matches list
            self.search_matches.append((pos, end_pos))

            # Highlight the match
            self.conversation_display.tag_add("search_highlight", pos, end_pos)

            # Move to next position
            start_pos = end_pos

        self.conversation_display.config(state=DISABLED)

        # Update status
        if self.search_matches:
            self.current_search_index = 0
            self.highlight_current_match()
            self.update_status(f"Found {len(self.search_matches)} matches for '{query}'")
        else:
            self.update_status(f"No matches found for '{query}'")

    def search_next(self):
        """Go to next search match."""
        if not self.search_matches:
            return

        self.current_search_index = (self.current_search_index + 1) % len(self.search_matches)
        self.highlight_current_match()

    def search_prev(self):
        """Go to previous search match."""
        if not self.search_matches:
            return

        self.current_search_index = (self.current_search_index - 1) % len(self.search_matches)
        self.highlight_current_match()

    def highlight_current_match(self):
        """Highlight the current search match and scroll to it."""
        if not self.search_matches or self.current_search_index < 0:
            return

        # Remove previous current highlight
        self.conversation_display.tag_remove("current_search", "1.0", END)

        # Add current highlight
        pos, end_pos = self.search_matches[self.current_search_index]
        self.conversation_display.tag_add("current_search", pos, end_pos)

        # Scroll to the match
        self.conversation_display.see(pos)

        # Update status
        self.update_status(f"Match {self.current_search_index + 1} of {len(self.search_matches)}")

    def clear_search(self):
        """Clear search highlights."""
        self.conversation_display.tag_remove("search_highlight", "1.0", END)
        self.conversation_display.tag_remove("current_search", "1.0", END)
        self.search_matches = []
        self.current_search_index = -1


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
    