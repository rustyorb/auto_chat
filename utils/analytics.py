from typing import List, Dict


def summarize_conversation(convo: List[Dict[str, str]]) -> str:
    """Generate a simple summary of the conversation."""
    total_turns = len(convo)
    personas = {}
    for msg in convo:
        persona = msg.get("persona", "?")
        personas[persona] = personas.get(persona, 0) + 1
    lines = [f"Total turns: {total_turns}"]
    for persona, count in personas.items():
        lines.append(f"{persona}: {count} turns")
    return "\n".join(lines)
