# Gemma-Hackathon-

## V2V Backend

FastAPI backend for Voice to Visual using hosted Gemma through the Google GenAI SDK.

### Structure

- `src/backend/main.py`
- `src/backend/services/gemma.py`
- `src/backend/agents.json`

### Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`.

### Run

```bash
uvicorn src.backend.main:app --reload
```

### Endpoints

- `GET /health`
- `GET /agents`
- `POST /generate-svg`
- `GET /latest-frame`
- `GET /viewer`

Example request:

```json
{
	"prompt": "Draw a pouch with one red token and two blue tokens.",
	"agent_name": "SVG-Generator"
}
```

### Quick visual testing loop

1. Start backend.
2. Open `http://127.0.0.1:8000/viewer` in a browser.
3. Send `POST /generate-svg` with a prompt.
4. Refresh the viewer page (or click Reload Current Frame) to see the latest generated SVG.