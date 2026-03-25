#!/usr/bin/env python3
"""
persona_generator.py - A tool to generate AI personas and add them to personas.json

This script generates creative and diverse AI personas using the same LLM models
available in rich_chat.py (Ollama and LM Studio). Generated personas are
automatically added to the personas.json file used by rich_chat.py.

Usage:
    python persona_generator.py

Features:
- Uses the same LLM providers as rich_chat.py
- Customizable persona attributes
- Safety filters to ensure appropriate content
- Automated addition to personas.json
"""

import os
import sys
import json
import time
import logging
from typing import Dict, List, Any, Optional

from api_clients import (
    APIClient,
    OllamaClient,
    LMStudioClient,
    OpenRouterClient,
    OpenAIClient,
)
from persona import Persona
from utils.config_utils import load_json_with_comments

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm, IntPrompt
from rich import box
from rich.align import Align
from rich.table import Table

from config import (
    PERSONAS_FILE,
    CONFIG_FILE,
    AGE_RANGES,
    CHARACTER_TYPES,
    GENDERS
)

# Configure console output
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
)
log = logging.getLogger("persona_generator")

class PersonaGenerator:
    """Generates AI personas using LLM providers."""

    def __init__(self):
        self.api_clients = {}
        self.selected_client = None
        self.selected_model = None

        # Initialize API clients
        self.api_clients["ollama"] = OllamaClient()
        self.api_clients["lmstudio"] = LMStudioClient()
        self.api_clients["openrouter"] = OpenRouterClient()
        self.api_clients["openai"] = OpenAIClient()

        # Character types for generating diverse personas
        self.character_types = [
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

        # Age ranges for diverse personas
        self.age_ranges = {
            "Young Adult": (4, 14),
            "Adult": (15, 25),
            "Middle-Aged": (30, 45),
            "Senior": (46, 85),
            "AI Entity": (9, 99)
        }

        # Gender options
        self.genders = ["male", "female", "non-binary", "AI Entity"]

        # Load existing personas
        self.existing_personas = self.load_personas()

    def load_personas(self) -> List[Dict[str, Any]]:
        """Load existing personas from file."""
        try:
            if os.path.exists(PERSONAS_FILE):
                data = load_json_with_comments(PERSONAS_FILE)
                if isinstance(data, list):
                    return data
                return data.get('personas', [])
            else:
                return []
        except Exception as e:
            log.error(f"Failed to load personas: {str(e)}")
            console.print(Panel(
                f"[bold red]Error loading personas: {str(e)}[/bold red]",
                title="Error"
            ))
            return []

    def select_model(self) -> bool:
        """Let user select the API client and model for persona generation."""
        console.print("\n[bold]Select API provider for persona generation:[/bold]")
        console.print("[1] Ollama")
        console.print("[2] LM Studio")
        console.print("[3] OpenRouter")
        console.print("[4] OpenAI")

        while True:
            try:
                choice = Prompt.ask(
                    "Select provider (1-4)",
                    console=console
                )
                if choice == "1":
                    client = self.api_clients["ollama"]
                    break
                elif choice == "2":
                    client = self.api_clients["lmstudio"]
                    break
                elif choice == "3":
                    client = self.api_clients["openrouter"]
                    break
                elif choice == "4":
                    client = self.api_clients["openai"]
                    break
                else:
                    console.print("[yellow]Invalid selection[/yellow]")
            except ValueError:
                console.print("[yellow]Please enter a number[/yellow]")

        self.selected_client = client

        # Handle API key input for OpenRouter and OpenAI
        if client.name in ["OpenRouter", "OpenAI"]:
            console.print(f"\n[bold]{client.name} requires an API key.[/bold]")

            # Check if we have an API key saved in config.json
            config_key = f"{client.name.lower()}_api_key"
            api_key = ""
            
            if os.path.exists(CONFIG_FILE):
                try:
                    config = load_json_with_comments(CONFIG_FILE)
                    api_key = config.get(config_key, "")
                except Exception as e:
                    log.error(f"Error loading config file: {e}")
            
            if api_key:
                console.print(f"Found saved API key for {client.name}.")
                use_saved = Confirm.ask("Use saved API key?", default=True)
                if not use_saved:
                    api_key = Prompt.ask(f"Enter {client.name} API key", password=True)
            else:
                api_key = Prompt.ask(f"Enter {client.name} API key", password=True)
            
            client.api_key = api_key
            client.update_headers()
            
            # Save API key to config.json
            if Confirm.ask("Save API key for future use?", default=True):
                try:
                    config = {}
                    if os.path.exists(CONFIG_FILE):
                        config = load_json_with_comments(CONFIG_FILE)
                    
                    config[config_key] = api_key
                    
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=4)
                    
                    console.print(f"[green]API key saved to {CONFIG_FILE}[/green]")
                except Exception as e:
                    console.print(f"[red]Error saving API key: {e}[/red]")

        # Get available models with retry option
        while True:
            models = client.get_available_models()

            if not models:
                console.print(f"[bold yellow]No models available from {client.name}.[/bold yellow]")
                if client.name in ["OpenRouter", "OpenAI"]:
                    console.print(f"Make sure your API key for {client.name} is valid.")
                else:
                    console.print(f"Make sure the {client.name} server is running at {client.base_url}.")

                retry = Confirm.ask("Retry connection?", default=True)
                if retry:
                    console.print(f"Retrying connection to {client.name}...")
                    continue
                else:
                    # Allow choosing a different provider
                    return self.select_model()

            # If we got to here, we have models
            break

        console.print(f"\n[bold]Select model for persona generation:[/bold]")
        for i, model in enumerate(models):
            console.print(f"[{i+1}] {model}")

        while True:
            try:
                choice = Prompt.ask(
                    f"Select model (1-{len(models)})",
                    console=console
                )
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    client.set_model(models[idx])
                    self.selected_model = models[idx]
                    break
                else:
                    console.print("[yellow]Invalid selection[/yellow]")
            except ValueError:
                console.print("[yellow]Please enter a number[/yellow]")

        return True

    def select_character_type(self) -> str:
        """Let user select a character type for the persona."""
        console.print("\n[bold]Select a character type for the persona:[/bold]")
        for i, char_type in enumerate(self.character_types):
            console.print(f"[{i+1}] {char_type}")

        # Add custom option
        console.print(f"[{len(self.character_types)+1}] Custom (specify your own)")

        while True:
            try:
                choice = Prompt.ask(
                    f"Select character type (1-{len(self.character_types)+1})",
                    console=console
                )
                idx = int(choice) - 1
                if 0 <= idx < len(self.character_types):
                    return self.character_types[idx]
                elif idx == len(self.character_types):
                    # Custom character type
                    custom_type = Prompt.ask(
                        "Enter custom character type",
                        console=console
                    )
                    return custom_type
                else:
                    console.print("[yellow]Invalid selection[/yellow]")
            except ValueError:
                console.print("[yellow]Please enter a number[/yellow]")

    def select_age_range(self) -> int:
        """Let user select an age range for the persona."""
        console.print("\n[bold]Select an age range for the persona:[/bold]")
        for i, (range_name, (min_age, max_age)) in enumerate(self.age_ranges.items()):
            console.print(f"[{i+1}] {range_name} ({min_age}-{max_age})")

        # Add custom option
        console.print(f"[{len(self.age_ranges)+1}] Custom (specify exact age)")

        while True:
            try:
                choice = Prompt.ask(
                    f"Select age range (1-{len(self.age_ranges)+1})",
                    console=console
                )
                idx = int(choice) - 1
                if 0 <= idx < len(self.age_ranges):
                    # Get a random age within the selected range
                    range_name = list(self.age_ranges.keys())[idx]
                    min_age, max_age = self.age_ranges[range_name]

                    # Let user specify exact age within range
                    while True:
                        age = IntPrompt.ask(
                            f"Enter specific age ({min_age}-{max_age})",
                            console=console
                        )
                        if min_age <= age <= max_age:
                            return age
                        else:
                            console.print(f"[yellow]Please enter an age between {min_age} and {max_age}[/yellow]")

                elif idx == len(self.age_ranges):
                    # Custom age
                    while True:
                        age = IntPrompt.ask(
                            "Enter custom age (4-100)",
                            console=console
                        )
                        if 4 <= age <= 100:
                            return age
                        else:
                            console.print("[yellow]Please enter an age between 4 and 100[/yellow]")
                else:
                    console.print("[yellow]Invalid selection[/yellow]")
            except ValueError:
                console.print("[yellow]Please enter a number[/yellow]")

    def select_gender(self) -> str:
        """Let user select a gender for the persona."""
        console.print("\n[bold]Select a gender for the persona:[/bold]")
        for i, gender in enumerate(self.genders):
            console.print(f"[{i+1}] {gender}")

        # Add custom option
        console.print(f"[{len(self.genders)+1}] Custom (specify your own)")

        while True:
            try:
                choice = Prompt.ask(
                    f"Select gender (1-{len(self.genders)+1})",
                    console=console
                )
                idx = int(choice) - 1
                if 0 <= idx < len(self.genders):
                    return self.genders[idx]
                elif idx == len(self.genders):
                    # Custom gender
                    custom_gender = Prompt.ask(
                        "Enter custom gender",
                        console=console
                    )
                    return custom_gender
                else:
                    console.print("[yellow]Invalid selection[/yellow]")
            except ValueError:
                console.print("[yellow]Please enter a number[/yellow]")

    def generate_name(self, character_type: str, age: int, gender: str, regenerations=0) -> str:
        """Generate a name for the persona."""
        prompt = f"""Generate ONE appropriate first name for a fictional {gender}, {age}-year-old {character_type} character. 

IMPORTANT INSTRUCTIONS:
- Return ONLY a single name with no additional text
- If the character is an AI Entity, generate a name that would be appropriate for an AI system, not a human name
- NO explanations, quotes, or additional text - just the name itself
"""

        system_message = "You are a helpful assistant that generates realistic character names. Return ONLY the name with NO additional text."

        console.print("[bold]Generating name...[/bold]")
        response = self.selected_client.generate_response(prompt, system_message)

        # Clean up response to just get the name
        name = response.strip()
        # Remove any quotation marks or extra text
        name = name.replace('"', '').replace("'", "")
        # Split by newlines and take first line if multiple lines
        name = name.split('\n')[0].strip()

        # If we get a title or extra text, try to clean it up
        name_parts = name.split()
        skip_words = ["name", "is", "would", "be", "character", "persona"]
        if any(word.lower() in skip_words for word in name_parts[:2]) and len(name_parts) > 2:
            name = ' '.join(name_parts[2:])

        # Handle common title prefixes
        prefixes = ["dr.", "dr", "mr.", "mr", "ms.", "ms", "mrs.", "mrs", "miss", "professor", "prof."]
        for prefix in prefixes:
            if name.lower().startswith(prefix + " "):
                name = name[len(prefix) + 1:]

        # Final cleanup for any remaining artifacts
        name = name.strip(".,;:- ")

        # Let user confirm or modify the name
        console.print(f"Generated name: [bold]{name}[/bold]")
        if not Confirm.ask("Use this name?", default=True):
            action = Prompt.ask("Would you like to (1) enter a custom name or (2) regenerate?", console=console)
            if action == "1":
                name = Prompt.ask("Enter custom name", console=console)
            elif action == "2":
                if regenerations < 5:  # Regeneration limit
                    name = self.generate_name(character_type, age, gender, regenerations + 1)
                else:
                    console.print("[yellow]Regeneration limit reached. Please enter a custom name.[/yellow]")
                    name = Prompt.ask("Enter custom name", console=console)
            else:
                console.print("[yellow]Invalid selection[/yellow]")
                name = Prompt.ask("Enter custom name", console=console)

        return name

    def generate_personality(self, name: str, character_type: str, age: int, gender: str, regenerations=0) -> str:
        """Generate a personality description for the persona."""

        # Ask user if they want to add custom details to influence the personality generation
        console.print("\n[bold cyan]Would you like to add custom details to influence the personality generation?[/bold cyan]")
        console.print("This could include specific traits, interests, background elements, or any other details.")

        custom_details = ""
        if Confirm.ask("Add custom details?", default=True):
            console.print("Enter custom details (press Enter when done):")
            lines = []
            while True:
                line = input()
                if not line and lines:  # Empty line and we have content
                    break
                lines.append(line)
            custom_details = '\n'.join(lines)
            console.print(f"[green]Custom details added:[/green] {custom_details}")

        # Build the prompt with custom details if provided
        prompt = f"""Create a rich, detailed personality description for a fictional character with these attributes:
- Name: {name}
- Age: {age}
- Gender: {gender}
- Character type: {character_type}
"""

        # Add custom details to the prompt if provided
        if custom_details:
            prompt += f"\n- Additional details that MUST be incorporated: {custom_details}"

        prompt += """\n
SPECIFIC REQUIREMENTS:
1. Write 6-8 sentences that vividly describe their personality traits, communication style, and thought processes.
2. Include both strengths and weaknesses/quirks that make the character unique and compelling.
3. Create a detailed, three-dimensional personality profile that feels like a real person.
4. Focus on cognitive, emotional, and social characteristics.
5. Make the description distinctive and avoid generic traits.
6. Do NOT include any inappropriate or explicit content.
7. Return ONLY the personality description, without repeating their name, age, gender, etc.

IMPORTANT: For AI Entity characters:
1. Do not include any details about a human physical body.
2. Write the personality in the format of a system persona, focusing on functions, communication style, and specialized capabilities.
"""

        system_message = """You are a character development expert who specializes in creating detailed, realistic character personalities.
Generate distinctive personality descriptions for fictional characters focusing on cognitive, emotional, and behavioral traits.
Write detailed, vivid descriptions that make each character feel unique and three-dimensional.
Your descriptions should be appropriate for all audiences while still being interesting and compelling."""

        console.print("[bold]Generating personality...[/bold]")
        response = self.selected_client.generate_response(prompt, system_message)

        # Clean up response to just get the personality description
        personality = response.strip()

        # Show the generated personality and allow editing
        console.print(f"\nGenerated personality description:")
        console.print(Panel(personality, title=f"{name}'s Personality", border_style="green"))

        if not Confirm.ask("Use this personality description?", default=True):
            action = Prompt.ask("Would you like to (1) enter a custom personality or (2) regenerate?", console=console)
            if action == "1":
                console.print("Enter custom personality description (press Enter when done):")
                lines = []
                while True:
                    line = input()
                    if not line and lines:  # Empty line and we have content
                        break
                    lines.append(line)
                personality = '\n'.join(lines)
            elif action == "2":
                if regenerations < 5:  # Regeneration limit
                    personality = self.generate_personality(name, character_type, age, gender, regenerations + 1)
                else:
                    console.print("[yellow]Regeneration limit reached. Please enter a custom personality.[/yellow]")
                    console.print("Enter custom personality description (press Enter when done):")
                    lines = []
                    while True:
                        line = input()
                        if not line and lines:  # Empty line and we have content
                            break
                        lines.append(line)
                    personality = '\n'.join(lines)
            else:
                console.print("[yellow]Invalid selection[/yellow]")
                console.print("Enter custom personality description (press Enter when done):")
                lines = []
                while True:
                    line = input()
                    if not line and lines:  # Empty line and we have content
                        break
                    lines.append(line)
                personality = '\n'.join(lines)

        return personality

    def save_persona(self, persona: Dict[str, Any]) -> bool:
        """Save the generated persona to the personas.json file."""
        try:
            # Create data structure if file doesn't exist
            if not os.path.exists(PERSONAS_FILE) or os.path.getsize(PERSONAS_FILE) == 0:
                data = {"personas": []}
            else:
                data = load_json_with_comments(PERSONAS_FILE)
                if "personas" not in data:
                    data["personas"] = []

            # Add the new persona
            data["personas"].append(persona)

            # Save back to file with pretty formatting
            with open(PERSONAS_FILE, 'w') as f:
                json.dump(data, f, indent=4)

            return True
        except Exception as e:
            log.error(f"Failed to save persona: {str(e)}")
            console.print(Panel(
                f"[bold red]Error saving persona: {str(e)}[/bold red]",
                title="Error"
            ))
            return False

    def generate_persona(self) -> Dict[str, Any]:
        """Generate a complete persona based on user inputs and LLM responses."""
        # Get character type preference
        character_type = self.select_character_type()

        # Get age preference
        age = self.select_age_range()

        # Get gender preference
        gender = self.select_gender()

        # Generate name
        name = self.generate_name(character_type, age, gender)

        # Generate personality (now with custom details support)
        personality = self.generate_personality(name, character_type, age, gender)

        # Create persona object
        persona = {
            "name": name,
            "personality": personality,
            "age": age,
            "gender": gender,
            "character_type": character_type  # Store the character type for reference
        }

        return persona

    def display_persona(self, persona: Dict[str, Any]) -> None:
        """Display a formatted view of the persona."""
        console.print("\n[bold green]Generated Persona:[/bold green]")

        # Create a styled table for display
        table = Table(title=f"Character Profile: {persona['name']}", box=box.ROUNDED)
        table.add_column("Attribute", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Name", persona['name'])
        table.add_row("Age", str(persona['age']))
        table.add_row("Gender", persona['gender'])
        table.add_row("Character Type", persona.get('character_type', 'Not specified'))
        table.add_row("Personality", persona['personality'])

        console.print(table)

    def run(self) -> None:
        """Main method to run the persona generator."""
        console.print(Panel.fit(
            "Persona Generator - Create AI personas for Rich Chat",
            title="Welcome",
            border_style="blue"
        ))

        # Select model for generation
        if not self.select_model():
            console.print("[bold red]Failed to select model. Exiting...[/bold red]")
            return

        while True:
            # Generate a new persona
            console.print("\n[bold blue]Generating new persona...[/bold blue]")
            persona = self.generate_persona()

            # Display the generated persona
            self.display_persona(persona)

            # Confirm and save
            if Confirm.ask("Add this persona to personas.json?", default=True):
                if self.save_persona(persona):
                    console.print("[bold green]Persona successfully added to personas.json![/bold green]")
                else:
                    console.print("[bold red]Failed to save persona.[/bold red]")

            # Ask to generate another
            if not Confirm.ask("Generate another persona?", default=True):
                break

        console.print("[bold blue]Thank you for using the Persona Generator![/bold blue]")


if __name__ == "__main__":

    generator = PersonaGenerator()
    generator.run()
