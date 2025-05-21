import json
import re
from typing import Any, Dict


def load_jsonc(path: str) -> Dict[str, Any]:
    """Load JSON file allowing C-style comments."""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Remove // comments
    content = re.sub(r"//.*", "", content)
    # Remove /* */ comments
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return json.loads(content)
