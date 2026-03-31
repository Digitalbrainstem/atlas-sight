"""Session history — remember what we described recently."""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from atlas_sight.config import HistorySettings
from atlas_sight.data.models import HistoryEntry, Scene

logger = logging.getLogger(__name__)


@dataclass
class SessionHistory:
    """Tracks recently described scenes so we don't repeat ourselves.

    Thread-safe for single-writer / multiple-reader async usage.
    """

    settings: HistorySettings = field(default_factory=HistorySettings)
    _entries: deque[HistoryEntry] = field(default=None, repr=False)
    _bookmarks: list[HistoryEntry] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self._entries is None:
            self._entries = deque(maxlen=self.settings.max_entries)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, scene: Scene, spoken_text: str, *, mode: str = "explore") -> HistoryEntry:
        """Record a new scene description."""
        entry = HistoryEntry(scene=scene, spoken_text=spoken_text, mode=mode)
        self._entries.append(entry)
        logger.debug("History entry added (%d total)", len(self._entries))
        return entry

    def bookmark_last(self) -> HistoryEntry | None:
        """Bookmark the most recent entry (user said 'remember this')."""
        if not self._entries:
            return None
        entry = self._entries[-1]
        if entry.bookmarked:
            return entry
        entry.bookmarked = True
        if len(self._bookmarks) < self.settings.max_bookmarks:
            self._bookmarks.append(entry)
            logger.info("Scene bookmarked (%d total)", len(self._bookmarks))
        else:
            logger.warning("Bookmark limit reached (%d)", self.settings.max_bookmarks)
        return entry

    @property
    def last(self) -> HistoryEntry | None:
        """Most recent entry, or None."""
        return self._entries[-1] if self._entries else None

    @property
    def last_description(self) -> str:
        """Text that was spoken for the most recent scene."""
        return self._entries[-1].spoken_text if self._entries else ""

    @property
    def entries(self) -> list[HistoryEntry]:
        """All entries, newest last."""
        return list(self._entries)

    @property
    def bookmarks(self) -> list[HistoryEntry]:
        """All bookmarked entries."""
        return list(self._bookmarks)

    def recent(self, n: int = 5) -> list[HistoryEntry]:
        """Return the *n* most recent entries (newest last)."""
        items = list(self._entries)
        return items[-n:]

    def clear(self) -> None:
        """Wipe the rolling history (keeps bookmarks)."""
        self._entries.clear()
        logger.info("History cleared (bookmarks preserved)")

    def __len__(self) -> int:
        return len(self._entries)
