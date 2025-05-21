import argparse
import os
from typing import List, Dict

from persona import Persona
from api_clients import OllamaClient, LMStudioClient, OpenRouterClient, OpenAIClient
from utils.config_utils import load_jsonc
from utils.analytics import summarize_conversation

CONFIG_FILE = "config.json"
PERSONAS_FILE = "personas.json"


def load_personas() -> List[Persona]:
    if os.path.exists(PERSONAS_FILE):
        data = load_jsonc(PERSONAS_FILE)
        if isinstance(data, list):
            return [Persona.from_dict(p) for p in data]
    return []


def create_client(provider: str, api_key: str = ""):
    if provider == "ollama":
        return OllamaClient()
    if provider == "lmstudio":
        return LMStudioClient()
    if provider == "openrouter":
        return OpenRouterClient(api_key=api_key)
    if provider == "openai":
        return OpenAIClient(api_key=api_key)
    raise ValueError(f"Unknown provider: {provider}")


def main():
    parser = argparse.ArgumentParser(description="Run AI chat in CLI mode")
    parser.add_argument("persona1")
    parser.add_argument("persona2")
    parser.add_argument("provider1")
    parser.add_argument("model1")
    parser.add_argument("provider2")
    parser.add_argument("model2")
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--theme", default="free conversation")
    args = parser.parse_args()

    config = load_jsonc(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else {}
    personas = {p.name: p for p in load_personas()}
    p1 = personas.get(args.persona1)
    p2 = personas.get(args.persona2)
    if not p1 or not p2:
        raise SystemExit("Invalid persona names")

    client1 = create_client(args.provider1, config.get(f"{args.provider1}_api_key", ""))
    client2 = create_client(args.provider2, config.get(f"{args.provider2}_api_key", ""))
    client1.set_model(args.model1)
    client2.set_model(args.model2)

    conversation: List[Dict[str, str]] = []
    current_turn = 0
    while current_turn < args.turns:
        actor_idx = current_turn % 2
        persona = p1 if actor_idx == 0 else p2
        client = client1 if actor_idx == 0 else client2
        system_prompt = persona.get_system_prompt(args.theme)
        history = conversation[-20:]
        prompt = conversation[-1]["content"] if conversation else args.theme
        response = client.generate_response(prompt, system_prompt, history)
        conversation.append({
            "role": "assistant" if actor_idx == 0 else "user",
            "persona": persona.name,
            "content": response
        })
        print(f"{persona.name}: {response}\n")
        current_turn += 1

    print("\n" + summarize_conversation(conversation))


if __name__ == "__main__":
    main()
