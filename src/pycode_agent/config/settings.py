from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ModelSettings(BaseModel):
    provider: str = "openai_compatible"
    name: str = "default-coding-model"
    base_url: str = "https://api.example.com/v1"
    api_key: str | None = None
    timeout: int = 120
    stream: bool = True


class SecuritySettings(BaseModel):
    mode: Literal["readonly", "confirm", "workspace", "dangerous"] = "confirm"
    allow_shell: bool = True
    allow_git_push: bool = False


class ContextSettings(BaseModel):
    max_files: int = 200
    max_tokens: int = 120000
    enable_project_memory: bool = True


class AgentSettings(BaseModel):
    max_turns: int = 12
    max_tool_calls: int = 40


class Settings(BaseModel):
    model: ModelSettings = Field(default_factory=ModelSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
