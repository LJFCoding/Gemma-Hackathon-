"""V2V backend — view pages + Gemma-powered voice assistant.

Run:  uvicorn main:app --reload --port 8000
Then: http://localhost:8000/assistant

The assistant does speech-to-text and text-to-speech in the browser
(Web Speech API), so no audio models are needed server-side. This file
only supplies the "brain": a Gemma chat completion.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Load .env if python-dotenv is available (optional dependency).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="V2V Co-Pilot")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# The React dev server runs on a different origin (5173/3000), so it needs CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",   # Vite
        "http://localhost:3000", "http://127.0.0.1:3000",   # CRA / Next
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Gemma configuration
#
# Two supported providers, chosen with GEMMA_PROVIDER:
#   "ollama" (default) — local, free, offline.  ollama pull gemma3
#   "google"           — Google AI Studio.      needs GOOGLE_API_KEY
# ---------------------------------------------------------------------------
PROVIDER: str = os.getenv("GEMMA_PROVIDER", "ollama").lower()
MODEL: str = os.getenv("GEMMA_MODEL", "gemma3")
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")

SYSTEM_PROMPT = (
    "You are V2V Co-Pilot, a voice assistant. Your replies are spoken aloud, "
    "so keep them short and conversational — usually one to three sentences. "
    "Use plain words, no markdown, no bullet points, no emoji. "
    "If you don't know something, say so briefly."
)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str


async def _ask_ollama(req: ChatRequest) -> str:
    """Call a local Ollama server running Gemma."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [m.model_dump() for m in req.history]
    messages.append({"role": "user", "content": req.message})

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": MODEL, "messages": messages, "stream": False},
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Can't reach Ollama at {OLLAMA_URL}. Install it from "
                    f"https://ollama.com, then run:  ollama pull {MODEL}"
                ),
            )
        if r.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail=f"Model '{MODEL}' not found in Ollama. Run:  ollama pull {MODEL}",
            )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


async def _ask_google(req: ChatRequest, max_tokens: int = 1200) -> str:
    """Call Gemma through the Google AI Studio API.

    Gemma 4 reasons before answering and returns that reasoning as extra
    parts flagged ``thought: true``. Those must be filtered out — otherwise
    the assistant reads its own scratchpad aloud. Thinking also consumes the
    output budget, so ``maxOutputTokens`` is set well above the spoken reply
    length to avoid getting truncated mid-thought with no answer at all.
    """
    if not GOOGLE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_API_KEY is not set. Add it to V2V/.env to use the Google provider.",
        )

    contents = [
        {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
        for m in req.history
    ]
    contents.append({"role": "user", "parts": [{"text": req.message}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            url,
            headers={"x-goog-api-key": GOOGLE_API_KEY},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": max_tokens},
            },
        )
        if r.status_code in (401, 403):
            raise HTTPException(status_code=503, detail="Google API key rejected. Check GOOGLE_API_KEY.")
        if r.status_code == 404:
            raise HTTPException(status_code=503, detail=f"Model '{MODEL}' not available to this key.")
        r.raise_for_status()
        data = r.json()

    candidate = (data.get("candidates") or [{}])[0]
    parts = candidate.get("content", {}).get("parts") or []

    # Keep only the spoken answer; drop the model's internal reasoning.
    spoken = " ".join(
        p["text"].strip() for p in parts if not p.get("thought") and p.get("text")
    ).strip()

    if not spoken:
        # Ran out of budget while still thinking, or was filtered.
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise HTTPException(
                status_code=502,
                detail="Gemma ran out of output budget while reasoning. Try a shorter question.",
            )
        raise HTTPException(status_code=502, detail="Gemma returned no usable text.")

    return spoken


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Send one turn to Gemma and return the spoken reply."""
    if PROVIDER == "google":
        reply = await _ask_google(req)
    else:
        reply = await _ask_ollama(req)
    return ChatResponse(reply=reply, provider=PROVIDER, model=MODEL)


@app.get("/api/health")
async def health() -> dict:
    """Report whether the configured Gemma provider is actually reachable."""
    status = {"provider": PROVIDER, "model": MODEL, "ready": False, "detail": ""}

    if PROVIDER == "google":
        if not GOOGLE_API_KEY:
            status["detail"] = "GOOGLE_API_KEY not set"
            return status
        # Confirm the key works *and* the model is actually visible to it.
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": GOOGLE_API_KEY},
                )
                if r.status_code in (401, 403):
                    status["detail"] = "API key rejected"
                    return status
                r.raise_for_status()
                names = {m["name"].removeprefix("models/") for m in r.json().get("models", [])}
                if MODEL in names:
                    status.update(ready=True, detail="ok")
                else:
                    status["detail"] = f"'{MODEL}' not available to this key"
            except httpx.HTTPError as exc:
                status["detail"] = f"Could not reach Google AI: {type(exc).__name__}"
        return status

    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            if any(m.split(":")[0] == MODEL.split(":")[0] for m in models):
                status.update(ready=True, detail="ok")
            else:
                status["detail"] = f"Ollama is running but '{MODEL}' is not pulled. Run: ollama pull {MODEL}"
        except httpx.ConnectError:
            status["detail"] = f"Ollama not reachable at {OLLAMA_URL}"
    return status


# ---------------------------------------------------------------------------
# Verbal assessment — grading spoken answers with Gemma
# ---------------------------------------------------------------------------
GRADER_PROMPT = """You are the assessment engine for V2V Co-Pilot, a live tutoring tool.

Grade the learner's spoken answer to the current topic. Their answer arrives as a
speech-to-text transcript, so ignore small transcription errors, filler words and
missing punctuation — grade the understanding, not the wording.

Reply with ONLY a JSON object, no code fence and no commentary:
{
  "score": <integer 0-10>,
  "feedback": "<one or two short sentences, spoken aloud to the learner>",
  "weak_spot": "<two or three words naming the concept they got wrong, or null if correct>",
  "difficulty": "<Beginner|Intermediate|Advanced>",
  "mastery_delta": <integer -5 to 10>
}"""


def _extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model reply, tolerating fences or stray prose."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError("no JSON object in model reply")


def _salvage_fields(text: str) -> dict[str, Any]:
    """Recover grading fields from a truncated/malformed reply.

    Gemma occasionally runs out of output budget mid-JSON. Without this, the
    raw broken JSON would end up in ``feedback`` and be read aloud verbatim.
    """
    out: dict[str, Any] = {}

    if m := re.search(r'"feedback"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        out["feedback"] = m.group(1).replace('\\"', '"').strip()
    if m := re.search(r'"score"\s*:\s*(\d+)', text):
        out["score"] = int(m.group(1))
    if m := re.search(r'"weak_spot"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        out["weak_spot"] = m.group(1).strip()
    if m := re.search(r'"difficulty"\s*:\s*"(Beginner|Intermediate|Advanced)"', text):
        out["difficulty"] = m.group(1)
    if m := re.search(r'"mastery_delta"\s*:\s*(-?\d+)', text):
        out["mastery_delta"] = int(m.group(1))
    return out


async def grade_answer(topic: str, transcript: str) -> dict[str, Any]:
    """Ask Gemma to grade one spoken answer. Falls back to a neutral result."""
    question = (
        f"{GRADER_PROMPT}\n\n"
        f"Current topic: {topic}\n"
        f"Learner's spoken answer: \"{transcript}\""
    )
    req = ChatRequest(message=question, history=[])
    # Grading needs more headroom than chat: Gemma reasons first, *then* emits
    # JSON, and a wrong answer produces noticeably longer reasoning.
    raw = await (
        _ask_google(req, max_tokens=3000) if PROVIDER == "google" else _ask_ollama(req)
    )

    try:
        data = _extract_json(raw)
    except ValueError:
        # Truncated or malformed — salvage what we can rather than speaking raw JSON.
        data = _salvage_fields(raw)
        if not data.get("feedback"):
            data["feedback"] = "Answer received, but grading was unclear. Try rephrasing."

    return {
        "score": max(0, min(10, int(data.get("score", 5)))),
        "feedback": str(data.get("feedback", "")).strip() or "Answer recorded.",
        "weak_spot": data.get("weak_spot") or None,
        "difficulty": data.get("difficulty") if data.get("difficulty") in
                      ("Beginner", "Intermediate", "Advanced") else "Intermediate",
        "mastery_delta": max(-5, min(10, int(data.get("mastery_delta", 0)))),
    }


class ConnectionManager:
    """Tracks live sockets so the backend can push blocks/patches to every client."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict) -> None:
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except (WebSocketDisconnect, RuntimeError):
                self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    """Live channel for the React timeline.

    Client → server:
      {"type": "TEXT_ANSWER", "topic": ..., "transcript": ..., "student_id": ...}
      {"type": "ASK",         "message": ...}
      {"type": "AUDIO_ANSWER", ...}   (rejected — Gemma has no audio input)

    Server → client:
      GRADE_RESULT | PROFILE_UPDATE | ASSISTANT_REPLY | NEW_BLOCK | DOM_PATCH | ERROR
    """
    await manager.connect(ws)
    await ws.send_json({"type": "READY", "provider": PROVIDER, "model": MODEL})

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")

            if kind == "TEXT_ANSWER":
                transcript = (msg.get("transcript") or "").strip()
                if not transcript:
                    await ws.send_json({"type": "ERROR", "detail": "Empty transcript."})
                    continue

                topic = msg.get("topic") or "the current topic"
                try:
                    result = await grade_answer(topic, transcript)
                except HTTPException as exc:
                    await ws.send_json({"type": "ERROR", "detail": exc.detail})
                    continue

                await ws.send_json({
                    "type": "GRADE_RESULT",
                    "transcript": transcript,
                    "score": f"{result['score']}/10",
                    "text": result["feedback"],
                    "weak_spot": result["weak_spot"],
                    "difficulty": result["difficulty"],
                    "mastery_delta": result["mastery_delta"],
                    "timestamp": datetime.now().strftime("%H:%M"),
                })

            elif kind == "ASK":
                try:
                    reply = await chat(ChatRequest(message=msg.get("message", ""), history=[]))
                    await ws.send_json({"type": "ASSISTANT_REPLY", "reply": reply.reply})
                except HTTPException as exc:
                    await ws.send_json({"type": "ERROR", "detail": exc.detail})

            elif kind == "AUDIO_ANSWER":
                await ws.send_json({
                    "type": "ERROR",
                    "detail": (
                        f"'{MODEL}' has no audio input. Send speech-to-text output as "
                        "TEXT_ANSWER instead — the browser handles transcription."
                    ),
                })

            else:
                await ws.send_json({"type": "ERROR", "detail": f"Unknown message type: {kind!r}"})

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
        raise


@app.get("/assistant", response_class=HTMLResponse)
async def assistant_page() -> str:
    return (STATIC_DIR / "assistant.html").read_text(encoding="utf-8")


@app.get("/view/{room_id}", response_class=HTMLResponse)
async def view_page(room_id: str) -> str:
    return (STATIC_DIR / "view.html").read_text(encoding="utf-8")


@app.get("/")
async def root() -> dict:
    return {"status": "V2V backend running", "assistant": "/assistant", "health": "/api/health"}
