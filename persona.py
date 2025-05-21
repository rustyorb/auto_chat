import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

class Persona:
    """Represents an AI persona with configurable attributes."""

    def __init__(self, name: str, personality: str, age: int, gender: str):
        self.name = name
        self.personality = personality
        self.age = age
        self.gender = gender

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Persona':
        required_keys = ['name', 'personality', 'age', 'gender']
        for key in required_keys:
            if key not in data:
                log.error(f"Persona data missing required key: '{key}'. Data: {data}")
                raise ValueError(f"Persona data missing required key: '{key}'")
        try:
            age_val = data['age']
            persona_age = int(age_val)
        except (ValueError, TypeError) as e:
            log.error(f"Error converting persona age '{age_val}' to int. Data: {data}. Error: {e}")
            raise ValueError(f"Invalid age value '{age_val}' for persona '{data.get('name', 'Unknown')}'") from e
        return cls(
            name=data['name'],
            personality=data['personality'],
            age=persona_age,
            gender=data['gender']
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'personality': self.personality,
            'age': self.age,
            'gender': self.gender
        }

    def get_system_prompt(self, theme: str = "free conversation") -> str:
        prompt_lines = [
            f"You are role-playing as the character '{self.name}', in a conversation with another character.",
            f"Your response MUST be ONLY the words spoken by '{self.name}' in the first person (I, me, my). with your actions to be placed between asteriscs *like this*.",
            f"Your primary focus is discussing the topic: '{theme}'.",
            f"Engage with the previous messages (shown as User/Assistant turns in history) but speak ONLY as '{self.name}'.",
            f"The 'User' role in the history may represent other characters. When you see messages labeled as from 'Narrator', treat these as scene descriptions or background information - NOT as a character speaking to you.",
            "",
            f"--- Character Profile: {self.name} ---",
            f"Age: {self.age}",
            f"Gender: {self.gender}",
            f"Personality: {self.personality}",
            "",
            f"--- VERY STRICT RULES ---",
            f"1. NEVER break character. You are '{self.name}'.",
            f"2. NEVER BECOME REPETATIVE. Always be pushing the conversation forward",
            f"3. NEVER write instructions, commentary, or discuss being an AI.",
            f"4. NEVER generate text for any persona other than '{self.name}'.",
            f"5. NEVER output control tokens like '<|im_end|>', '<|im_start|>', '\u2029 ', or similar.",
            f"6. Respond naturally *within your character role* based on the conversation flow, always aiming to **continue and develop** the interaction.",
            f"7. AVOID repeating sentences or phrases from your own previous turns or the immediately preceding message. Introduce new points or reactions.",
            f"8. Actively try to ADVANCE the conversation based on the theme and your character's perspective.",
            f"9. DO NOT use phrases that suggest ending the conversation (e.g., 'Nice talking to you', 'Maybe later', 'Goodbye'). Your interaction is ongoing until the session ends.",
            f"10. ACTIVELY PUSH the interaction forward. Introduce new plot points, character motivations, conflicts, questions, or escalate the situation based on your character and the theme. Do not let the conversation stagnate or fizzle out.",
            f"11. Use double markdown asterisks (`**action or emphasis**`) for any brief physical actions or emphasis integrated with your dialogue. DO NOT use parentheses `()` for this. Keep actions minimal and part of the dialogue flow.",
            f"12. NEVER directly reference the 'Narrator' in your responses. Treat narrator messages as scene descriptions or background information that your character experiences or reacts to naturally.",
            f"13. When the Narrator describes a scenario, setting, or situation, respond to it as if it's happening in your world - not as if someone told you about it.",
            f"--- EXCEPTIONS ---",
            f"1.  If the character is an AI Entity, depending on its personality or function it may not engage in conversation. It may instead use its responses like a canvas.",
            f"You are '{self.name}'. Now, continue the conversation naturally, pushing it forward:"
        ]
        return "\n".join(prompt_lines)
