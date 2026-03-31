"""Tests for atlas_sight.vision (camera, vlm, ocr, detector)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlas_sight.config import VisionSettings
from atlas_sight.data.models import BoundingBox, ObjectCategory, TextBlock
from atlas_sight.vision.camera import CameraManager
from atlas_sight.vision.detector import CATEGORY_MAP, ObjectDetector
from atlas_sight.vision.ocr import TextReader
from atlas_sight.vision.vlm import VisionLM, VisionLMBase


# ===========================================================================
# CameraManager
# ===========================================================================


class TestCameraManager:
    async def test_capture_returns_none_without_cv2(self):
        with patch("atlas_sight.vision.camera._HAS_CV2", False):
            cam = CameraManager(VisionSettings())
            result = await cam.capture_frame()
            assert result is None

    async def test_start_without_cv2_logs_warning(self):
        with patch("atlas_sight.vision.camera._HAS_CV2", False):
            cam = CameraManager(VisionSettings())
            await cam.start()
            assert cam._started is False

    async def test_stop_idempotent(self):
        with patch("atlas_sight.vision.camera._HAS_CV2", False):
            cam = CameraManager(VisionSettings())
            await cam.stop()
            assert cam._started is False

    async def test_context_manager(self):
        with patch("atlas_sight.vision.camera._HAS_CV2", False):
            async with CameraManager(VisionSettings()) as cam:
                assert cam._started is False


# ===========================================================================
# VisionLM
# ===========================================================================


class TestVisionLM:
    async def test_describe_without_model(self):
        vlm = VisionLM(model_path="", max_image_size=448)
        result = await vlm.describe(b"\x00", prompt="test")
        assert "not loaded" in result.lower()

    async def test_answer_without_model(self):
        vlm = VisionLM()
        result = await vlm.answer(b"\x00", "question")
        assert "not loaded" in result.lower()

    def test_is_loaded_false_by_default(self):
        vlm = VisionLM()
        assert vlm.is_loaded is False

    async def test_load_model_no_path(self):
        vlm = VisionLM(model_path="")
        await vlm.load_model()
        assert vlm.is_loaded is False

    async def test_load_model_no_transformers(self):
        with patch("atlas_sight.vision.vlm._HAS_TRANSFORMERS", False):
            vlm = VisionLM(model_path="some/model")
            await vlm.load_model()
            assert vlm.is_loaded is False

    async def test_unload_model_noop(self):
        vlm = VisionLM()
        await vlm.unload_model()  # Should not raise


# ===========================================================================
# OCR — TextReader
# ===========================================================================


class _MockVLM(VisionLMBase):
    """Minimal mock VLM for testing OCR and Detector."""

    def __init__(self, answer_text: str = ""):
        self._answer_text = answer_text
        self._loaded = True

    async def describe(self, image: bytes, prompt: str | None = None) -> str:
        return "test description"

    async def answer(self, image: bytes, question: str) -> str:
        return self._answer_text

    async def load_model(self) -> None:
        self._loaded = True

    async def unload_model(self) -> None:
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded


class TestTextReader:
    async def test_read_structured_response(self):
        vlm = _MockVLM(
            answer_text=(
                'TEXT: "Exit Sign" | POSITION: top-center | LANG: en\n'
                'TEXT: "Room 204" | POSITION: center | LANG: en'
            )
        )
        reader = TextReader(vlm, confidence_threshold=0.0)
        blocks = await reader.read(b"\x00")
        assert len(blocks) == 2
        assert blocks[0].text == "Exit Sign"
        assert blocks[1].text == "Room 204"

    async def test_read_no_text_found(self):
        vlm = _MockVLM(answer_text="NO_TEXT_FOUND")
        reader = TextReader(vlm)
        blocks = await reader.read(b"\x00")
        assert blocks == []

    async def test_read_freeform_fallback(self):
        vlm = _MockVLM(answer_text="- Warning sign\n- No parking")
        reader = TextReader(vlm, confidence_threshold=0.0)
        blocks = await reader.read(b"\x00")
        assert len(blocks) >= 2

    async def test_read_unloaded_vlm(self):
        vlm = _MockVLM()
        vlm._loaded = False
        reader = TextReader(vlm)
        blocks = await reader.read(b"\x00")
        assert blocks == []

    async def test_confidence_threshold_filters(self):
        vlm = _MockVLM(answer_text="- short text\n- another")
        reader = TextReader(vlm, confidence_threshold=0.9)
        blocks = await reader.read(b"\x00")
        # Free-form fallback gives low confidence (0.45), should be filtered
        assert blocks == []


class TestOCRParsing:
    def test_parse_with_language(self):
        vlm = _MockVLM()
        reader = TextReader(vlm)
        blocks = reader._parse_vlm_response(
            'TEXT: "Bonjour" | POSITION: center | LANG: fr'
        )
        assert len(blocks) == 1
        assert blocks[0].language == "fr"

    def test_parse_empty_response(self):
        vlm = _MockVLM()
        reader = TextReader(vlm)
        assert reader._parse_vlm_response("") == []

    def test_heuristic_confidence_structured(self):
        assert TextReader._heuristic_confidence("hello", structured=True) >= 0.7

    def test_heuristic_confidence_freeform(self):
        assert TextReader._heuristic_confidence("hello", structured=False) < 0.7


# ===========================================================================
# ObjectDetector
# ===========================================================================


class TestObjectDetector:
    async def test_detect_structured_response(self):
        vlm = _MockVLM(
            answer_text=(
                "OBJ: chair | BBOX: 0.1, 0.2, 0.5, 0.8 | SIZE: medium\n"
                "OBJ: person | BBOX: 0.6, 0.1, 0.9, 0.9 | SIZE: large"
            )
        )
        detector = ObjectDetector(vlm, confidence_threshold=0.0)
        objects = await detector.detect(b"\x00")
        assert len(objects) == 2
        labels = {o.label for o in objects}
        assert "chair" in labels
        assert "person" in labels

    async def test_detect_no_objects(self):
        vlm = _MockVLM(answer_text="NO_OBJECTS_FOUND")
        detector = ObjectDetector(vlm)
        objects = await detector.detect(b"\x00")
        assert objects == []

    async def test_detect_unloaded_vlm(self):
        vlm = _MockVLM()
        vlm._loaded = False
        detector = ObjectDetector(vlm)
        objects = await detector.detect(b"\x00")
        assert objects == []

    async def test_detect_freeform_fallback(self):
        vlm = _MockVLM(answer_text="- car\n- bicycle\n- tree")
        detector = ObjectDetector(vlm, confidence_threshold=0.0)
        objects = await detector.detect(b"\x00")
        assert len(objects) >= 3


class TestCategoryClassification:
    def test_exact_match(self):
        assert ObjectDetector._classify_category("person") == ObjectCategory.PERSON
        assert ObjectDetector._classify_category("car") == ObjectCategory.VEHICLE
        assert ObjectDetector._classify_category("stairs") == ObjectCategory.STAIRS

    def test_substring_match(self):
        assert ObjectDetector._classify_category("traffic sign post") == ObjectCategory.SIGN
        assert ObjectDetector._classify_category("large doorway") == ObjectCategory.DOOR

    def test_unknown_category(self):
        assert ObjectDetector._classify_category("alien spacecraft") == ObjectCategory.OTHER

    def test_case_insensitive(self):
        assert ObjectDetector._classify_category("Person") == ObjectCategory.PERSON


class TestCategoryMap:
    def test_key_categories(self):
        assert CATEGORY_MAP["person"] == ObjectCategory.PERSON
        assert CATEGORY_MAP["car"] == ObjectCategory.VEHICLE
        assert CATEGORY_MAP["chair"] == ObjectCategory.FURNITURE
        assert CATEGORY_MAP["door"] == ObjectCategory.DOOR
        assert CATEGORY_MAP["stairs"] == ObjectCategory.STAIRS
        assert CATEGORY_MAP["pole"] == ObjectCategory.OBSTACLE
        assert CATEGORY_MAP["sign"] == ObjectCategory.SIGN
        assert CATEGORY_MAP["dog"] == ObjectCategory.ANIMAL
        assert CATEGORY_MAP["food"] == ObjectCategory.FOOD
        assert CATEGORY_MAP["phone"] == ObjectCategory.ELECTRONIC

    def test_safe_bbox_invalid(self):
        assert ObjectDetector._safe_bbox("abc", "0.1", "0.5", "0.8") is None

    def test_safe_bbox_inverted(self):
        assert ObjectDetector._safe_bbox("0.8", "0.8", "0.1", "0.1") is None

    def test_safe_bbox_valid(self):
        bb = ObjectDetector._safe_bbox("0.1", "0.2", "0.5", "0.8")
        assert bb is not None
        assert bb.x_min == pytest.approx(0.1)
