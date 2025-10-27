# Auto Chat Architecture

This document describes the architecture and structure of the Auto Chat project.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [API Integration](#api-integration)
- [Configuration System](#configuration-system)
- [Extending the Application](#extending-the-application)

## Overview

Auto Chat is a Python application that enables AI-to-AI conversations using multiple Large Language Model (LLM) providers. The application is built with a modular architecture that separates concerns and allows for easy extension.

### Key Design Principles

- **Modularity**: Separate modules for API clients, personas, utilities
- **Abstraction**: Base classes for API clients enable easy provider addition
- **Flexibility**: Support for multiple LLM providers and models
- **User Experience**: Both GUI (Tkinter) and CLI interfaces available

## Project Structure

```
auto_chat/
├── auto_chat.py           # Main GUI application entry point
├── cli_chat.py            # Command-line interface
├── api_clients.py         # API client implementations
├── persona.py             # Persona class definition
├── persona_generator.py   # Interactive persona creation tool
├── utils/                 # Utility modules
│   ├── __init__.py
│   ├── analytics.py       # Conversation analysis
│   └── config_utils.py    # Configuration loading utilities
├── config.json.example    # Example API configuration
├── personas.json.example  # Example persona definitions
├── requirements.txt       # Python dependencies
└── README.md             # Main documentation
```

## Core Components

### 1. Main Application (`auto_chat.py`)

The primary GUI application built with Tkinter and ttkbootstrap.

**Key Classes:**
- `AutoChatApp`: Main application class managing the entire GUI
  - Setup screen for configuration
  - Conversation display
  - Control panel for interaction
  - Event handling and threading

**Features:**
- Turn-based conversation management
- Real-time message display
- Pause/Resume functionality
- Narrator mode
- Conversation logging and export
- Persistent configuration

### 2. CLI Interface (`cli_chat.py`)

Command-line version for terminal-based usage.

**Features:**
- Simple text-based interaction
- Same conversation logic as GUI
- Ideal for scripting and automation

### 3. API Clients (`api_clients.py`)

Abstract base class and concrete implementations for different LLM providers.

**Class Hierarchy:**
```
APIClient (ABC)
├── OllamaClient
├── LMStudioClient
├── OpenRouterClient
└── OpenAIClient
```

**APIClient Interface:**
```python
@abstractmethod
def send_message(
    self,
    messages: List[Dict[str, str]],
    model: str,
    **kwargs
) -> Optional[str]:
    """Send messages and get response"""
    pass

@abstractmethod
def list_models(self) -> List[str]:
    """Get available models"""
    pass
```

**Each Client Handles:**
- API endpoint configuration
- Request formatting
- Response parsing
- Error handling
- Model listing

### 4. Persona System (`persona.py`)

The `Persona` class encapsulates AI personality and behavior.

**Attributes:**
- `name`: Persona identifier
- `system_prompt`: Instructions defining behavior
- `model`: LLM model to use
- `provider`: API provider
- `temperature`: Randomness parameter
- `max_tokens`: Response length limit

**Methods:**
- JSON serialization/deserialization
- Persona validation

### 5. Persona Generator (`persona_generator.py`)

Interactive CLI tool using the `rich` library for creating and managing personas.

**Features:**
- Guided persona creation
- Template-based generation
- Direct file saving
- User-friendly TUI

### 6. Utilities (`utils/`)

#### `analytics.py`
- Conversation analysis
- Summary generation
- Statistics calculation

#### `config_utils.py`
- JSONC file loading (JSON with comments)
- Configuration validation
- Error handling

## Data Flow

### Conversation Flow

```
1. User Setup
   ├── Select Persona A & B
   ├── Choose API Providers
   ├── Set Models
   └── Configure Parameters

2. Conversation Initialization
   ├── Load API Clients
   ├── Initialize Personas
   └── Setup Message History

3. Turn-Based Loop
   ├── Persona A
   │   ├── Prepare context (history + system prompt)
   │   ├── API call via client
   │   └── Display response
   ├── Update history
   ├── Persona B
   │   ├── Prepare context
   │   ├── API call
   │   └── Display response
   └── Update history

4. Optional Narrator
   └── Inject system message into conversation

5. Conversation End
   ├── Display summary
   └── Save log (optional)
```

### Message Context Structure

Each API call includes:
```python
[
    {"role": "system", "content": persona.system_prompt},
    {"role": "user", "content": previous_message},
    {"role": "assistant", "content": persona_response},
    # ... conversation history
]
```

## API Integration

### Adding a New API Provider

1. Create a new client class in `api_clients.py`:
```python
class NewProviderClient(APIClient):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.newprovider.com/v1"

    def send_message(self, messages, model, **kwargs):
        # Implementation
        pass

    def list_models(self):
        # Implementation
        pass
```

2. Update `config.json` with provider settings:
```json
{
    "newprovider": {
        "api_key": "your_key",
        "base_url": "https://api.newprovider.com/v1"
    }
}
```

3. Add provider option in UI/CLI

### Supported Providers

| Provider | Base URL | Authentication |
|----------|----------|----------------|
| Ollama | http://localhost:11434 | None |
| LM Studio | http://localhost:1234 | None |
| OpenRouter | https://openrouter.ai/api/v1 | API Key |
| OpenAI | https://api.openai.com/v1 | API Key |

## Configuration System

### Configuration Files

**`config.json`** - API settings
```json
{
    "ollama": {
        "base_url": "http://localhost:11434"
    },
    "lmstudio": {
        "base_url": "http://localhost:1234"
    },
    "openrouter": {
        "api_key": "your_key"
    },
    "openai": {
        "api_key": "your_key"
    }
}
```

**`personas.json`** - Persona definitions
```json
{
    "personas": [
        {
            "name": "Philosopher",
            "system_prompt": "You are a thoughtful philosopher...",
            "model": "gpt-4",
            "provider": "openai",
            "temperature": 0.7,
            "max_tokens": 500
        }
    ]
}
```

### Environment Variables

API keys can also be set via `.env`:
```env
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-...
```

## Extending the Application

### Adding New Features

1. **New UI Components**
   - Extend `AutoChatApp` class in `auto_chat.py`
   - Add methods for new widgets
   - Connect to event handlers

2. **New Conversation Modes**
   - Modify conversation loop logic
   - Add new control options
   - Update message handling

3. **New Analytics**
   - Add functions to `utils/analytics.py`
   - Integrate into conversation end flow
   - Display in UI or export to file

4. **New Persona Features**
   - Extend `Persona` class
   - Update JSON schema
   - Modify persona generator

### Testing Considerations

- Test with multiple API providers
- Verify error handling for API failures
- Test conversation flow edge cases
- Validate configuration file loading
- Check UI responsiveness during API calls

## Dependencies

Core dependencies:
- `tkinter` / `ttkbootstrap` - GUI framework
- `requests` - HTTP API calls
- `python-dotenv` - Environment variable management
- `rich` - Terminal UI for persona generator

## Threading Model

The GUI application uses threading to prevent UI freezing during API calls:

- Main thread: UI rendering and event handling
- Worker thread: API calls and conversation logic
- Thread-safe updates via `after()` method

## Error Handling

- API client errors are caught and logged
- User-friendly error messages displayed
- Graceful degradation on configuration issues
- Network timeout handling

## Security Considerations

- API keys stored in `config.json` or `.env`
- Configuration files should be in `.gitignore`
- No hardcoded credentials in source code
- Use environment variables for sensitive data

---

For questions or suggestions about the architecture, please open an issue on GitHub.
