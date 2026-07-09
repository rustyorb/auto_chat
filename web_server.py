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


@app.get("/api/personas")
def get_personas():
    return [p.to_dict() for p in load_personas()]


@app.post("/api/personas")
def create_persona(body: PersonaIn):
    personas = load_personas()
    if any(p.name == body.name for p in personas):
        raise HTTPException(409, f"Persona '{body.name}' already exists")
    personas.append(Persona(body.name, body.personality, body.age, body.gender,
                            body.fallback_provider or None, body.fallback_model or None))
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
    if not save_personas(personas):
        raise HTTPException(500, "Failed to save personas")
    return {"ok": True}


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


class StartIn(BaseModel):
    cast: List[CastIn]
    topic: str
    max_turns: int = 20
    turn_order: str = "round-robin"
    streaming: bool = True


@app.post("/api/conversation/start")
def start_conversation(body: StartIn):
    if engine.is_running:
        raise HTTPException(409, "A conversation is already running")
    if not 2 <= len(body.cast) <= 10:
        raise HTTPException(400, "Cast must have between 2 and 10 members")

    personas = {p.name: p for p in load_personas()}
    cfg = load_app_config()
    cast = []
    for item in body.cast:
        persona = personas.get(item.persona)
        if not persona:
            raise HTTPException(404, f"Persona '{item.persona}' not found")
        if not item.model:
            raise HTTPException(400, f"No model selected for {item.persona}")
        try:
            cast.append(CastMember(persona, item.provider, item.model, cfg))
        except ValueError as e:
            raise HTTPException(400, str(e))

    try:
        engine.configure(cast, body.topic, body.max_turns, body.turn_order, body.streaming)
        engine.start()
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


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


@app.get("/api/conversation/export")
def export_current(format: str = "md"):
    if not engine.conversation:
        raise HTTPException(404, "No conversation to export")
    if format == "json":
        payload = json.dumps({
            "metadata": {"theme": engine.topic},
            "conversation": engine.conversation,
        }, indent=2)
        media, ext = "application/json", "json"
    elif format == "md":
        lines = [f"# {engine.topic}\n",
                 f"_Exported {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]
        for msg in engine.conversation:
            lines.append(f"**{msg['persona']}**  \n{msg['content']}\n")
        payload = "\n".join(lines)
        media, ext = "text/markdown", "md"
    else:
        lines = [f"Conversation: {engine.topic}", "-" * 30, ""]
        for msg in engine.conversation:
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
def get_history(search: Optional[str] = None, favorites: bool = False, limit: int = 100):
    return engine.history_manager.list_conversations(
        limit=limit, search_query=search or None, favorites_only=favorites)


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
