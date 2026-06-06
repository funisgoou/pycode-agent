from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}
_LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".php": "php", ".swift": "swift", ".kt": "kotlin",
    ".kts": "kotlin", ".scala": "scala", ".r": "r", ".R": "r",
    ".dart": "dart", ".lua": "lua", ".sh": "shell", ".bash": "shell",
    ".zsh": "shell", ".ps1": "powershell", ".html": "html", ".css": "css",
    ".sql": "sql", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".json": "json", ".xml": "xml",
}
MAX_TREE_ENTRIES = 300


@dataclass
class ProjectProfile:
    """Lightweight scan of a project: file tree, detected languages, markers."""

    root: Path
    tree: list[str] = field(default_factory=list)
    languages: set[str] = field(default_factory=set)
    markers: list[str] = field(default_factory=list)

    def summary(self) -> str:
        langs = ", ".join(sorted(self.languages)) or "unknown"
        markers = ", ".join(self.markers) or "none"
        head = "\n".join(self.tree[:60])
        return (f"Languages: {langs}\nMarkers: {markers}\n"
                f"Files ({len(self.tree)} shown, capped):\n{head}")


def scan_project(root: Path) -> ProjectProfile:
    root = Path(root)
    profile = ProjectProfile(root=root)
    marker_files = {"pyproject.toml", "package.json", "go.mod", "Cargo.toml", "pom.xml"}

    # Use os.walk so we can skip ignored directories entirely (prune),
    # instead of rglob which traverses everything then filters.
    all_entries: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories IN-PLACE so os.walk won't descend into them.
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        # Sort dirnames so os.walk visits subdirectories in sorted order.
        dirnames.sort()

        rel_dir = os.path.relpath(dirpath, root)
        for fname in sorted(filenames):
            rel = (fname if rel_dir == "." else f"{rel_dir}/{fname}")
            if len(profile.tree) < MAX_TREE_ENTRIES:
                profile.tree.append(rel)
            all_entries.append(rel)

    # Second pass: detect languages and markers from the collected entries.
    for rel in all_entries:
        suffix = os.path.splitext(rel)[1]
        lang = _LANG_BY_EXT.get(suffix)
        if lang:
            profile.languages.add(lang)
        basename = os.path.basename(rel)
        if basename in marker_files:
            profile.markers.append(basename)

    return profile
