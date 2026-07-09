<div align="center">

# 🤖 Auto Chat Studio

**Watch AI personas talk to each other — a real-time, multi-model conversation sandbox.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-frontend-61dafb?style=for-the-badge&logo=react)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

Assemble a cast of **2–10 AI personas** — each on its own model, from any provider —
set the scene, and watch them think, argue, riff, and build a conversation in real time.

</div>

> _Add a screenshot or GIF here — `docs/screenshot.png` — to show the studio in action._

---

## ✨ What makes it fun

- **A cast, not a pair.** Run 2 to 10 personas in one conversation, each bound to its own model.
- **Mix providers freely.** A local LM Studio model can debate an Anthropic model while an Ollama model heckles from the side.
- **See the machine think.** Reasoning models stream their chain-of-thought into collapsible blocks under each message.
- **Direct the scene.** Pause anytime to steer the topic, drop in a narrator event, or hand the mic back.
- **Let it run itself.** Turn on **Auto-Director** and an unseen narrator injects twists and complications to keep long, unattended runs alive.
- **Never lose a good one.** Every conversation auto-saves to a searchable history you can favorite, resume, summarize, and export.

---

## 🚀 Quick start

### Windows (easiest)

```bat
start_webapp.bat
```

That installs dependencies on first run, launches the server, and opens the studio in your browser.
`stop_webapp.bat` shuts it down.

### Any platform (manual)

```bash
pip install -r requirements.txt
python web_server.py
```

Then open **http://127.0.0.1:8008**.

> The web UI is pre-built and committed (`web/dist`), so **you don't need Node.js just to run it** — only Python.

---

## 🔌 Providers

Mix and match any of these in a single conversation. Local providers are free and private; cloud providers need an API key (entered right in the UI via the **"set API key…"** button next to the model picker).

| Provider | Type | Needs key? | Notes |
|---|---|---|---|
| **Ollama** | Local | No | Point at any host with the "set URL…" button (default `127.0.0.1:11434`). |
| **LM Studio** | Local | No | OpenAI-compatible; set its URL (e.g. `127.0.0.1:1234`) — `/v1` is added for you. |
| **OpenAI** | Cloud | Yes | GPT and o-series models. |
| **Anthropic** | Cloud | Yes | Claude models, with streaming + thinking. |
| **OpenRouter** | Cloud | Yes | Hundreds of models behind one key. |
| **Venice AI** | Cloud | Yes | Privacy-focused, OpenAI-compatible. |
| **Grok (xAI)** | Cloud | Yes | OpenAI-compatible. |

Keys and local URLs are saved to `config.json` (which is git-ignored — your keys never leave the machine).

---

## 🎭 Feature tour

**Casting & models**
- 2–10 personas per conversation, each with its own provider + model
- Searchable model picker (handles providers with dozens of models)
- Per-persona **temperature** and **max-tokens** tuning
- Optional **fallback model** per persona if its primary errors out

**Personas**
- Full library: create, edit, delete
- **AI persona generator** — describe a character in one line ("a paranoid weather forecaster who trusts pigeons") and a model drafts the whole persona. Supports *any* entity, human or not — rogue LLMs, sentient objects, abstract concepts.

**Running the scene**
- Live token streaming with typing indicators and markdown rendering
- **Visible thinking**: reasoning models' chain-of-thought in collapsible blocks
- Adjustable **turn delay** and round-robin or random turn order
- **∞ Endless mode**: start it and let it run until you hit Stop
- **Pause / Resume / Stop** anytime; **Clear** the stage for a fresh start (runs stay in History)
- **Interject**: steer to a new topic, drop a system event, or add a narrator scene note — woven in naturally, not as a fire alarm
- **Auto-Director** (optional): an LLM narrator automatically injects a twist every few turns so unattended runs stay dynamic

**After the fact**
- **Continue** a finished conversation for more turns
- **Redo** the last turn if you didn't like it
- **Resume** any past conversation from history and keep it going
- One-click **summary** written by a model of your choice
- **Auto-titled** history entries so past runs are easy to find

**Keeping & sharing**
- Searchable **history** with favorites; every run auto-saves
- Reusable scene **templates**
- **Export** transcripts as Markdown, JSON, plain text, or a self-contained styled **HTML** page
- **Usage dashboard**: token counts and estimated cost per model and provider

---

## 🧠 How it works

```
                       ┌──────────────────────────────┐
   Browser (React) ◄───┤  FastAPI  (web_server.py)     │
        ▲   │  REST +  │                               │
        │   │  WebSocket  ConversationEngine           │
        │   ▼          │  (chat_engine.py)             │
   live events ◄───────┤   • one worker thread         │
                       │   • per-persona API clients   │
                       │   • emits typed WS events     │
                       └──────────────┬────────────────┘
                                      │
             ┌────────────────────────┼───────────────────────┐
             ▼                        ▼                        ▼
        api_clients.py          SQLite history          SQLite usage
   (Ollama / LM Studio /     (conversation_history)     (usage_tracker)
    OpenAI / Anthropic /
    OpenRouter / Venice / Grok)
```

- **`chat_engine.py`** runs the conversation loop on a worker thread and emits typed events (`message_chunk`, `thinking_chunk`, `turn`, `done`, …) over a WebSocket. Each persona gets its own client instance, so several personas can share a provider while running different models.
- **`api_clients.py`** holds one client per provider, with streaming, token-usage capture, reasoning capture, and retry-with-backoff.
- **`web_server.py`** is the FastAPI app: REST endpoints for setup/history/usage and the `/ws` event stream. It serves the built React app from `web/dist`.
- The React frontend (`web/src`) reconnects and pulls a full snapshot on connect, so refreshing mid-conversation just works.

---

## ⚙️ Configuration

On first run, copy the examples (the launcher and app will also create sensible defaults):

```bash
cp config.json.example config.json
cp personas.json.example personas.json
```

- `config.json` — API keys and local provider URLs (`<provider>_api_key`, `<provider>_url`). **Git-ignored.**
- `personas.json` — your persona library. **Git-ignored.**
- The DB path for the read-only mirror and usage/history SQLite files live alongside the app.

Most settings are editable right in the UI, so you rarely need to touch these by hand.

---

## 🧑‍💻 Development

The frontend is React + Vite. To work on it:

```bash
cd web
npm install
npm run dev      # Vite dev server, proxies API + WS to the Python backend
```

When you're done, rebuild the committed bundle so the app runs without Node:

```bash
npm run build    # refreshes web/dist  (commit the result)
```

Run the Python backend separately with `python web_server.py`.

**Keeping this README honest:** when you add or change a user-facing feature, update the *Feature tour* and *Providers* sections in the same PR. Future-you (and contributors) will thank you.

---

## 🖥️ Legacy interfaces

The original desktop and terminal apps still work but are no longer the focus:

- **Tkinter desktop app:** `python auto_chat.py`
- **CLI:** `python cli_chat.py`
- **Standalone persona generator:** `python persona_generator.py`

New development happens on the web app.

---

## 🗺️ Roadmap ideas

- Per-persona avatars
- Voice / TTS playback of turns
- Branch a conversation at any point ("what if they'd said…")
- Tournament mode: many casts, scored by a judge model

PRs and ideas welcome.

---

## 📄 License

MIT — see [LICENSE](LICENSE).
