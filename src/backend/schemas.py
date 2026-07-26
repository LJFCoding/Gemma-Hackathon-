from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GenerateSvgRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2_000)
    agent_name: str = Field(default="SVG-Generator", min_length=1)


class SvgGenerationConfig(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1)
    max_output_tokens: int = Field(default=2048, ge=1)
    response_mime_type: Literal["text/plain", "application/json"] = "text/plain"
    thinking_level: Literal["off", "low", "medium", "high"] = "off"


class AgentDefinition(BaseModel):
    name: str
    model: str
    description: str
    goal: str
    canvas: dict[str, int | str]
    system_instruction: str
    config: SvgGenerationConfig


class GenerateSvgResponse(BaseModel):
    agent_name: str
    model: str
    svg: str


class HealthResponse(BaseModel):
    status: str
