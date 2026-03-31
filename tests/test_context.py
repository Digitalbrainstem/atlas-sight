"""Tests for atlas_sight.core.context.ContextTracker."""
from __future__ import annotations

from atlas_sight.core.context import ContextTracker
from atlas_sight.data.history import SessionHistory
from atlas_sight.data.models import Scene


def _scene(desc: str = "test") -> Scene:
    return Scene(description=desc)


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


class TestSimilarity:
    def test_identical_strings(self):
        assert ContextTracker._similarity("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert ContextTracker._similarity("cat dog", "fish bird") == 0.0

    def test_partial_overlap(self):
        s = ContextTracker._similarity("the big red car", "the big blue truck")
        assert 0.0 < s < 1.0

    def test_empty_string_a(self):
        assert ContextTracker._similarity("", "hello") == 0.0

    def test_empty_string_b(self):
        assert ContextTracker._similarity("hello", "") == 0.0

    def test_both_empty(self):
        assert ContextTracker._similarity("", "") == 0.0

    def test_case_insensitive(self):
        assert ContextTracker._similarity("Hello World", "hello world") == 1.0


# ---------------------------------------------------------------------------
# was_recently_described
# ---------------------------------------------------------------------------


class TestWasRecentlyDescribed:
    def test_not_recently_described_empty_history(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        assert tracker.was_recently_described("new scene") is False

    def test_recently_described_identical(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        tracker.add(_scene(), "a person crossing the street")
        assert tracker.was_recently_described("a person crossing the street") is True

    def test_recently_described_similar(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        tracker.add(_scene(), "a person crossing the street quickly")
        # High similarity should pass
        assert tracker.was_recently_described(
            "a person crossing the street",
            threshold=0.6,
        ) is True

    def test_not_recently_described_different(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        tracker.add(_scene(), "a cat sleeping on a couch")
        assert tracker.was_recently_described("cars parked on a street") is False


# ---------------------------------------------------------------------------
# Context prompt
# ---------------------------------------------------------------------------


class TestContextPrompt:
    def test_empty_history(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        assert tracker.get_context_prompt() == ""

    def test_with_entries(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        tracker.add(_scene(), "A person crossing the street")
        tracker.add(_scene(), "Two parked cars on the left")
        prompt = tracker.get_context_prompt()
        assert "Previously described:" in prompt
        assert "A person crossing the street" in prompt
        assert "Two parked cars on the left" in prompt

    def test_truncates_long_text(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        long_text = "a" * 200
        tracker.add(_scene(), long_text)
        prompt = tracker.get_context_prompt()
        assert "..." in prompt


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestContextProperties:
    def test_last_description_empty(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        assert tracker.last_description == ""

    def test_last_description_after_add(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        tracker.add(_scene(), "test text")
        assert tracker.last_description == "test text"

    def test_recent_descriptions(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        for i in range(7):
            tracker.add(_scene(), f"desc {i}")
        recent = tracker.recent_descriptions
        assert len(recent) == 5
        assert recent[-1] == "desc 6"


# ---------------------------------------------------------------------------
# Add delegates to history
# ---------------------------------------------------------------------------


class TestAddDelegation:
    def test_add_returns_entry(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        entry = tracker.add(_scene(), "spoke this", mode="read")
        assert entry.spoken_text == "spoke this"
        assert entry.mode == "read"

    def test_add_increases_history_length(self):
        history = SessionHistory()
        tracker = ContextTracker(history)
        tracker.add(_scene(), "first")
        tracker.add(_scene(), "second")
        assert len(history) == 2
