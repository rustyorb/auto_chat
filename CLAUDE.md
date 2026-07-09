# Auto Chat — agent notes

## HANDOFF — session of 2026-07-09 (read this first)
Current state, left by the previous Claude session:
- The React+FastAPI web app is COMPLETE but lives ONLY on branch
  `claude/implement-improvements-011CUXPvVmiyyz79MMSaNiqp` — it is NOT
  merged into main yet. If you are on main and see no `web_server.py`,
  run: `git checkout claude/implement-improvements-011CUXPvVmiyyz79MMSaNiqp`
- First goals on the new machine (the LM Studio box, formerly ".177"):
  1. Check out the branch above.
  2. Run `start_webapp.bat` (or `python web_server.py`) → http://127.0.0.1:8008
  3. LM Studio is LOCAL here — if port 1234 is unreachable, use the UI's
     "set URL…" with `127.0.0.1:1235` (user runs it on port 1235).
  4. Get a real 2-3 persona conversation working end-to-end — the user has
     NEVER seen this app work; that is the finish line.
  5. Then help the user merge the branch into main (click-by-click GitHub
     instructions; they are not git-fluent) and delete the branch.
- Old tkinter app (`auto_chat.py`) is legacy; web is primary.
- The user's other agent (Codex) has touched this repo before — verify
  remote state with `git fetch --prune` before assuming anything.

## What this is
AI-vs-AI conversation app. 2–10 personas, each on its own model, mixing
providers (Ollama, LM Studio, OpenAI, OpenRouter) in one conversation.

Two frontends:
- **Web (primary)**: `python web_server.py` → http://127.0.0.1:8008.
  FastAPI (`web_server.py`) + engine (`chat_engine.py`) + React/Vite
  (`web/`). WebSocket `/ws` streams typed events; new clients get a full
  snapshot on connect. `web/dist` is COMMITTED so the app runs without
  Node — after editing `web/src`, run `cd web && npm run build` and commit
  the new dist.
- **Tkinter (legacy)**: `python auto_chat.py`. Still works; don't invest
  further unless asked.

## Architecture map
- `chat_engine.py` — UI-agnostic conversation loop, emits events via
  callback. Each cast member gets its OWN client instance (never share
  clients across personas — models would clobber each other).
- `api_clients.py` — provider clients; retry w/ backoff; token usage is
  reset per call and captured from streaming + non-streaming responses.
- Provider base URLs and API keys live in `config.json`
  (`<provider>_url`, `<provider>_api_key`), normalized by
  `chat_engine.normalize_provider_url`.
- `utils/usage_tracker.py` — SQLite token/cost tracking.
- `conversation_templates.py` — template names are slugged before
  touching the filesystem (path-traversal guard); keep it that way.

## Testing
- Compile: `python -m py_compile <files>`.
- Engine e2e: fake clients driving `ConversationEngine` (see PR history).
- GUI (tkinter): xvfb-run; browser: Playwright with the preinstalled
  Chromium at /opt/pw-browsers/chromium.

## User preferences (rustyorb) — honor these
- **Always ship `start_webapp.bat` / `stop_webapp.bat`** (or equivalent
  start/stop scripts) for any web app in this or future projects.
  Start = launch server minimized + open browser; Stop = kill by port.
- Not git-fluent: give click-by-click GitHub UI instructions, never
  assume rebase/cherry-pick knowledge. Keep the repo at ONE branch
  (main) plus at most one active work branch.
- Budget-conscious: keep agent runs lean; avoid huge exploratory reads.
- Their LAN: LM Studio serves ~30 models at `192.168.0.177:1235/v1`
  (set via the UI's "set URL…" or `lmstudio_url` in config.json);
  Ollama is installed locally but NOT left running — remind them to
  start it before use.
- Other agents (Codex) sometimes touch this repo; before assuming repo
  state, `git fetch --prune` and verify.
