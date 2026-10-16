"""HTTP API and the Clearpath desk."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agents import ask
from app.db import ping
from app.seed import ensure_seeded, reset_all

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ready = False
    app.state.error = "FalkorDB is not connected yet."
    for _ in range(30):
        try:
            ping()
            ensure_seeded()
            app.state.ready = True
            app.state.error = ""
            break
        except Exception as exc:
            app.state.error = str(exc)
            time.sleep(1)
    yield


app = FastAPI(title="Clearpath", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    user_id: str = "aditya"
    session_id: str = "session"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": bool(app.state.ready), "error": app.state.error}


@app.post("/api/ask")
def ask_route(body: AskIn):
    if not app.state.ready:
        raise HTTPException(status_code=503, detail=app.state.error or "FalkorDB is not connected.")
    try:
        return ask(body.question, body.user_id, body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reset")
def reset_route():
    try:
        reset_all()
        app.state.ready = True
        app.state.error = ""
    except Exception as exc:
        app.state.ready = False
        app.state.error = str(exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}
