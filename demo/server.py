"""Atlas Sight — Demo Server.

FastAPI server that serves the phone UI and proxies vision requests
to llama-server running on Overwatch.
"""
from __future__ import annotations

import argparse
import base64
import logging
import os
import re
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("atlas-sight")

LLAMA_HOST = os.getenv("LLAMA_HOST", "192.168.3.8")
LLAMA_PORT = os.getenv("LLAMA_PORT", "8080")
LLAMA_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
SIGHT_PORT = int(os.getenv("SIGHT_PORT", "5200"))
DEMO_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(application: FastAPI):
    yield
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


app = FastAPI(title="Atlas Sight Demo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared httpx client for llama-server communication
_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_think(text: str) -> str:
    """Remove Qwen3 thinking blocks, keeping only the final answer."""
    if "<think>" not in text:
        return text

    # Case 1: Closed think blocks — <think>...</think>actual answer
    cleaned = _THINK_RE.sub("", text).strip()
    if cleaned and "<think>" not in cleaned:
        return cleaned

    # Case 2: Unclosed think block — model used all tokens thinking.
    # Extract any content after the last complete thought.
    inner = text
    if inner.startswith("<think>"):
        inner = inner[7:]
    if inner.endswith("</think>"):
        inner = inner[:-8]

    # Salvage useful sentences from the thinking output
    lines = inner.strip().split("\n")
    content_lines = []
    for line in reversed(lines):
        stripped = line.strip().lstrip("*-•0123456789.) ")
        # Skip short/empty lines
        if not stripped or len(stripped) < 15:
            continue
        lower = stripped.lower()
        # Skip meta/planning lines
        skip_prefixes = (
            "thinking", "analyz", "determin", "constraint", "task:",
            "input", "role:", "check", "critique", "draft", "revised",
            "wait,", "correction", "further", "refin", "sentence ",
            "let's", "let me", "i need to", "i should", "maybe",
            "constraint", "length:", "tone:", "content:", "final",
            "actually", "version", "optimiz", "keep it",
        )
        if any(lower.startswith(s) for s in skip_prefixes):
            continue
        # Skip lines with heavy markdown formatting or labels
        if stripped.startswith("**") or stripped.endswith(":**"):
            continue
        # Skip lines that reference prompt mechanics
        if "preamble" in lower or "persona" in lower or "constraint" in lower:
            continue
        # Skip lines with quote marks wrapping (drafts)
        if stripped.startswith('"') and stripped.endswith('"'):
            continue
        # Skip lines with parenthetical annotations like "(1 sentence)"
        if re.search(r'\(\d+ sentence', stripped):
            continue
        content_lines.insert(0, stripped)
        if len(content_lines) >= 3:
            break

    if content_lines:
        return " ".join(content_lines)
    return "I received your request but need a moment. Please try again."


async def llm_generate(prompt: str, max_tokens: int = 512) -> str:
    """Send a prompt to llama-server and return the completion text."""
    client = await get_client()
    try:
        resp = await client.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Respond directly and concisely. No preamble."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        return _strip_think(text)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach llama-server at {LLAMA_URL}",
        )
    except Exception as exc:
        logger.exception("LLM generate failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the single-page phone UI."""
    html_path = DEMO_DIR / "index.html"
    return HTMLResponse(html_path.read_text())


@app.post("/describe")
async def describe(request: Request):
    """Receive a base64-encoded image and return a scene description.

    For now (no VLM), we ask the LLM to generate a helpful response
    acknowledging we're in demo mode. When a real VLM is connected,
    this endpoint swaps in actual image understanding.
    """
    body = await request.json()
    image_b64: str = body.get("image", "")
    context: str = body.get("context", "general")
    mode: str = body.get("mode", "describe")

    # Validate we actually received image data
    if not image_b64:
        raise HTTPException(status_code=400, detail="No image data provided")

    # Strip data URI prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    # Calculate approximate image size for context
    image_bytes = len(base64.b64decode(image_b64))
    image_kb = image_bytes / 1024

    if mode == "read_text":
        prompt = (
            "You are Atlas Sight, an AI assistant helping a visually impaired person. "
            "The user just pointed their phone camera at something and asked you to "
            "read any text visible. This is a DEMO without real vision — acknowledge "
            "that you received their camera frame and explain that real text reading "
            "will work once the vision model is connected. Be warm, brief, and helpful. "
            "Suggest they try pointing at a sign, label, or document."
        )
    elif mode == "emergency":
        prompt = (
            "You are Atlas Sight, an AI assistant helping a visually impaired person. "
            "The user triggered the 'where am I?' emergency mode. This is a DEMO without "
            "real vision — acknowledge the emergency request and explain that with real "
            "vision, you would describe their surroundings, identify landmarks, read signs, "
            "and help them orient themselves. Be reassuring, calm, and brief."
        )
    else:
        prompt = (
            "You are Atlas Sight, an AI assistant helping a visually impaired person. "
            "The user just captured an image with their phone camera. "
            f"Image received: {image_kb:.0f} KB, context: {context}. "
            "This is a DEMO — real vision is not yet connected, but the camera capture "
            "pipeline is working. Acknowledge you received the image and briefly describe "
            "what you WOULD do with real vision: identify objects, read text, describe "
            "people, detect obstacles, read labels, describe spatial layout. "
            "Be warm, concise (2-3 sentences max), and encouraging."
        )

    description = await llm_generate(prompt, max_tokens=1500)
    return JSONResponse({"description": description, "mode": mode})


@app.post("/ask")
async def ask(request: Request):
    """Receive a text question (+ optional image context) and return an answer."""
    body = await request.json()
    question: str = body.get("question", "")
    image_context: str = body.get("image_context", "")

    if not question.strip():
        raise HTTPException(status_code=400, detail="No question provided")

    context_part = ""
    if image_context:
        context_part = f" The user previously captured an image described as: '{image_context}'."

    prompt = (
        "You are Atlas Sight, an AI assistant helping a visually impaired person. "
        f"The user asks: \"{question}\"{context_part} "
        "Answer helpfully and concisely. If the question relates to something visual "
        "and you don't have image data, say so honestly. "
        "Keep your response under 3 sentences for easy listening."
    )

    answer = await llm_generate(prompt, max_tokens=1500)
    return JSONResponse({"answer": answer})


@app.get("/health")
async def health():
    """Check server health and llama-server connectivity."""
    llama_ok = False
    llama_detail = ""
    try:
        client = await get_client()
        resp = await client.get(f"{LLAMA_URL}/health", timeout=5.0)
        llama_ok = resp.status_code == 200
        llama_detail = "connected"
    except Exception as exc:
        llama_detail = str(exc)

    return JSONResponse({
        "status": "ok",
        "llama_server": {
            "url": LLAMA_URL,
            "connected": llama_ok,
            "detail": llama_detail,
        },
    })



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Atlas Sight Demo Server")
    parser.add_argument("--ssl", action="store_true", help="Enable HTTPS with self-signed cert")
    parser.add_argument("--port", type=int, default=SIGHT_PORT)
    args = parser.parse_args()

    ssl_kwargs: dict = {}
    if args.ssl:
        cert_path = DEMO_DIR / "cert.pem"
        key_path = DEMO_DIR / "key.pem"
        if not cert_path.exists() or not key_path.exists():
            print("Generating self-signed certificate...")
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:2048",
                    "-keyout", str(key_path), "-out", str(cert_path),
                    "-days", "365", "-nodes", "-subj", "/CN=atlas-sight",
                ],
                check=True,
            )
        ssl_kwargs["ssl_certfile"] = str(cert_path)
        ssl_kwargs["ssl_keyfile"] = str(key_path)

    print(f"\n  Atlas Sight Demo Server")
    print(f"  Listening on port {args.port}")
    print(f"  LLM backend: {LLAMA_URL}")
    if args.ssl:
        print(f"  HTTPS enabled (self-signed)")
    print()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
