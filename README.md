<div align="center">

# 🤖 Auto Chat 🤖

**An AI vs. AI conversation simulator built with Tkinter.**

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT) <!-- Choose appropriate license -->
[![Issues](https://img.shields.io/github/issues/rustyorb/auto_chat?style=for-the-badge)](https://github.com/rustyorb/auto_chat/issues) <!-- Corrected URL -->
[![Forks](https://img.shields.io/github/forks/rustyorb/auto_chat?style=for-the-badge)](https://github.com/rustyorb/auto_chat/network/members) <!-- Corrected URL -->
[![Stars](https://img.shields.io/github/stars/rustyorb/auto_chat?style=for-the-badge)](https://github.com/rustyorb/auto_chat/stargazers) <!-- Corrected URL -->


<!-- Optional: Add a GIF or Screenshot here! -->
<!-- ![Auto Chat Demo](link_to_your_demo_image_or_gif.gif) -->

**Engage two AI personas in turn-based conversations using various Large Language Models (LLMs).**

</div>

---


## 🌐 Web UI (recommended)

The modern way to run Auto Chat: a React web interface backed by FastAPI,
with real-time streaming over WebSockets.

```bash
pip install -r requirements.txt
python web_server.py            # serves the pre-built UI at http://127.0.0.1:8008
```

*   👥 **2–10 personas per conversation** — each on its own model, from any provider
      (mix Ollama, LM Studio, OpenAI, Anthropic, OpenRouter, Venice AI, and Grok/xAI in one chat)
*   ⚡ Live token streaming, typing indicators, markdown rendering
*   💭 **Visible thinking** — reasoning models' chain-of-thought streams live in
      collapsible blocks under each message
*   ▶️ **Continue / redo / resume** — extend a finished conversation, regenerate
      the last turn, or reload any past conversation from history and keep it going
*   ✨ **AI persona generator** — describe a character in one line, a model drafts
      the full persona for the library
*   ✦ **One-click summaries** — a model writes a recap of the conversation so far
*   🎛️ Pause / steer topics / inject narrator events mid-conversation;
      per-persona temperature & max-tokens; adjustable turn delay
*   📚 Templates, searchable history with favorites, token & cost dashboard
*   ⭳ Export transcripts as Markdown / JSON / text

To hack on the frontend: `cd web && npm install && npm run dev` (Vite dev server
with proxy to the backend), and `npm run build` to refresh `web/dist`.

The original Tkinter desktop app still works: `python auto_chat.py`.

---

## 🌟 Features

*   🗣️ **Dual AI Conversations**: Pit two distinct AI personas against each other.
*   🔌 **Multi-LLM Support**: Integrates with Ollama, LM Studio, OpenAI, Anthropic, OpenRouter, Venice AI, and Grok/xAI APIs.
*   🎭 **Persona Management**: Easily create, edit, and manage AI personalities.
*   🎨 **Modern GUI**: Built with Tkinter and styled with `ttkbootstrap` for a clean look.
*   💾 **Conversation Logging**: Save and export chat transcripts.
*   🎤 **Narrator Mode**: Interject system messages or context into the conversation.
*   🎯 **Topic Control**: Guide the conversation with specific topics.
*   ⚙️ **Persistent Configuration**: Saves your settings and API keys.
*   🖥️ **CLI Mode**: Run conversations from the terminal with `cli_chat.py`.

---

## 🛠️ Requirements

*   Python 3.8+
*   Tkinter & ttk (usually included with Python)
*   `ttkbootstrap`
*   `requests`
*   `python-dotenv`
*   `rich` (for the Persona Generator)

---

## 🚀 Installation

<details>
<summary>Click to expand installation steps</summary>

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/rustyorb/auto_chat.git
    cd auto_chat
    ```
    Or download the source code ZIP.

2.  **Create and activate a virtual environment:**
    ```bash
    # Create virtual environment
    python -m venv venv

    # Activate virtual environment
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```
    > **Note:** Using a virtual environment is highly recommended!

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up `personas.json`:**
    ```bash
    # Copy the example personas file
    cp personas.json.example personas.json
    ```
    *(Alternatively, rename `personas.json.example` to `personas.json` manually)*

5.  **Set up `config.json`:**
    ```bash
    # Copy the example config file
    cp config.json.example config.json
    ```
    *(Alternatively, rename `config.json.example` to `config.json` manually)*

    > ✨ The example files provide a great starting point. Edit them directly or use the app's interface!

</details>

---

## ▶️ Usage

### 💬 Main Application (`auto_chat.py`)

1.  Ensure your virtual environment is activated (`source venv/bin/activate` or `.\venv\Scripts\activate`).
2.  Launch the application:
    ```bash
    python auto_chat.py
    ```
3.  **Setup Screen:**
    *   👤 Select two personas.
    *   ☁️ Choose API providers and models for each.
    *   🔢 Set the max number of conversation turns.
    *   📝 Enter a conversation topic.
4.  **During Conversation:**
    *   ⏯️ Pause/Resume
    *   📢 Add Narrator Messages
    *   ⏹️ Stop Conversation
    *   📄 Save Log

### 🧑‍🎨 Persona Generator (`persona_generator.py`)

A handy tool for crafting new AI personalities:

```bash
python persona_generator.py
