"""Tests for atlas_sight.data.history.SessionHistory."""
from __future__ import annotations

from atlas_sight.config import HistorySettings
from atlas_sight.data.history import SessionHistory
from atlas_sight.data.models import Scene


def _scene(desc: str = "test scene") -> Scene:
    return Scene(description=desc)


# ---------------------------------------------------------------------------
# Basic add / retrieve
# ---------------------------------------------------------------------------


class TestSessionHistory:
    def test_add_and_retrieve(self):
        h = SessionHistory()
        entry = h.add(_scene(), "First description")
        assert entry.spoken_text == "First description"
        assert len(h) == 1

    def test_add_multiple(self):
        h = SessionHistory()
        h.add(_scene(), "one")
        h.add(_scene(), "two")
        h.add(_scene(), "three")
        assert len(h) == 3

    def test_entries_property(self):
        h = SessionHistory()
        h.add(_scene(), "alpha")
        h.add(_scene(), "beta")
        entries = h.entries
        assert len(entries) == 2
        assert entries[0].spoken_text == "alpha"
        assert entries[1].spoken_text == "beta"

    def test_last_property(self):
        h = SessionHistory()
        assert h.last is None
        h.add(_scene(), "hello")
        assert h.last is not None
        assert h.last.spoken_text == "hello"

    def test_last_description(self):
        h = SessionHistory()
        assert h.last_description == ""
        h.add(_scene(), "spoken text")
        assert h.last_description == "spoken text"

    # ------------------------------------------------------------------
    # recent(n)
    # ------------------------------------------------------------------

    def test_recent_default(self):
        h = SessionHistory()
        for i in range(10):
            h.add(_scene(), f"entry {i}")
        recent = h.recent()
        assert len(recent) == 5
        assert recent[0].spoken_text == "entry 5"
        assert recent[-1].spoken_text == "entry 9"

    def test_recent_custom_n(self):
        h = SessionHistory()
        for i in range(10):
            h.add(_scene(), f"entry {i}")
        recent = h.recent(3)
        assert len(recent) == 3
        assert recent[0].spoken_text == "entry 7"

    def test_recent_more_than_entries(self):
        h = SessionHistory()
        h.add(_scene(), "only one")
        recent = h.recent(10)
        assert len(recent) == 1

    # ------------------------------------------------------------------
    # Bookmark
    # ------------------------------------------------------------------

    def test_bookmark_last(self):
        h = SessionHistory()
        h.add(_scene(), "to bookmark")
        entry = h.bookmark_last()
        assert entry is not None
        assert entry.bookmarked is True
        assert len(h.bookmarks) == 1

    def test_bookmark_last_empty_history(self):
        h = SessionHistory()
        assert h.bookmark_last() is None

    def test_bookmark_idempotent(self):
        h = SessionHistory()
        h.add(_scene(), "once")
        h.bookmark_last()
        h.bookmark_last()
        assert len(h.bookmarks) == 1

    def test_bookmark_limit(self):
        settings = HistorySettings(max_bookmarks=2)
        h = SessionHistory(settings=settings)
        h.add(_scene(), "a")
        h.bookmark_last()
        h.add(_scene(), "b")
        h.bookmark_last()
        h.add(_scene(), "c")
        h.bookmark_last()
        # Only first 2 should be bookmarked in _bookmarks list
        assert len(h.bookmarks) == 2

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def test_clear_preserves_bookmarks(self):
        h = SessionHistory()
        h.add(_scene(), "keep this")
        h.bookmark_last()
        h.add(_scene(), "lose this")
        h.clear()
        assert len(h) == 0
        assert len(h.bookmarks) == 1
        assert h.bookmarks[0].spoken_text == "keep this"

    def test_clear_empties_entries(self):
        h = SessionHistory()
        h.add(_scene(), "a")
        h.add(_scene(), "b")
        h.clear()
        assert h.last is None
        assert h.last_description == ""
        assert h.entries == []

    # ------------------------------------------------------------------
    # max_entries deque behavior
    # ------------------------------------------------------------------

    def test_max_entries_eviction(self):
        settings = HistorySettings(max_entries=3)
        h = SessionHistory(settings=settings)
        h.add(_scene(), "a")
        h.add(_scene(), "b")
        h.add(_scene(), "c")
        h.add(_scene(), "d")
        assert len(h) == 3
        assert h.entries[0].spoken_text == "b"
        assert h.entries[-1].spoken_text == "d"

    def test_mode_is_recorded(self):
        h = SessionHistory()
        entry = h.add(_scene(), "nav desc", mode="navigate")
        assert entry.mode == "navigate"
