#!/usr/bin/env python3
"""Simple command-line interface for AI-to-AI conversations."""

import argparse
import os
from typing import List, Dict

from api_clients import OllamaClient, LMStudioClient, OpenRouterClient, OpenAIClient
from persona import Persona
from utils.config_utils import load_json_with_comments
from utils.analytics import summarize_conversation
from config import CONFIG_FILE, PERSONAS_FILE, DEFAULT_HISTORY_LIMIT


def load_personas() -> List[Persona]:
    if os.path.exists(PERSONAS_FILE):
        data = load_json_with_comments(PERSONAS_FILE)
        if isinstance(data, list):
            persona_list = data
        else:
            persona_list = data.get("personas", [])
        return [Persona.from_dict(p) for p in persona_list]
    return []


def load_config() -> Dict[str, str]:
    if os.path.exists(CONFIG_FILE):
        return load_json_with_comments(CONFIG_FILE)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Run AI chat in the terminal")
    parser.add_argument("--model1", required=True, help="Model for persona 1")
    parser.add_argument("--model2", required=True, help="Model for persona 2")
    parser.add_argument("--persona1", help="Name of first persona")
    parser.add_argument("--persona2", help="Name of second persona")
    parser.add_argument("--provider1", default="ollama", help="Provider for persona 1")
    parser.add_argument("--provider2", default="ollama", help="Provider for persona 2")
    parser.add_argument("--turns", type=int, default=10, help="Number of turns")
    parser.add_argument("--theme", default="free conversation", help="Conversation theme")
    args = parser.parse_args()

    personas = load_personas()
    if not personas:
        raise SystemExit("No personas available")

    p1 = next((p for p in personas if p.name == args.persona1), personas[0])
    if len(personas) > 1:
        p2 = next((p for p in personas if p.name == args.persona2), personas[1])
    else:
        p2 = p1

    config = load_config()

    clients = {
        "ollama": OllamaClient(),
        "lmstudio": LMStudioClient(),
        "openrouter": OpenRouterClient(api_key=config.get("openrouter_api_key", "")),
        "openai": OpenAIClient(api_key=config.get("openai_api_key", "")),
    }

    c1 = clients[args.provider1]
    c2 = clients[args.provider2]
    c1.set_model(args.model1)
    c2.set_model(args.model2)

    conversation: List[Dict[str, str]] = []
    last_prompt = "Let's start the conversation."
    for turn in range(args.turns):
        actor_index = turn % 2
        persona = p1 if actor_index == 0 else p2
        client = c1 if actor_index == 0 else c2
        history = conversation[-DEFAULT_HISTORY_LIMIT:]
        system_prompt = persona.get_system_prompt(args.theme)
        response = client.generate_response(prompt=last_prompt, system=system_prompt, conversation_history=history)
        response = response.strip()
        role = "assistant" if actor_index == 0 else "user"
        message = {"role": role, "persona": persona.name, "content": response}
        conversation.append(message)
        print(f"{persona.name}: {response}\n")
        last_prompt = response

    print("\n" + summarize_conversation(conversation))


if __name__ == "__main__":
    main()
