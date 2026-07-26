from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os

app = FastAPI()

VIEW_HTML_PATH = os.path.join(os.path.dirname(__file__), "static", "view.html")


@app.get("/view/{room_id}", response_class=HTMLResponse)
async def view_page(room_id: str):
    with open(VIEW_HTML_PATH, "r") as f:
        return f.read()


@app.get("/")
async def root():
    return {"status": "V2V backend running"}
