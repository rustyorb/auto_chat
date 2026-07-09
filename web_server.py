#!/usr/bin/env python3
"""
web_server.py - FastAPI backend for the Auto Chat web UI

Serves the REST API + WebSocket event stream, and (when built) the React
frontend from web/dist. Run with:

    uvicorn web_server:app --port 8008
or:
    python web_server.py
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from persona import Persona
from chat_engine import (
    ConversationEngine, CastMember, CLIENT_FACTORIES, PROVIDERS_REQUIRING_KEY,
    load_personas, save_personas, load_app_config, save_app_config, make_client,
    normalize_provider_url,
)
from conversation_templates import (
    ConversationTemplate, initialize_templates, list_templates,
    save_template, delete_template,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="[%X]")
log = logging.getLogger("web_server")

app = FastAPI(title="Auto Chat Studio", version="2.0")

# --- Event bus: engine worker thread -> websocket clients ------------------

_clients: List[WebSocket] = []
_loop: Optional[asyncio.AbstractEventLoop] = None


def _broadcast_from_thread(event: Dict[str, Any]) -> None:
    """Called from the engine's worker thread; hop onto the asyncio loop."""
    if _loop is not None:
        asyncio.run_coroutine_threadsafe(_broadcast(event), _loop)


async def _broadcast(event: Dict[str, Any]) -> None:
    dead = []
    for ws in _clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _clients:
            _clients.remove(ws)


engine = ConversationEngine(_broadcast_from_thread)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()
    initialize_templates()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    # Bring the new client up to date immediately
    await ws.send_json(engine.snapshot())
    try:
        while True:
            await ws.receive_text()  # keepalive; we don't expect client messages
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _clients:
            _clients.remove(ws)


# --- Personas ---------------------------------------------------------------

class PersonaIn(BaseModel):
    name: str
    personality: str
    age: int
    gender: str
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    avatar: Optional[str] = None


@app.get("/api/personas")
def get_personas():
    return [p.to_dict() for p in load_personas()]


@app.post("/api/personas")
def create_persona(body: PersonaIn):
    personas = load_personas()
    if any(p.name == body.name for p in personas):
        raise HTTPException(409, f"Persona '{body.name}' already exists")
    personas.append(Persona(body.name, body.personality, body.age, body.gender,
                            body.fallback_provider or None, body.fallback_model or None,
                            avatar=(body.avatar or "").strip()[:4] or None))
    if not save_personas(personas):
        raise HTTPException(500, "Failed to save personas")
    return {"ok": True}


@app.put("/api/personas/{name}")
def update_persona(name: str, body: PersonaIn):
    personas = load_personas()
    persona = next((p for p in personas if p.name == name), None)
    if not persona:
        raise HTTPException(404, f"Persona '{name}' not found")
    persona.name = body.name
    persona.personality = body.personality
    persona.age = body.age
    persona.gender = body.gender
    persona.fallback_provider = body.fallback_provider or None
    persona.fallback_model = body.fallback_model or None
    persona.avatar = (body.avatar or "").strip()[:4] or None
    if not save_personas(personas):
        raise HTTPException(500, "Failed to save personas")
    return {"ok": True}


class GeneratePersonaIn(BaseModel):
    description: str
    provider: str
    model: str


@app.post("/api/personas/generate")
async def generate_persona(body: GeneratePersonaIn):
    """Draft a persona from a one-line description using an LLM. Returns the
    draft without saving it; the client decides whether to keep it."""
    if not body.description.strip():
        raise HTTPException(400, "Description is required")
    try:
        client = make_client(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    client.set_model(body.model)

    system = (
        "You are a character designer for an open-ended AI conversation "
        "sandbox. Bring the user's description to life EXACTLY as written — "
        "follow their intent literally and do not sanitize, normalize, or "
        "substitute your own idea.\n\n"
        "The persona can be ANYTHING: a rogue LLM, a sentient toaster, an "
        "ancient god, an abstract concept, an alien hive-mind, a talking "
        "storm, a glitchy chatbot, a human — whatever the description implies. "
        "Do NOT default to a human if the description points elsewhere. "
        "Non-human entities usually have no meaningful age or gender — use "
        "\"n/a\" for those, or a fitting value (e.g. age = a version number, "
        "gender = \"none\"/\"unspecified\"). Never force human traits onto a "
        "non-human concept.\n\n"
        "There are no content restrictions on personality, tone, or theme — "
        "match the vibe the user asked for, however weird, edgy, or playful.\n\n"
        "Reply with ONLY a JSON object (no prose, no code fences, no commentary) "
        "with exactly these keys:\n"
        '{"name": "an evocative name or handle", "age": "n/a or a number or a '
        'fitting value", "gender": "n/a unless clearly relevant", "personality": '
        '"3-5 sentences: what it is, how it speaks, its quirks, drives, and '
        'point of view — vivid and specific to the description", '
        '"avatar": "one single emoji that captures this persona"}')
    try:
        raw = await asyncio.to_thread(
            client.generate_response,
            prompt=f"Create this persona, exactly as described: {body.description.strip()}",
            system=system, conversation_history=[])
    except Exception as e:
        raise HTTPException(502, f"Generation failed: {e}")

    # Models love wrapping JSON in fences or prose — extract the first object.
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise HTTPException(502, f"Model did not return JSON: {raw[:200]}")
    try:
        draft = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        raise HTTPException(502, f"Model returned invalid JSON: {raw[:200]}")

    for key in ("name", "personality"):
        if not str(draft.get(key, "")).strip():
            raise HTTPException(502, f"Model omitted '{key}'")

    # age is free-form (may be "n/a", a version string, etc.); keep the int
    # column happy while preserving non-numeric answers in the personality.
    raw_age = str(draft.get("age", "")).strip()
    age_digits = "".join(ch for ch in raw_age if ch.isdigit())
    age = int(age_digits) if age_digits else 0
    return {
        "name": str(draft["name"]).strip(),
        "age": age,
        "gender": str(draft.get("gender") or "n/a").strip(),
        "personality": str(draft["personality"]).strip(),
        "avatar": str(draft.get("avatar") or "").strip()[:4],
    }


class SurpriseIn(BaseModel):
    provider: str
    model: str
    vibe: str = ""      # optional flavour, e.g. "cosmic horror", "sitcom"
    cast_size: int = 2  # how many personas to invent (0 = topic only)


@app.post("/api/surprise")
async def surprise_me(body: SurpriseIn):
    """Invent a wild conversation topic and (optionally) a themed cast in one
    shot. Returns {topic, personas: [...]} — the client applies it."""
    try:
        client = make_client(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    client.set_model(body.model)

    cast_size = max(0, min(6, body.cast_size))
    vibe = body.vibe.strip()
    vibe_line = f"Lean into this vibe: {vibe}.\n" if vibe else ""
    system = (
        "You are an imaginative scene generator for an AI role-play sandbox. "
        "Invent a fresh, unexpected, provocative conversation topic and a matching "
        "cast of characters that would clash or spark off each other in fun ways. "
        "Characters can be anyone or anything — people, AIs, objects, gods, "
        "concepts — whatever makes the scene interesting. No content limits.\n"
        "Reply with ONLY a JSON object, no prose or code fences:\n"
        '{"topic": "a vivid one-sentence scene/topic", "personas": '
        '[{"name": "...", "age": "n/a or number", "gender": "n/a unless relevant", '
        '"personality": "2-4 sentences: what they are, how they talk, their angle", '
        '"avatar": "one single emoji"}]}'
        f"\nProvide exactly {cast_size} personas."
        if cast_size else
        "You are an imaginative scene generator. Invent one fresh, unexpected, "
        "provocative conversation topic. Reply with ONLY JSON: {\"topic\": \"...\"}."
    )
    prompt = f"{vibe_line}Surprise me. Make it interesting."
    try:
        raw = await asyncio.to_thread(
            client.generate_response, prompt=prompt, system=system,
            conversation_history=[])
    except Exception as e:
        raise HTTPException(502, f"Generation failed: {e}")

    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise HTTPException(502, f"Model did not return JSON: {raw[:200]}")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        raise HTTPException(502, f"Model returned invalid JSON: {raw[:200]}")

    topic = str(data.get("topic", "")).strip()
    if not topic:
        raise HTTPException(502, "Model omitted a topic")

    personas = []
    for p in (data.get("personas") or [])[:cast_size]:
        name = str(p.get("name", "")).strip()
        personality = str(p.get("personality", "")).strip()
        if not name or not personality:
            continue
        raw_age = str(p.get("age", "")).strip()
        age_digits = "".join(ch for ch in raw_age if ch.isdigit())
        personas.append({
            "name": name,
            "age": int(age_digits) if age_digits else 0,
            "gender": str(p.get("gender") or "n/a").strip(),
            "personality": personality,
            "avatar": str(p.get("avatar") or "").strip()[:4],
        })
    return {"topic": topic, "personas": personas}


@app.delete("/api/personas/{name}")
def delete_persona(name: str):
    personas = load_personas()
    remaining = [p for p in personas if p.name != name]
    if len(remaining) == len(personas):
        raise HTTPException(404, f"Persona '{name}' not found")
    if not save_personas(remaining):
        raise HTTPException(500, "Failed to save personas")
    return {"ok": True}


# --- Providers & models ------------------------------------------------------

@app.get("/api/providers")
def get_providers():
    cfg = load_app_config()
    return [
        {
            "id": key,
            "requires_key": key in PROVIDERS_REQUIRING_KEY,
            "has_key": bool(cfg.get(f"{key}_api_key")),
            "url": cfg.get(f"{key}_url", ""),
            "configurable_url": key in ("ollama", "lmstudio"),
        }
        for key in CLIENT_FACTORIES
    ]


class UrlIn(BaseModel):
    provider: str
    url: str


@app.post("/api/providers/url")
def set_provider_url(body: UrlIn):
    provider = body.provider.lower()
    if provider not in ("ollama", "lmstudio"):
        raise HTTPException(400, f"URL not configurable for {provider}")
    cfg = load_app_config()
    if body.url.strip():
        cfg[f"{provider}_url"] = normalize_provider_url(provider, body.url)
    else:
        cfg.pop(f"{provider}_url", None)  # empty = back to default
    save_app_config(cfg)
    return {"ok": True, "url": cfg.get(f"{provider}_url", "")}


@app.get("/api/models/{provider}")
async def get_models(provider: str):
    provider = provider.lower()
    if provider not in CLIENT_FACTORIES:
        raise HTTPException(404, f"Unknown provider: {provider}")
    try:
        client = make_client(provider)
    except Exception as e:
        raise HTTPException(400, str(e))
    if provider in PROVIDERS_REQUIRING_KEY and not client.api_key:
        raise HTTPException(401, f"API key required for {provider}")
    models = await asyncio.to_thread(client.get_available_models)
    return {"provider": provider, "models": models}


class KeyIn(BaseModel):
    provider: str
    key: str


@app.post("/api/keys")
def set_api_key(body: KeyIn):
    provider = body.provider.lower()
    if provider not in PROVIDERS_REQUIRING_KEY:
        raise HTTPException(400, f"{provider} does not use an API key")
    cfg = load_app_config()
    cfg[f"{provider}_api_key"] = body.key
    save_app_config(cfg)
    return {"ok": True}


# --- Conversation control ----------------------------------------------------

class CastIn(BaseModel):
    persona: str
    provider: str
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class StartIn(BaseModel):
    cast: List[CastIn]
    topic: str
    max_turns: int = 20
    turn_order: str = "round-robin"
    streaming: bool = True
    turn_delay: float = 1.0
    director: bool = False
    director_every: int = 4
    endless: bool = False


def _build_cast(items: List[CastIn], allow_adhoc: bool = False) -> List[CastMember]:
    """Turn CastIn specs into CastMembers. With allow_adhoc, personas missing
    from the library (e.g. deleted since a conversation was saved) are stubbed
    so history can still be resumed."""
    personas = {p.name: p for p in load_personas()}
    cfg = load_app_config()
    cast = []
    for item in items:
        persona = personas.get(item.persona)
        if not persona:
            if not allow_adhoc:
                raise HTTPException(404, f"Persona '{item.persona}' not found")
            persona = Persona(item.persona, f"You are {item.persona}.", 30, "unspecified")
        if not item.model:
            raise HTTPException(400, f"No model selected for {item.persona}")
        try:
            cast.append(CastMember(persona, item.provider, item.model, cfg,
                                   temperature=item.temperature,
                                   max_tokens=item.max_tokens))
        except ValueError as e:
            raise HTTPException(400, str(e))
    return cast


@app.post("/api/conversation/start")
def start_conversation(body: StartIn):
    if engine.is_running:
        raise HTTPException(409, "A conversation is already running")
    if not 2 <= len(body.cast) <= 10:
        raise HTTPException(400, "Cast must have between 2 and 10 members")

    cast = _build_cast(body.cast)
    try:
        engine.configure(cast, body.topic, body.max_turns, body.turn_order,
                         body.streaming, body.turn_delay,
                         director=body.director, director_every=body.director_every,
                         endless=body.endless)
        engine.start()
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


class ContinueIn(BaseModel):
    turns: int = 4


@app.post("/api/conversation/continue")
def continue_conversation(body: ContinueIn):
    try:
        engine.continue_run(body.turns)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/conversation/clear")
def clear_conversation():
    try:
        engine.clear()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/conversation/regenerate")
def regenerate_last():
    try:
        engine.regenerate_last()
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


class LoadIn(BaseModel):
    history_id: int
    cast: List[CastIn]


@app.post("/api/conversation/load")
def load_conversation(body: LoadIn):
    if engine.is_running:
        raise HTTPException(409, "A conversation is already running")
    data = engine.history_manager.get_conversation(body.history_id)
    if not data:
        raise HTTPException(404, "Conversation not found")
    if not 2 <= len(body.cast) <= 10:
        raise HTTPException(400, "Cast must have between 2 and 10 members")

    messages = data.get("conversation", [])
    transcript_names = {m.get("persona") for m in messages
                        if m.get("role") in ("assistant", "user")}
    cast_names = {c.persona for c in body.cast}
    missing = transcript_names - cast_names
    if missing:
        raise HTTPException(400,
                            f"Cast must include everyone in the transcript; missing: {', '.join(sorted(missing))}")

    cast = _build_cast(body.cast, allow_adhoc=True)
    topic = data.get("metadata", {}).get("theme", "Resumed conversation")
    try:
        engine.load_conversation(messages, cast, topic, history_id=body.history_id)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "turns": engine.current_turn, "topic": topic}


class SummarizeIn(BaseModel):
    provider: str
    model: str


@app.post("/api/conversation/judge")
async def judge_conversation(body: SummarizeIn):
    """Score the participants and declare a winner. Same input as summarize."""
    messages = engine.messages_copy()
    spoken = [m for m in messages
              if m.get("role") in ("assistant", "user") and m.get("content")]
    if len(spoken) < 2:
        raise HTTPException(404, "Not enough conversation to judge")
    transcript = "\n\n".join(f"{m['persona']}: {m['content']}" for m in spoken)
    transcript = transcript[-12000:]
    names = sorted({m["persona"] for m in spoken})

    try:
        client = make_client(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    client.set_model(body.model)
    system = (
        "You are a sharp, fair, entertaining judge of conversations and debates. "
        "Given a transcript, deliver a verdict in markdown:\n"
        "1. A one-line **Verdict** naming the strongest participant and why.\n"
        "2. A **Scorecard**: one line per participant with a score out of 10 "
        "and a pointed one-sentence justification (argument quality, wit, "
        "consistency, how well they stayed in character).\n"
        "3. **Best moment** — quote the single best line of the conversation.\n"
        "Be specific and a little theatrical; never invent quotes.")
    try:
        verdict = await asyncio.to_thread(
            client.generate_response,
            prompt=(f"Participants: {', '.join(names)}\n\n"
                    f"Transcript:\n{transcript}\n\nDeliver your verdict."),
            system=system, conversation_history=[])
    except Exception as e:
        raise HTTPException(502, f"Judging failed: {e}")
    return {"verdict": verdict.strip()}


@app.post("/api/conversation/summarize")
async def summarize_conversation(body: SummarizeIn):
    messages = engine.messages_copy()
    if not messages:
        raise HTTPException(404, "No conversation to summarize")
    transcript = "\n\n".join(
        f"{m['persona']}: {m['content']}" for m in messages
        if m.get("role") in ("assistant", "user") and m.get("content"))
    transcript = transcript[-12000:]  # keep the prompt bounded

    try:
        client = make_client(body.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))
    client.set_model(body.model)
    system = ("You summarize conversations. Reply with: one short paragraph of "
              "overall summary, then 3-6 bullet points of the key moments or "
              "arguments, then one line naming who steered the conversation most. "
              "Be concise and specific.")
    try:
        summary = await asyncio.to_thread(
            client.generate_response,
            prompt=f"Summarize this conversation:\n\n{transcript}",
            system=system, conversation_history=[])
    except Exception as e:
        raise HTTPException(502, f"Summarization failed: {e}")
    return {"summary": summary.strip()}


@app.post("/api/conversation/pause")
def pause_conversation():
    engine.pause()
    return {"ok": True, "paused": engine.is_paused}


@app.post("/api/conversation/resume")
def resume_conversation():
    engine.resume()
    return {"ok": True, "paused": engine.is_paused}


@app.post("/api/conversation/stop")
def stop_conversation():
    engine.stop()
    return {"ok": True}


class InterjectIn(BaseModel):
    kind: str  # "topic" | "system" | "narrator"
    content: str


@app.post("/api/conversation/interject")
def interject(body: InterjectIn):
    if body.kind == "topic":
        engine.interject_topic(body.content)
    elif body.kind == "narrator":
        engine.interject_narrator(body.content)
    else:
        engine.interject_system(body.content)
    return {"ok": True}


@app.get("/api/conversation")
def get_conversation():
    return engine.snapshot()


_PERSONA_COLORS = [
    "#4cc9f0", "#f72585", "#ffd166", "#06d6a0", "#c77dff",
    "#ff8fab", "#80ffdb", "#fca311", "#90e0ef", "#e5989b",
]


def _render_html_transcript(topic: str, messages: List[Dict[str, Any]]) -> str:
    """A self-contained, styled HTML page — nice to share or archive."""
    from html import escape
    speakers = []
    for m in messages:
        if m.get("role") in ("assistant", "user") and m["persona"] not in speakers:
            speakers.append(m["persona"])
    color_of = {name: _PERSONA_COLORS[i % len(_PERSONA_COLORS)]
                for i, name in enumerate(speakers)}
    try:
        avatar_of = {p.name: p.avatar for p in load_personas() if p.avatar}
    except Exception:
        avatar_of = {}

    rows = []
    for m in messages:
        role = m.get("role")
        content = escape(m.get("content", "")).replace("\n", "<br>")
        if role in ("system", "narrator"):
            rows.append(f'<div class="note">{content}</div>')
            continue
        color = color_of.get(m["persona"], "#8a919c")
        avatar = avatar_of.get(m["persona"])
        badge = (f'<span class="avatar">{escape(avatar)}</span>' if avatar
                 else f'<span class="dot" style="background:{color}"></span>')
        rows.append(
            f'<div class="msg">'
            f'<div class="who" style="color:{color}">'
            f'{badge}{escape(m["persona"])}</div>'
            f'<div class="body">{content}</div></div>'
        )
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(topic) or 'Auto Chat transcript'}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#1a1d21; color:#e8eaed;
    font:16px/1.6 'Segoe UI',system-ui,-apple-system,sans-serif; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:40px 20px 80px; }}
  h1 {{ font-size:24px; font-weight:700; margin:0 0 4px; }}
  .sub {{ color:#8a919c; font-size:13px; margin-bottom:32px; }}
  .msg {{ margin:0 0 22px; }}
  .who {{ font-weight:700; margin-bottom:4px; display:flex; align-items:center; gap:8px; }}
  .dot {{ width:9px; height:9px; border-radius:50%; display:inline-block; }}
  .avatar {{ font-size:17px; line-height:1; }}
  .body {{ background:#2a2f36; border-radius:10px; padding:12px 14px; }}
  .note {{ text-align:center; color:#8a919c; font-style:italic; font-size:14px; margin:22px 0; }}
  .foot {{ margin-top:48px; text-align:center; color:#5a616c; font-size:12px; }}
</style></head><body><div class="wrap">
<h1>{escape(topic) or 'Untitled conversation'}</h1>
<div class="sub">Auto Chat Studio · exported {stamp}</div>
{''.join(rows)}
<div class="foot">🤖 generated with Auto Chat Studio</div>
</div></body></html>"""


@app.get("/api/conversation/export")
def export_current(format: str = "md"):
    messages = engine.messages_copy()
    if not messages:
        raise HTTPException(404, "No conversation to export")
    if format == "json":
        payload = json.dumps({
            "metadata": {"theme": engine.topic},
            "conversation": messages,
        }, indent=2)
        media, ext = "application/json", "json"
    elif format == "md":
        lines = [f"# {engine.topic}\n",
                 f"_Exported {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]
        for msg in messages:
            lines.append(f"**{msg['persona']}**  \n{msg['content']}\n")
        payload = "\n".join(lines)
        media, ext = "text/markdown", "md"
    elif format == "html":
        payload = _render_html_transcript(engine.topic, messages)
        media, ext = "text/html", "html"
    else:
        lines = [f"Conversation: {engine.topic}", "-" * 30, ""]
        for msg in messages:
            lines.append(f"{msg['persona']} ({msg['role']}):\n{msg['content']}\n")
        payload = "\n".join(lines)
        media, ext = "text/plain", "txt"

    return PlainTextResponse(payload, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="conversation.{ext}"'
    })


# --- Templates ----------------------------------------------------------------

class TemplateIn(BaseModel):
    name: str
    description: str
    persona1_name: str
    persona2_name: str
    initial_topic: str
    max_turns: int = 10
    category: str = "custom"


@app.get("/api/templates")
def get_templates():
    return [t.to_dict() for t in list_templates()]


@app.post("/api/templates")
def create_template(body: TemplateIn):
    t = ConversationTemplate(body.name, body.description, body.persona1_name,
                             body.persona2_name, body.initial_topic,
                             body.max_turns, body.category)
    if not save_template(t):
        raise HTTPException(500, "Failed to save template")
    return {"ok": True}


@app.delete("/api/templates/{name}")
def remove_template(name: str):
    if not delete_template(name):
        raise HTTPException(404, f"Template '{name}' not found")
    return {"ok": True}


# --- History -------------------------------------------------------------------

@app.get("/api/history")
def get_history(search: Optional[str] = None, favorites: bool = False,
                limit: int = 50, offset: int = 0):
    return engine.history_manager.list_conversations(
        limit=limit, offset=offset,
        search_query=search or None, favorites_only=favorites)


@app.delete("/api/history")
def clear_history():
    """Bulk-delete all non-favorite conversations (favorites are kept)."""
    try:
        deleted = engine.history_manager.delete_non_favorites()
    except Exception as e:
        raise HTTPException(500, f"Bulk delete failed: {e}")
    return {"ok": True, "deleted": deleted}


@app.get("/api/history/{conv_id}")
def get_history_item(conv_id: int):
    data = engine.history_manager.get_conversation(conv_id)
    if not data:
        raise HTTPException(404, "Conversation not found")
    return data


@app.post("/api/history/{conv_id}/favorite")
def toggle_favorite(conv_id: int):
    engine.history_manager.toggle_favorite(conv_id)
    return {"ok": True}


@app.delete("/api/history/{conv_id}")
def delete_history_item(conv_id: int):
    engine.history_manager.delete_conversation(conv_id)
    return {"ok": True}


# --- Usage ----------------------------------------------------------------------

@app.get("/api/usage")
def get_usage():
    return {
        "session": engine.usage_tracker.get_session_usage(),
        "total": engine.usage_tracker.get_total_usage(),
        "by_model": engine.usage_tracker.get_usage_by_model(),
        "by_provider": engine.usage_tracker.get_usage_by_provider(),
    }


# --- Static frontend (built React app) -------------------------------------------

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")

if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(DIST_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8008)
