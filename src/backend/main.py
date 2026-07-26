from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from google.genai import errors

from src.backend.config import get_settings, load_agents
from src.backend.schemas import GenerateSvgRequest, GenerateSvgResponse, HealthResponse
from src.backend.services.gemma import (
    AgentNotFoundError,
    GenerationTimeoutError,
    generate_svg,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("v2v.api")

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.state.latest_frame = {
    "prompt": None,
    "agent_name": None,
    "model": None,
    "svg": None,
    "updated_at": None,
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/agents")
async def list_agents() -> dict[str, list[dict[str, str]]]:
    return {
        "agents": [
            {
                "name": agent.name,
                "model": agent.model,
                "description": agent.description,
                "goal": agent.goal,
            }
            for agent in load_agents().values()
        ]
    }


@app.get("/latest-frame")
async def latest_frame() -> dict[str, str | None]:
    return app.state.latest_frame


@app.get("/viewer", response_class=HTMLResponse)
async def viewer() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>V2V SVG Viewer</title>
    <style>
        :root {
            color-scheme: light;
            --bg: #f7f7f3;
            --card: #ffffff;
            --text: #1f2937;
            --muted: #6b7280;
            --accent: #0f766e;
            --border: #d1d5db;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--text);
            background: radial-gradient(circle at top left, #ecfeff 0%, var(--bg) 50%);
            display: grid;
            place-items: center;
            padding: 24px;
        }
        .panel {
            width: min(900px, 100%);
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
            padding: 18px;
        }
        h1 {
            font-size: 1.15rem;
            margin: 0 0 8px;
        }
        .meta {
            color: var(--muted);
            font-size: 0.92rem;
            margin-bottom: 14px;
            white-space: normal;
            overflow-wrap: anywhere;
            line-height: 1.3;
        }
        .frame {
            width: 100%;
            min-height: 320px;
            border: 1px dashed var(--border);
            border-radius: 10px;
            background: #fff;
            display: grid;
            place-items: center;
            overflow: hidden;
            padding: 12px;
        }
        .frame svg {
            display: block;
            width: 100%;
            max-width: 500px;
            height: auto;
            max-height: 300px;
            overflow: hidden;
        }
        .status {
            color: var(--muted);
            text-align: center;
        }
        .controls {
            margin-top: 12px;
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        button {
            border: none;
            border-radius: 8px;
            background: var(--accent);
            color: white;
            padding: 8px 12px;
            font-weight: 600;
            cursor: pointer;
        }
        input, textarea {
            width: 100%;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 10px;
            font: inherit;
        }
        label {
            font-size: 0.9rem;
            color: var(--muted);
            display: block;
            margin-bottom: 6px;
        }
        .form {
            margin-top: 14px;
            display: grid;
            gap: 10px;
        }
        .actions {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        .msg {
            font-size: 0.85rem;
            color: var(--muted);
        }
        .small {
            color: var(--muted);
            font-size: 0.85rem;
        }
        code {
            background: #f1f5f9;
            border-radius: 6px;
            padding: 1px 5px;
        }
    </style>
</head>
<body>
    <main class=\"panel\">
        <h1>Voice to Visual - Current SVG Frame</h1>
        <div class=\"meta\" id=\"meta\">Loading current frame...</div>
        <section class=\"frame\" id=\"frame\"></section>
        <div class=\"controls\">
            <button id=\"reload\" type=\"button\">Reload Current Frame</button>
            <span class=\"small\">Tip: Generate with <code>POST /generate-svg</code>, then refresh this page or click reload.</span>
        </div>
        <form class=\"form\" id=\"generate-form\">
            <div>
                <label for=\"prompt\">Prompt</label>
                <textarea id=\"prompt\" rows=\"3\" placeholder=\"Draw a pouch with one red token and two blue tokens.\" required></textarea>
            </div>
            <div>
                <label for=\"agent_name\">Agent Name</label>
                <input id=\"agent_name\" value=\"SVG-Generator\" />
            </div>
            <div class=\"actions\">
                <button id=\"generate\" type=\"submit\">Generate Frame</button>
                <span class=\"msg\" id=\"msg\"></span>
            </div>
        </form>
    </main>

    <script>
        async function loadFrame() {
            const frameEl = document.getElementById('frame');
            const metaEl = document.getElementById('meta');
            try {
                const res = await fetch('/latest-frame', { cache: 'no-store' });
                const payload = await res.json();

                if (!payload || payload.svg === null) {
                    metaEl.textContent = 'No frame yet. Call POST /generate-svg first.';
                    frameEl.innerHTML = '<p class="status">No SVG frame available yet.</p>';
                    return;
                }

                const prompt = payload.prompt || '(unknown prompt)';
                const agent = payload.agent_name || '(unknown agent)';
                const model = payload.model || '(unknown model)';
                const updatedAt = payload.updated_at || '(unknown time)';

                metaEl.textContent = 'Prompt: ' + prompt + ' | Agent: ' + agent + ' | Model: ' + model + ' | Updated: ' + updatedAt;
                frameEl.innerHTML = payload.svg;

                const svg = frameEl.querySelector('svg');
                if (svg) {
                    const vb = svg.getAttribute('viewBox');
                    if (!vb) {
                        svg.setAttribute('viewBox', '0 0 500 300');
                    }
                    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
                    svg.setAttribute('width', '500');
                    svg.setAttribute('height', '300');
                    svg.style.width = '100%';
                    svg.style.maxWidth = '500px';
                    svg.style.height = 'auto';
                    svg.style.maxHeight = '300px';
                    svg.style.overflow = 'hidden';
                }
            } catch (err) {
                metaEl.textContent = 'Failed to load frame.';
                frameEl.innerHTML = '<p class="status">Error loading latest frame.</p>';
            }
        }

        async function generateFrame(event) {
            event.preventDefault();

            const msgEl = document.getElementById('msg');
            const prompt = document.getElementById('prompt').value.trim();
            const agentName = document.getElementById('agent_name').value.trim() || 'SVG-Generator';

            if (!prompt) {
                msgEl.textContent = 'Please enter a prompt.';
                return;
            }

            msgEl.textContent = 'Generating...';
            try {
                const res = await fetch('/generate-svg', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: prompt, agent_name: agentName }),
                });

                if (!res.ok) {
                    let detail = 'Generation failed';
                    try {
                        const err = await res.json();
                        detail = err.detail || detail;
                    } catch (_) {
                        // Keep default message when response body is not JSON.
                    }
                    msgEl.textContent = detail;
                    return;
                }

                msgEl.textContent = 'Frame updated.';
                await loadFrame();
            } catch (err) {
                msgEl.textContent = 'Request failed. Check server/API key.';
            }
        }

        document.getElementById('reload').addEventListener('click', loadFrame);
        document.getElementById('generate-form').addEventListener('submit', generateFrame);
        loadFrame();
    </script>
</body>
</html>
"""


@app.post("/generate-svg", response_model=GenerateSvgResponse)
async def generate_svg_endpoint(request: GenerateSvgRequest) -> GenerateSvgResponse:
    logger.info(
        "[API] POST /generate-svg agent=%s prompt=%r",
        request.agent_name,
        request.prompt,
    )
    try:
        response = await generate_svg(request.prompt, request.agent_name)
        logger.info(
            "[API] generate-svg success model=%s svg_len=%d",
            response.model,
            len(response.svg),
        )
        app.state.latest_frame = {
            "prompt": request.prompt,
            "agent_name": response.agent_name,
            "model": response.model,
            "svg": response.svg,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return response
    except AgentNotFoundError as exc:
        logger.exception("[API] unknown agent")
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{exc.args[0]}'.",
        ) from exc
    except errors.APIError as exc:
        logger.exception("[API] upstream API error")
        raise HTTPException(status_code=502, detail=exc.message) from exc
    except GenerationTimeoutError as exc:
        logger.exception("[API] model generation timed out")
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[API] unhandled exception")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
