"""Vision Language Model — scene description and visual Q&A.

Designed for tiny VLMs (Qwen3-VL-0.8B Q4 or similar) that can run on
phones with 1–2 GB RAM.  Heavy model operations are off-loaded to a
background thread so the async event loop is never blocked.
"""
from __future__ import annotations

import abc
import asyncio
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------

_HAS_TRANSFORMERS = False
try:
    from transformers import (  # type: ignore[import-untyped]
        AutoProcessor,
        AutoModelForVision2Seq,
    )

    _HAS_TRANSFORMERS = True
except ImportError:  # pragma: no cover
    AutoProcessor = None  # type: ignore[assignment,misc]
    AutoModelForVision2Seq = None  # type: ignore[assignment,misc]

_HAS_PIL = False
try:
    from PIL import Image as PILImage  # type: ignore[import-untyped]

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    PILImage = None  # type: ignore[assignment,misc]

_HAS_TORCH = False
try:
    import torch  # type: ignore[import-untyped]

    _HAS_TORCH = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_DESCRIBE_SYSTEM = (
    "You are describing a scene for a blind person. Be concise but mention "
    "obstacles, people, text, and spatial layout. Use clock-face directions "
    "(e.g. 'at 2 o'clock') when helpful."
)

_DESCRIBE_USER = "Describe what you see in this image."

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class VisionLMBase(abc.ABC):
    """Interface for all vision-language model backends."""

    @abc.abstractmethod
    async def describe(self, image: bytes, prompt: str | None = None) -> str:
        """Return a natural-language description of *image*.

        Parameters
        ----------
        image:
            JPEG or PNG bytes.
        prompt:
            Optional user prompt to guide the description.
        """

    @abc.abstractmethod
    async def answer(self, image: bytes, question: str) -> str:
        """Answer a free-form *question* about *image*."""

    @abc.abstractmethod
    async def load_model(self) -> None:
        """Load model weights into memory."""

    @abc.abstractmethod
    async def unload_model(self) -> None:
        """Release model weights and free memory."""

    @property
    @abc.abstractmethod
    def is_loaded(self) -> bool:
        """``True`` when the model is ready for inference."""


# ---------------------------------------------------------------------------
# Concrete implementation — small transformers VLM
# ---------------------------------------------------------------------------


class VisionLM(VisionLMBase):
    """Concrete VLM backed by a HuggingFace ``transformers`` model.

    Parameters
    ----------
    model_path:
        HuggingFace model ID or local path.  Defaults to an empty
        string (model must be loaded explicitly or the path set before
        calling :meth:`load_model`).
    max_image_size:
        Resize input images so the longest edge does not exceed this
        value.  Smaller images → faster inference on constrained devices.
    """

    def __init__(
        self,
        model_path: str = "",
        max_image_size: int = 448,
    ) -> None:
        self._model_path = model_path
        self._max_image_size = max_image_size
        self._model: Any = None
        self._processor: Any = None
        self._device: str = "cpu"
        self._lock = asyncio.Lock()

    # -- lifecycle ----------------------------------------------------------

    async def load_model(self) -> None:
        """Load model and processor from *model_path*."""
        if self._model is not None:
            return
        if not self._model_path:
            logger.warning("No VLM model path configured — skipping load")
            return
        if not _HAS_TRANSFORMERS or not _HAS_TORCH:
            logger.warning(
                "transformers/torch not installed — VLM unavailable. "
                "Install with: pip install transformers torch"
            )
            return

        async with self._lock:
            if self._model is not None:
                return
            logger.info("Loading VLM from %s …", self._model_path)
            self._processor, self._model = await asyncio.to_thread(
                self._load_model_sync
            )
            if self._model is not None:
                logger.info("VLM loaded on %s", self._device)

    async def unload_model(self) -> None:
        """Release model and processor to free memory."""
        async with self._lock:
            if self._model is None:
                return
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            if _HAS_TORCH and torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("VLM unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    # -- inference ----------------------------------------------------------

    async def describe(self, image: bytes, prompt: str | None = None) -> str:
        if not self.is_loaded:
            return "Vision model not loaded — cannot describe the scene."
        user_prompt = prompt or _DESCRIBE_USER
        return await asyncio.to_thread(
            self._generate_sync, image, _DESCRIBE_SYSTEM, user_prompt
        )

    async def answer(self, image: bytes, question: str) -> str:
        if not self.is_loaded:
            return "Vision model not loaded — cannot answer questions."
        system = (
            "You are a helpful visual assistant for a blind user. "
            "Answer the question about this image clearly and concisely."
        )
        return await asyncio.to_thread(
            self._generate_sync, image, system, question
        )

    # -- internals ----------------------------------------------------------

    def _load_model_sync(self) -> tuple[Any, Any]:
        """Blocking helper — load model weights."""
        try:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            processor = AutoProcessor.from_pretrained(
                self._model_path, trust_remote_code=True
            )
            model = AutoModelForVision2Seq.from_pretrained(
                self._model_path,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                low_cpu_mem_usage=True,
            ).to(self._device)
            model.eval()
            return processor, model
        except Exception:
            logger.exception("Failed to load VLM from %s", self._model_path)
            return None, None

    def _generate_sync(
        self, image_bytes: bytes, system: str, user_prompt: str
    ) -> str:
        """Blocking helper — run a single generation turn."""
        try:
            pil_img = self._bytes_to_pil(image_bytes)
            if pil_img is None:
                return "Could not decode image."

            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ]

            text_prompt = self._processor.apply_chat_template(
                messages, add_generation_prompt=True
            )
            inputs = self._processor(
                text=text_prompt,
                images=[pil_img],
                return_tensors="pt",
            ).to(self._device)

            with torch.inference_mode():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                )

            # Decode only the new tokens (skip the prompt tokens)
            generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]
            result: str = self._processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]
            return result.strip()
        except Exception:
            logger.exception("VLM generation failed")
            return "Error during image analysis."

    def _bytes_to_pil(self, data: bytes) -> Any:
        """Convert raw image bytes to a PIL Image, resizing if needed."""
        if not _HAS_PIL:
            return None
        try:
            img = PILImage.open(io.BytesIO(data)).convert("RGB")
            # Resize to fit within max_image_size while preserving aspect ratio
            w, h = img.size
            longest = max(w, h)
            if longest > self._max_image_size:
                scale = self._max_image_size / longest
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = img.resize((new_w, new_h), PILImage.LANCZOS)
            return img
        except Exception:
            logger.exception("Failed to decode image bytes")
            return None
