from __future__ import annotations
import re
from pathlib import PurePosixPath

_SENSITIVE_PATTERNS = [
    r"(^|/)\.env(\.|$)",
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"\.pfx$",
    r"(^|/)id_rsa($|\.)",
    r"token",
    r"secret",
    r"credential",
    r"\.aws/credentials$",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SENSITIVE_PATTERNS]


def is_sensitive(path: str) -> bool:
    norm = str(PurePosixPath(path.replace("\\", "/")))
    return any(rx.search(norm) for rx in _COMPILED)
