"""Configuration constants for the auto_chat application."""

# API Configuration
DEFAULT_TIMEOUT = 60  # seconds
MODEL_LIST_TIMEOUT = 10  # seconds
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2000

# LLM Provider URLs
OLLAMA_DEFAULT_URL = "http://127.0.0.1:11434"
LMSTUDIO_DEFAULT_URL = "http://localhost:1234/v1"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1"
OPENAI_API_URL = "https://api.openai.com/v1"

# Conversation Settings
DEFAULT_MAX_TURNS = 20
DEFAULT_HISTORY_LIMIT = 20  # Number of messages to keep in context
DEFAULT_TOPIC = "A casual chat about AI."

# File Paths
LOG_FILE = "chatroom_log.txt"
PERSONAS_FILE = "personas.json"
CONFIG_FILE = "config.json"

# UI Configuration
DEFAULT_WINDOW_WIDTH = 1000
DEFAULT_WINDOW_HEIGHT = 700
MIN_WINDOW_WIDTH = 800
MIN_WINDOW_HEIGHT = 600
DEFAULT_THEME = "darkly"

# Age Ranges for Persona Generation
AGE_RANGES = {
    "Young Adult": (4, 14),
    "Adult": (15, 25),
    "Middle-Aged": (30, 45),
    "Senior": (46, 85),
    "AI Entity": (9, 99)
}

# Character Types for Persona Generation
CHARACTER_TYPES = [
    "Academic/Intellectual",
    "Artist/Creative",
    "Business Professional",
    "Scientist/Researcher",
    "Medical Professional",
    "Technology Expert",
    "Adventurer/Explorer",
    "Educator/Teacher",
    "Philosopher/Thinker",
    "Humanitarian/Activist",
    "Engineer/Builder",
    "Writer/Storyteller",
    "Historian/Archivist",
    "Diplomat/Negotiator",
    "Athlete/Physical Expert",
    "Craftsperson/Artisan",
    "AI Entity"
]

# Gender Options
GENDERS = ["male", "female", "non-binary", "AI Entity"]
