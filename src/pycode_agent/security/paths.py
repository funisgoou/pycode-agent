from __future__ import annotations

import re
from pathlib import PurePosixPath

# Patterns are matched against the POSIX-normalised path. Earlier versions
# matched ``token``/``secret``/``credential`` as bare substrings, which
# false-flagged legitimate files like ``tokenizer.py`` or
# ``test_secret_manager.py``. The word-boundary variants below only match
# when the term stands alone as a path/word component (delimited by /, -,
# _, ., or string edges).
_SENSITIVE_PATTERNS = [
    r"(^|/)\.env(\.|$)",
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"\.pfx$",
    r"(^|/)id_rsa($|\.)",
    r"(^|[/_.-])tokens?([/_.-]|$)",
    r"(^|[/_.-])secrets?([/_.-]|$)",
    r"(^|[/_.-])credentials?([/_.-]|$)",
    r"\.aws/credentials$",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SENSITIVE_PATTERNS]


def is_sensitive(path: str) -> bool:
    """True if *path* names a file that likely holds secrets/credentials."""
    norm = str(PurePosixPath(path.replace("\\", "/")))
    return any(rx.search(norm) for rx in _COMPILED)
