from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.backend.schemas import AgentDefinition

BASE_DIR = Path(__file__).resolve().parents[2]
AGENTS_CONFIG_PATH = BASE_DIR / "src" / "backend" / "agents.json"


class Settings(BaseSettings):
    app_name: str = "V2V Gemma Backend"
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GEMMA_API_KEY"),
    )
    default_agent_name: str = "SVG-Generator"
    generation_timeout_seconds: float = 30.0
    verbose_model_logs: bool = True
    allow_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def load_agents() -> dict[str, AgentDefinition]:
    payload = json.loads(AGENTS_CONFIG_PATH.read_text(encoding="utf-8"))
    agents = [AgentDefinition.model_validate(item) for item in payload["agents"]]
    return {agent.name: agent for agent in agents}
