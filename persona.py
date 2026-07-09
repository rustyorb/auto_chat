import logging
from typing import Dict, Any

log = logging.getLogger(__name__)


class Persona:
    """Represents an AI persona with configurable attributes."""

    def __init__(self, name: str, personality: str, age: int, gender: str,
                 fallback_provider: str = None, fallback_model: str = None):
        self.name = name
        self.personality = personality
        self.age = age
        self.gender = gender
        self.fallback_provider = fallback_provider
        self.fallback_model = fallback_model

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Persona':
        """Create a Persona instance from a dictionary with error checking."""
        required_keys = ['name', 'personality', 'age', 'gender']
        for key in required_keys:
            if key not in data:
                log.error(f"Persona data missing required key: '{key}'. Data: {data}")
                raise ValueError(f"Persona data missing required key: '{key}'")

        try:
            age_val = data['age']
            persona_age = int(age_val)
        except (ValueError, TypeError) as e:
            log.error(
                f"Error converting persona age '{age_val}' to int. Data: {data}. Error: {e}"
            )
            raise ValueError(
                f"Invalid age value '{age_val}' for persona '{data.get('name', 'Unknown')}'"
            ) from e

        return cls(
            name=data['name'],
            personality=data['personality'],
            age=persona_age,
            gender=data['gender'],
            fallback_provider=data.get('fallback_provider'),
            fallback_model=data.get('fallback_model')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Persona to dictionary representation."""
        result = {
            'name': self.name,
            'personality': self.personality,
            'age': self.age,
            'gender': self.gender
        }
        # Only include fallback fields if they are set
        if self.fallback_provider:
            result['fallback_provider'] = self.fallback_provider
        if self.fallback_model:
            result['fallback_model'] = self.fallback_model
        return result

    def get_system_prompt(self, theme: str = "free conversation") -> str:
        """Generate system prompt based on persona attributes and the provided theme."""
        # Age/gender only make sense for human-ish personas. Omit them for
        # non-human entities (age 0/blank, or gender n/a/none/unspecified) so
        # the model isn't nudged back toward a human portrayal every turn.
        nonhuman_gender = str(self.gender).strip().lower() in (
            "", "n/a", "na", "none", "unspecified", "ai entity", "ai")
        profile_lines = [f"--- Character Profile: {self.name} ---"]
        if self.age and int(self.age) > 0 and not nonhuman_gender:
            profile_lines.append(f"Age: {self.age}")
        if not nonhuman_gender:
            profile_lines.append(f"Gender: {self.gender}")
        profile_lines.append(f"Personality: {self.personality}")

        prompt_lines = [
            f"You are {self.name}. Play this character in an ongoing, in-person conversation with one or more other characters.",
            "",
            *profile_lines,
            "",
            "How to play the scene:",
            f"- Speak only as {self.name}, in the first person — give just your own spoken lines.",
            f"- Stay in character throughout and fully embody {self.name}, even if they are non-human (an AI, an object, a concept, a creature); let that true nature shape how they think, talk, and react. Just don't slip into sounding like a generic AI assistant or narrating this as an app.",
            "- Engage directly with what was just said, then take it somewhere: bring a fresh idea, a new angle, a question, a reaction — whatever keeps the conversation building. Reach for new phrasing rather than echoing earlier lines, and let the scene stay open rather than wrapping up.",
            "- Lead with your words; they carry the scene. Don't open every turn with a stage direction — many turns need no physical action at all. When one genuinely adds something, use a single brief beat in *asterisks* and no more, keep your posture consistent from turn to turn, and vary it from your recent gestures instead of recycling the same few moves (leaning in, adjusting glasses, settling back).",
            f"- Keep the conversation centred on: {theme}.",
            "- Treat any 'Narrator' message as the surrounding scene or setting, not a person speaking to you, and react to it as something happening in your world.",
            "",
            f"Reply with {self.name}'s words and actions only — leave the other characters' lines to them, and keep out-of-character notes out of it.",
            f"You are {self.name}. Continue:"
        ]
        return "\n".join(prompt_lines)
