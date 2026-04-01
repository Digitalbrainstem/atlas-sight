"""Atlas Sight — Proxy Server.

Minimal FastAPI server that serves the phone UI and proxies
LLM requests to llama-server running locally in Termux.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("atlas-sight")

LLAMA_HOST = os.getenv("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = os.getenv("LLAMA_PORT", "8080")
LLAMA_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
SIGHT_PORT = int(os.getenv("SIGHT_PORT", "5200"))
DEMO_DIR = Path(__file__).parent

app = FastAPI(title="Atlas Sight")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


# ---------------------------------------------------------------------------
# Qwen3 think-tag stripping
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_think(text: str) -> str:
    """Remove Qwen3 thinking blocks, keeping only the final answer."""
    if "<think>" not in text:
        return text

    cleaned = _THINK_RE.sub("", text).strip()
    if cleaned and "<think>" not in cleaned:
        return cleaned

    # Unclosed think block — salvage useful content
    inner = text.removeprefix("<think>").removesuffix("</think>").strip()
    lines = inner.split("\n")
    content = []
    for line in reversed(lines):
        s = line.strip().lstrip("*-•0123456789.) ")
        if not s or len(s) < 15:
            continue
        low = s.lower()
        if any(low.startswith(p) for p in (
            "thinking", "analyz", "determin", "constraint", "task:", "input",
            "role:", "check", "critique", "draft", "revised", "wait,",
            "correction", "further", "refin", "sentence ", "let's", "let me",
            "i need to", "i should", "maybe", "length:", "tone:", "content:",
            "final", "actually", "version", "optimiz", "keep it",
        )):
            continue
        if s.startswith("**") or s.endswith(":**"):
            continue
        if s.startswith('"') and s.endswith('"'):
            continue
        content.insert(0, s)
        if len(content) >= 3:
            break
    return " ".join(content) if content else "Please try again."


async def llm_generate(prompt: str, max_tokens: int = 1500) -> str:
    """Send a prompt to local llama-server."""
    client = await get_client()
    try:
        resp = await client.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": "Respond directly and concisely. No preamble."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return _strip_think(data["choices"][0]["message"]["content"].strip())
    except httpx.ConnectError:
        raise HTTPException(502, f"Cannot reach llama-server at {LLAMA_URL}. Is it running?")
    except Exception as exc:
        logger.exception("LLM generate failed")
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((DEMO_DIR / "index.html").read_text())


@app.post("/describe")
async def describe(request: Request):
    body = await request.json()
    image_b64: str = body.get("image", "")
    mode: str = body.get("mode", "describe")

    if not image_b64:
        raise HTTPException(400, "No image data provided")

    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    image_kb = len(base64.b64decode(image_b64)) / 1024

    prompts = {
        "read_text": (
            "You are Atlas Sight, helping a visually impaired person. "
            "They want to read text from their camera. This is a demo without real vision — "
            "acknowledge and explain text reading comes with the vision model. Be warm, 2 sentences."
        ),
        "emergency": (
            "You are Atlas Sight, helping a visually impaired person. "
            "They triggered 'where am I?' emergency mode. This is a demo — acknowledge "
            "and explain that real vision would describe surroundings and landmarks. "
            "Be reassuring, 2 sentences."
        ),
    }
    prompt = prompts.get(mode, (
        "You are Atlas Sight, helping a visually impaired person. "
        f"They captured an image ({image_kb:.0f}KB). This is a demo — real vision coming soon. "
        "Acknowledge the image, briefly say what you WOULD do: identify objects, read text, "
        "detect obstacles, describe layout. Be warm, 2-3 sentences."
    ))

    description = await llm_generate(prompt)
    return JSONResponse({"description": description, "mode": mode})


@app.post("/ask")
async def ask(request: Request):
    body = await request.json()
    question: str = body.get("question", "")
    image_context: str = body.get("image_context", "")

    if not question.strip():
        raise HTTPException(400, "No question provided")

    ctx = f" Previously saw: '{image_context}'." if image_context else ""
    prompt = (
        f"You are Atlas Sight, helping a visually impaired person. "
        f"They ask: \"{question}\"{ctx} "
        "Answer helpfully in under 3 sentences."
    )

    return JSONResponse({"answer": await llm_generate(prompt)})


@app.get("/health")
async def health():
    client = await get_client()
    ok, detail = False, ""
    try:
        resp = await client.get(f"{LLAMA_URL}/health", timeout=5.0)
        ok = resp.status_code == 200
        detail = "connected"
    except Exception as exc:
        detail = str(exc) or "connection failed"

    return JSONResponse({
        "status": "ok",
        "llama_server": {"url": LLAMA_URL, "connected": ok, "detail": detail},
    })


if __name__ == "__main__":
    print(f"\n  Atlas Sight Server")
    print(f"  UI:    http://localhost:{SIGHT_PORT}")
    print(f"  LLM:   {LLAMA_URL}\n")
    uvicorn.run(app, host="127.0.0.1", port=SIGHT_PORT, log_level="info")

