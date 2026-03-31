"""Camera management — capture frames for the vision pipeline.

Uses OpenCV when available, gracefully degrades when running headless
or on devices without a camera.  All blocking I/O is pushed to a
thread-pool via ``asyncio.to_thread`` so the main event loop stays
responsive.
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

from atlas_sight.config import VisionSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: OpenCV
# ---------------------------------------------------------------------------

_HAS_CV2 = False
try:
    import cv2  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Optional dependency: Pillow (always available in practice)
# ---------------------------------------------------------------------------

_HAS_PIL = False
try:
    from PIL import Image as _PILImage

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _PILImage = None  # type: ignore[assignment,misc]


class CameraManager:
    """Async wrapper around an OpenCV ``VideoCapture`` device.

    Parameters
    ----------
    settings:
        Vision configuration — mainly ``camera_index``, ``frame_width``,
        and ``frame_height``.

    Usage::

        async with CameraManager(settings) as cam:
            frame = await cam.capture_frame()
    """

    def __init__(self, settings: VisionSettings) -> None:
        self._settings = settings
        self._cap: cv2.VideoCapture | None = None  # type: ignore[name-defined]
        self._started = False
        self._lock = asyncio.Lock()

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Open the camera device."""
        if not _HAS_CV2:
            logger.warning(
                "OpenCV not installed — camera capture disabled. "
                "Install with: pip install opencv-python-headless"
            )
            return
        async with self._lock:
            if self._started:
                return
            self._cap = await asyncio.to_thread(self._open_camera)
            if self._cap is not None and self._cap.isOpened():
                self._started = True
                logger.info(
                    "Camera %d opened (%dx%d)",
                    self._settings.camera_index,
                    self._settings.frame_width,
                    self._settings.frame_height,
                )
            else:
                logger.error(
                    "Failed to open camera %d", self._settings.camera_index
                )
                self._cap = None

    async def stop(self) -> None:
        """Release the camera device."""
        async with self._lock:
            if self._cap is not None:
                await asyncio.to_thread(self._cap.release)
                logger.info("Camera %d released", self._settings.camera_index)
            self._cap = None
            self._started = False

    # -- capture ------------------------------------------------------------

    async def capture_frame(self) -> bytes | None:
        """Capture a single JPEG-encoded frame.

        Returns ``None`` when the camera is unavailable or a frame
        cannot be read.
        """
        await self._ensure_camera()
        if self._cap is None:
            return None
        frame = await asyncio.to_thread(self._read_frame)
        if frame is None:
            return None
        return await asyncio.to_thread(self._encode_jpeg, frame)

    async def capture_pil_image(self) -> Image | None:
        """Capture a frame and return it as a PIL ``Image``.

        Useful for VLM pipelines that expect PIL inputs.  Returns
        ``None`` when either OpenCV or Pillow is unavailable.
        """
        if not _HAS_PIL:
            logger.warning("Pillow not installed — cannot return PIL Image")
            return None
        jpeg = await self.capture_frame()
        if jpeg is None:
            return None
        return _PILImage.open(io.BytesIO(jpeg))  # type: ignore[union-attr]

    # -- context manager ----------------------------------------------------

    async def __aenter__(self) -> CameraManager:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.stop()

    # -- internals ----------------------------------------------------------

    async def _ensure_camera(self) -> None:
        """Lazily initialise the camera if not already open."""
        if not self._started:
            await self.start()

    def _open_camera(self) -> cv2.VideoCapture | None:  # type: ignore[name-defined]
        """Blocking helper — runs in a thread."""
        cap = cv2.VideoCapture(self._settings.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._settings.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._settings.frame_height)
        return cap

    def _read_frame(self) -> np.ndarray | None:  # type: ignore[name-defined]
        """Blocking helper — grab one frame."""
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            logger.debug("Frame read failed on camera %d", self._settings.camera_index)
            return None
        return frame

    @staticmethod
    def _encode_jpeg(frame: np.ndarray, quality: int = 85) -> bytes | None:  # type: ignore[name-defined]
        """Blocking helper — encode a BGR frame to JPEG bytes."""
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return None
        return buf.tobytes()
