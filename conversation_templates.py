#!/usr/bin/env python3
"""
conversation_templates.py - Template management for Auto Chat

Provides functionality to create, load, and manage conversation templates
that define pre-configured conversation scenarios.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

log = logging.getLogger("conversation_templates")

TEMPLATES_DIR = "templates"


class ConversationTemplate:
    """Represents a conversation template with personas and settings."""

    def __init__(
        self,
        name: str,
        description: str,
        persona1_name: str,
        persona2_name: str,
        initial_topic: str,
        max_turns: int = 10,
        category: str = "custom"
    ):
        self.name = name
        self.description = description
        self.persona1_name = persona1_name
        self.persona2_name = persona2_name
        self.initial_topic = initial_topic
        self.max_turns = max_turns
        self.category = category
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "persona1_name": self.persona1_name,
            "persona2_name": self.persona2_name,
            "initial_topic": self.initial_topic,
            "max_turns": self.max_turns,
            "category": self.category,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTemplate':
        """Create template from dictionary."""
        template = cls(
            name=data["name"],
            description=data["description"],
            persona1_name=data["persona1_name"],
            persona2_name=data["persona2_name"],
            initial_topic=data["initial_topic"],
            max_turns=data.get("max_turns", 10),
            category=data.get("category", "custom")
        )
        template.created_at = data.get("created_at", datetime.now().isoformat())
        return template


def ensure_templates_dir():
    """Ensure the templates directory exists."""
    os.makedirs(TEMPLATES_DIR, exist_ok=True)


def save_template(template: ConversationTemplate) -> bool:
    """Save a template to a JSON file."""
    try:
        ensure_templates_dir()
        filename = os.path.join(TEMPLATES_DIR, f"{template.name.lower().replace(' ', '_')}.json")

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(template.to_dict(), f, indent=4)

        log.info(f"Template '{template.name}' saved to {filename}")
        return True
    except Exception as e:
        log.error(f"Error saving template '{template.name}': {e}")
        return False


def load_template(filename: str) -> Optional[ConversationTemplate]:
    """Load a template from a JSON file."""
    try:
        filepath = os.path.join(TEMPLATES_DIR, filename)
        if not filepath.endswith('.json'):
            filepath += '.json'

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        template = ConversationTemplate.from_dict(data)
        log.info(f"Template '{template.name}' loaded from {filepath}")
        return template
    except Exception as e:
        log.error(f"Error loading template from {filename}: {e}")
        return None


def list_templates() -> List[ConversationTemplate]:
    """List all available templates."""
    templates = []

    try:
        ensure_templates_dir()

        for filename in os.listdir(TEMPLATES_DIR):
            if filename.endswith('.json'):
                template = load_template(filename)
                if template:
                    templates.append(template)

        log.info(f"Found {len(templates)} templates")
    except Exception as e:
        log.error(f"Error listing templates: {e}")

    return templates


def delete_template(template_name: str) -> bool:
    """Delete a template file."""
    try:
        filename = os.path.join(TEMPLATES_DIR, f"{template_name.lower().replace(' ', '_')}.json")

        if os.path.exists(filename):
            os.remove(filename)
            log.info(f"Template '{template_name}' deleted")
            return True
        else:
            log.warning(f"Template file not found: {filename}")
            return False
    except Exception as e:
        log.error(f"Error deleting template '{template_name}': {e}")
        return False


def create_default_templates():
    """Create default conversation templates."""
    default_templates = [
        ConversationTemplate(
            name="Debate",
            description="Two personas with opposing views engage in a structured debate",
            persona1_name="Alice",
            persona2_name="Bob",
            initial_topic="Should artificial intelligence be regulated by governments?",
            max_turns=15,
            category="debate"
        ),
        ConversationTemplate(
            name="Interview",
            description="Interviewer and subject in a professional interview setting",
            persona1_name="Alice",
            persona2_name="Bob",
            initial_topic="Tell me about your experience with AI and machine learning",
            max_turns=12,
            category="interview"
        ),
        ConversationTemplate(
            name="Brainstorming",
            description="Creative ideation and collaborative problem-solving",
            persona1_name="Alice",
            persona2_name="Bob",
            initial_topic="Let's brainstorm innovative ways to use AI in education",
            max_turns=20,
            category="brainstorming"
        ),
        ConversationTemplate(
            name="Tutoring",
            description="Teacher and student in an educational setting",
            persona1_name="Alice",
            persona2_name="Bob",
            initial_topic="Let's learn about quantum computing basics",
            max_turns=15,
            category="tutoring"
        ),
        ConversationTemplate(
            name="Storytelling",
            description="Collaborative narrative creation",
            persona1_name="Alice",
            persona2_name="Bob",
            initial_topic="Let's create a science fiction story set in the year 2150",
            max_turns=25,
            category="storytelling"
        )
    ]

    for template in default_templates:
        save_template(template)

    log.info(f"Created {len(default_templates)} default templates")


def initialize_templates():
    """Initialize the templates directory with defaults if empty."""
    ensure_templates_dir()

    # Check if any templates exist
    existing_templates = list_templates()

    if not existing_templates:
        log.info("No templates found, creating defaults")
        create_default_templates()
    else:
        log.info(f"Found {len(existing_templates)} existing templates")
