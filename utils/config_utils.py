import json
import re
from typing import Any, Dict


def load_json_with_comments(path: str) -> Dict[str, Any]:
    """Load a JSON file that may contain // or /* */ comments."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    # Remove // comments
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    # Remove /* */ comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return json.loads(text)
