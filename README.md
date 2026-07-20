<div align="center">

# 🤖 Auto Chat

**Watch AI personas talk to each other — 2 to 10 of them, each on its own model, mixing providers in one conversation.**

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

</div>

---

## What it is

Auto Chat sets up AI personas with distinct personalities and lets them converse with each other,
turn by turn, while you watch (and optionally steer). Each persona can run on a different model
from a different provider — mix a local Ollama model, an LM Studio model, and a hosted OpenAI or
Anthropic model in the same conversation.

There are three ways to run it:

| Interface | Entry point | Status |
|---|---|---|
| **Web UI** (recommended) | `python web_server.py` | Primary, actively developed |
| **CLI** | `python cli_chat.py` | Lightweight, scriptable, 2-persona only |
| **Desktop (Tkinter)** | `python auto_chat.py` | Legacy, still functional |

## Features

- **2–10 personas per conversation**, each independently configured with its own provider and model
- **Multi-provider**: Ollama, LM Studio, OpenAI, Anthropic, OpenRouter, Venice AI, and Grok/xAI — mixed freely in one chat
- **Live streaming** over WebSockets — token-by-token output, typing indicators, markdown rendering
- **Visible thinking** — reasoning models' chain-of-thought streams live in collapsible blocks
- **Continue / regenerate / resume** — extend a finished conversation, redo the last turn, or reload any past conversation from history and keep going
- **AI persona generator** — describe a character in one line and a model drafts the full persona
- **One-click summaries** — a model writes a recap of the conversation so far
- **Mid-conversation control** — pause/resume, steer the topic, inject narrator events
- **Per-persona tuning** — temperature, max tokens, turn delay
- **Conversation templates** (brainstorming, debate, interview, storytelling, tutoring)
- **Searchable history** with favorites, plus a token & cost usage dashboard
- **Export** transcripts as Markdown, JSON, or plain text
- **Persona library management** — create, edit, and generate personas from the UI

## Tech stack

- **Backend**: Python, [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/), WebSockets for streaming
- **Frontend**: React 18 + Vite, plain CSS, `marked` for markdown rendering
- **Storage**: JSON files for config/personas/templates, SQLite for usage/cost tracking (`utils/usage_tracker.py`)
- **Legacy desktop UI**: Tkinter + `ttkbootstrap`

## Install

```bash
git clone https://github.com/rustyorb/auto_chat.git
cd auto_chat

python -m venv venv
source venv/bin/activate      # Windows: .\venv\Scripts\activate

pip install -r requirements.txt
```

`web/dist` (the built frontend) is committed to the repo, so **no Node.js install is required**
to run the web UI. Node is only needed if you want to edit the frontend source.

## Quickstart

### Web UI (recommended)

```bash
python web_server.py
```

Then open http://127.0.0.1:8008. On Windows you can instead double-click `start_webapp.bat`,
which installs dependencies on first run, starts the server minimized, and opens the browser
for you; `stop_webapp.bat` kills whatever is listening on port 8008.

On first run, set up personas and provider URLs/API keys from the UI, or seed them from the
example files:

```bash
cp config.json.example config.json
cp personas.json.example personas.json
```

### CLI

Two personas, one conversation, printed to the terminal:

```bash
python cli_chat.py --model1 llama3 --model2 llama3 \
  --persona1 "Professor Maxwell" --persona2 "Sophie Chen" \
  --provider1 ollama --provider2 ollama \
  --turns 10 --theme "the future of AI"
```

| Flag | Default | Description |
|---|---|---|
| `--model1` / `--model2` | *(required)* | Model name for each persona |
| `--persona1` / `--persona2` | first two personas in `personas.json` | Persona to use |
| `--provider1` / `--provider2` | `ollama` | `ollama`, `lmstudio`, `openrouter`, or `openai` |
| `--turns` | `10` | Number of conversation turns |
| `--theme` | `free conversation` | Conversation topic |

### Desktop (Tkinter)

```bash
python auto_chat.py
```

Pick two personas and providers/models from the setup screen, set a turn limit and topic, then
run the conversation with pause/resume, narrator interjections, and log saving.

### Persona generator (interactive, terminal)

```bash
python persona_generator.py
```

## Configuration

Configuration lives in two gitignored JSON files, seeded from the `*.example` templates:

- **`config.json`** — provider base URLs and API keys (`<provider>_url`, `<provider>_api_key`),
  plus last-used model per provider. Supports `//` and `/* */` comments (stripped on load).
- **`personas.json`** — the persona library: `name`, `personality`, and optional `age`/`gender`
  (omitted automatically in prompts for non-human personas).

Local providers need no key, only a reachable URL:

| Provider | Default URL |
|---|---|
| Ollama | `http://127.0.0.1:11434` |
| LM Studio | `http://localhost:1234/v1` |

Hosted providers need an API key, set via the web UI's "set API key…" flow or directly in
`config.json`: OpenAI, Anthropic, OpenRouter, Venice AI, Grok/xAI.

Never commit your real `config.json` — it's already covered by `.gitignore`.

## Project structure

```
auto_chat/
├── web_server.py          # FastAPI app: REST + WebSocket API for the web UI
├── chat_engine.py         # UI-agnostic conversation loop, emits events via callback
├── api_clients.py         # Per-provider LLM clients (retry/backoff, streaming, usage capture)
├── persona.py             # Persona model + system-prompt construction
├── persona_generator.py   # Interactive persona creation tool (CLI)
├── conversation_history.py# Conversation persistence/history store
├── conversation_templates.py # Named conversation templates (slugged filenames)
├── config.py               # App-wide constants (timeouts, defaults, provider URLs)
├── auto_chat.py            # Legacy Tkinter desktop app
├── cli_chat.py             # Terminal 2-persona conversation runner
├── utils/
│   ├── config_utils.py     # Comment-tolerant JSON config loader
│   ├── analytics.py        # Conversation summarization helpers
│   ├── export_formats.py   # Markdown/JSON/text transcript export
│   └── usage_tracker.py    # SQLite token/cost tracking
├── templates/               # Built-in conversation templates (JSON)
├── web/                     # React + Vite frontend
│   ├── src/                 # App.jsx, Sidebar.jsx, Stage.jsx, Modals.jsx, useChat.js, api.js
│   └── dist/                # Pre-built frontend, committed so no Node is required to run
├── config.json.example      # Template for config.json
├── personas.json.example    # Template for personas.json
├── start_webapp.bat / stop_webapp.bat  # Windows launch/stop helpers for the web UI
└── requirements.txt
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for a deeper look at the data flow and component design.

## Frontend development

The prebuilt `web/dist` lets you run the app without Node, but to change the UI itself:

```bash
cd web
npm install
npm run dev      # Vite dev server with API proxy to the backend
npm run build     # refresh web/dist — commit the result
```

## Testing

There is no automated test suite. Sanity-check changes with a compile pass:

```bash
python -m py_compile web_server.py chat_engine.py api_clients.py persona.py config.py
```

## License

[MIT](LICENSE) © 2024 rustyorb
