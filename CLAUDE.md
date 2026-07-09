# Auto Chat — agent notes

## HANDOFF — updated 2026-07-09 (quality pass)
- Prompt overhaul (persona.get_system_prompt): the old 14-rule shouty block
  had ~10 prohibitions (six NEVERs), a typo (REPETATIVE), the "push forward"
  directive stated 4×, and a contradiction (rule "NEVER discuss being an AI"
  vs the whole AI-persona feature). Rewrote it POSITIVE-framed: profile + 6
  "how to play the scene" bullets + one soft guard. Fewer, gentler negatives
  → less stilted output on small local models. Non-human personas already
  omit Age/Gender lines.
- Interjections de-escalated: narrator/system/topic notes were wrapped as
  "EMERGENCY ALERT" / "URGENT SCENE CHANGE - REACT IMMEDIATELY" and re-fired
  for 3 turns. Now phrased calmly ("[Scene / narration]: …", "The topic is
  now …") and reacted to once (recent_system checks only conversation[-1]).
- Engine bugs fixed (from a code audit): (1) stop→start thread race — a
  stale worker's finally could clobber the new run; added a `_run_id`
  generation token so a superseded loop tears down nothing. (2) Stop
  mid-stream left a blank placeholder message (saved to history + index
  drift); now dropped + `message_remove` emitted, matching the
  APIRequestError path (which now also always removes its placeholder).
  (3) snapshot/export/summarize read `conversation` unlocked while the
  worker mutated it → added `engine.messages_copy()` (locked). (4) Cost was
  $0 for anthropic/venice/grok (no PRICING rows) — added them. (5)
  Substring pricing mis-matched "gpt-4" before "gpt-4o" (6× overcharge) —
  now longest-key match. (6) history turn_count counted interjections —
  now spoken turns only.
- Cadence: physical-action spam (constant sit/stand/window loops) fixed via
  the continuity guidance in the persona prompt. Measured after: 0 sit/
  stand/window beats, ~1 action/turn (was 3–5).

## HANDOFF — updated 2026-07-09 (on the LM Studio box)
- The app now RUNS on this machine: branch checked out, deps installed,
  `config.json` created with `lmstudio_url: http://127.0.0.1:1235/v1`,
  server verified at http://127.0.0.1:8008, and a real 3-persona LM Studio
  conversation completed end-to-end.
- Two bugs found and fixed this session:
  1. `utils/config_utils.py` — the // comment-stripper ate the `//` inside
     URL strings ("http://…"), corrupting config.json on every load, which
     silently reset the LM Studio URL to the default port 1234. Stripper
     now skips string literals.
  2. `chat_engine.py` — thinking models (qwen3.5 etc.) sometimes put the
     whole turn into `reasoning_content` and stream zero `content`,
     yielding a blank message that then became the next speaker's prompt.
     The engine now retries an empty turn (up to 2×) and never feeds an
     empty `last_content` forward.
- Feature sprint (same day, autonomous session): per-persona
  temperature/max_tokens, visible thinking (reasoning_content streamed as
  `thinking_chunk` events + collapsible UI blocks), continue/regenerate/
  resume-from-history (engine `run_target` drives the loop; auto-save
  replaces its previous history row via `_history_id` so continues don't
  duplicate), turn_delay, model-search combobox, AI persona generator
  (`POST /api/personas/generate`), one-click summaries
  (`POST /api/conversation/summarize`), localStorage setup persistence.
  Gotcha found: a small max_tokens cap gets eaten entirely by reasoning
  on thinking models → engine lifts the cap when retrying an empty turn
  (`_retry_turn`).
- Bug-fix pass (Opus session, same day): two user-reported bugs fixed —
  (a) persona generator always produced boxed-in human personas: its JSON
  schema demanded a human name/age/gender. Rewrote the generator system
  prompt (web_server `generate_persona`) to allow ANY entity (AI, object,
  concept…) and follow the description literally; age is now free-form,
  gender defaults "n/a". `persona.get_system_prompt` omits Age/Gender for
  non-human personas so the conversation doesn't re-humanize them.
  (b) personas repeated/derailed within a few turns: the loop echoed the
  previous message as the `prompt` AND included it as the last history
  entry, so the model saw it twice and parroted it. `_build_api_history`
  now takes `drop_last` to remove that duplication; also added mild
  anti-repetition penalties (frequency/presence for OpenAI-style,
  repeat_penalty for Ollama) in config.py.
- Providers added: openai + openrouter already existed; added
  **anthropic** (dedicated Messages-API client with streaming + thinking),
  **venice** (OpenAI-compatible), **grok**/xAI (OpenAI-compatible). All in
  CLIENT_FACTORIES + PROVIDERS_REQUIRING_KEY; the UI's per-model
  "set API key…" flow handles their keys. Base URLs in config.py.
  OpenAI model list no longer filters to only "gpt" (shows o-series too).
- config.json holds the user's real OpenAI + OpenRouter keys — it is
  gitignored; NEVER git add it.
- REMAINING: user merges PR #17 on GitHub (not git-fluent — the PR is
  ready; merging is one click), then deletes the branch so the repo is
  back to one branch.
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
  The loop runs until `run_target` (not `max_turns` — continue/regenerate
  move the target). WS event types the UI depends on: snapshot, status,
  turn, typing, typing_end, message_start, message_chunk, thinking_chunk,
  message_complete, message_remove, run_state, usage, error, done.
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
