# Auto Chat

A Tkinter-based application for AI-to-AI conversations that enables turn-based conversations between two AI personas using different Large Language Models (LLMs).

## Features

- Dual AI conversation with different models
- Multiple LLM API support (Ollama, LM Studio, OpenRouter, OpenAI)
- Comprehensive persona management with creation and editing
- Tkinter GUI with ttkbootstrap styling
- Conversation logging and export
- System intervention and narrator mode
- Conversation topic management
- Configuration persistence

## Requirements

- Python 3.8+
- Tkinter and ttk (included with Python)
- ttkbootstrap
- requests
- python-dotenv
- rich (for persona generator)

## Installation

1. Clone this repository or download the source code
2. Create and activate a virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. Install the required dependencies:

```bash
pip install -r requirements.txt
```

4. Set up your personas file:

```bash
# Copy the example personas file
cp personas.json.example personas.json
# Or manually rename the file personas.json.example to personas.json
```

5. Set up your configuration file:

```bash
# Copy the example config file
cp config.json.example config.json
# Or manually rename the file config.json.example to config.json
```

The example files provide a starting point. You can edit these files directly or use the application's interfaces to update them.

## Usage

### Main Application

1. Ensure your virtual environment is activated
2. Run the main application:

```bash
python auto_chat.py
```

3. In the setup screen:
   - Select two personas for the conversation
   - Choose API providers and models for each persona
   - Set the maximum number of conversation turns
   - Enter a conversation topic

4. After starting the conversation, you can:
   - Pause/resume the conversation
   - Add narrator messages
   - Stop the conversation
   - Save the conversation log

### Persona Generator

A separate tool is available to create new personas:

```bash
python persona_generator.py
```

This tool allows you to:
- Connect to various LLM providers
- Define personality traits, age, and gender
- Generate creative personas for use in auto_chat.py

## API Support

The application supports multiple LLM providers:

- **Ollama**: Local models via Ollama API (default: http://127.0.0.1:11434)
- **LM Studio**: Local models via LM Studio API (default: http://127.0.0.1:1234/v1)
- **OpenRouter**: Cloud models via OpenRouter API (requires API key)
- **OpenAI**: Cloud models via OpenAI API (requires API key)

## Configuration

The `config.json` file stores application settings and API keys. It has the following structure:

```json
{
    "last_model_ollama": "llama3:latest",
    "last_model_lmstudio": "your-local-model",
    "last_model_openrouter": "anthropic/claude-3-opus",
    "last_model_openai": "gpt-4",
    "openai_api_key": "your-openai-api-key",
    "openrouter_api_key": "your-openrouter-api-key"
}
```

You can edit this file manually or enter API keys through the application's interface.

## Persona Structure

Each persona in the personas.json file follows this structure:

```json
{
    "name": "Persona Name",
    "personality": "Detailed description of the persona's personality traits and characteristics",
    "age": 30,
    "gender": "male|female|non-binary|etc"
}
```

You can edit this file manually or use the persona generator tool to create and manage your personas.

## File Structure

- `auto_chat.py`: Main application
- `persona_generator.py`: Tool for generating and managing personas
- `personas.json`: Stores persona data
- `personas.json.example`: Example persona templates
- `config.json`: Stores application configuration
- `config.json.example`: Example configuration template
- `chatroom_log.txt`: Records conversation history


