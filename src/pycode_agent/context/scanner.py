from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}
_LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
}
MAX_TREE_ENTRIES = 300


@dataclass
class ProjectProfile:
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
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if len(profile.tree) < MAX_TREE_ENTRIES:
                profile.tree.append(rel)
            lang = _LANG_BY_EXT.get(path.suffix)
            if lang:
                profile.languages.add(lang)
            if path.name in marker_files:
                profile.markers.append(path.name)
    return profile
