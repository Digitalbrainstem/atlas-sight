"""ContextTracker — tracks what we described to avoid repetition."""
from __future__ import annotations

import logging

from atlas_sight.data.history import SessionHistory
from atlas_sight.data.models import HistoryEntry, Scene

logger = logging.getLogger(__name__)


class ContextTracker:
    """Tracks recently described scenes to avoid repetitive descriptions.

    Uses simple word-overlap similarity (Jaccard) to detect when a scene
    description is too similar to what we recently told the user.  No ML
    needed — just set intersection on lowercased word tokens.
    """

    def __init__(self, history: SessionHistory) -> None:
        self._history = history

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def was_recently_described(
        self,
        description: str,
        threshold: float = 0.8,
    ) -> bool:
        """Return *True* if a similar description was given in the last few entries.

        Parameters
        ----------
        description:
            The candidate description text.
        threshold:
            Jaccard similarity cutoff (0.0–1.0). Anything at or above
            this value is considered "already said".
        """
        for entry in self._history.recent(5):
            if self._similarity(description, entry.spoken_text) >= threshold:
                return True
        return False

    def add(
        self,
        scene: Scene,
        spoken_text: str,
        mode: str = "explore",
    ) -> HistoryEntry:
        """Record what we just described.

        Delegates to :pyclass:`SessionHistory` so the rolling window and
        bookmark system stay in sync.
        """
        return self._history.add(scene, spoken_text, mode=mode)

    def get_context_prompt(self) -> str:
        """Build a short context string to prepend to the VLM prompt.

        Returns something like::

            Previously described: A person crossing the street. |
            Two parked cars on the left.

        Giving the VLM this context helps it focus on what is *new* or
        *changed* since the last capture.  Returns an empty string when
        there is no history yet.
        """
        recent = self._history.recent(3)
        if not recent:
            return ""

        summaries: list[str] = []
        for entry in recent:
            text = entry.spoken_text
            if len(text) > 80:
                text = text[:77] + "..."
            summaries.append(text)
        return "Previously described: " + " | ".join(summaries)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def last_description(self) -> str:
        """The most recently spoken description, or ``""``."""
        return self._history.last_description

    @property
    def recent_descriptions(self) -> list[str]:
        """Up to the last 5 spoken descriptions, newest last."""
        return [entry.spoken_text for entry in self._history.recent(5)]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Jaccard similarity on lowercased word sets.

        Returns 0.0 when either string is empty, 1.0 for identical bags
        of words.  Cheap enough to run in a tight loop over a handful of
        history entries.
        """
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)
