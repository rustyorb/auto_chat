import json
from typing import Any, Dict


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments, but never inside string literals
    (a regex-based strip would eat the // in "http://host:port")."""
    out = []
    i = 0
    in_string = False
    while i < len(text):
        c = text[i]
        if in_string:
            out.append(c)
            if c == '\\' and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
        elif c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif text.startswith('//', i):
            j = text.find('\n', i)
            i = len(text) if j == -1 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            i = len(text) if j == -1 else j + 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def load_json_with_comments(path: str) -> Dict[str, Any]:
    """Load a JSON file that may contain // or /* */ comments."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    return json.loads(_strip_comments(text))
