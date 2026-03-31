"""Command parser — map natural language to structured voice commands."""
from __future__ import annotations

import logging
import re
import time

from atlas_sight.data.models import VoiceCommand

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent constants
# ---------------------------------------------------------------------------

DESCRIBE = "describe"
READ_TEXT = "read_text"
LOCATE = "locate"
CHECK_AHEAD = "check_ahead"
HELP = "help"
LOUDER = "louder"
SOFTER = "softer"
SLOWER = "slower"
FASTER = "faster"
MORE_DETAIL = "more_detail"
LESS_DETAIL = "less_detail"
REMEMBER = "remember"
STOP = "stop"
IDENTIFY = "identify"
NAVIGATE = "navigate"
REPEAT = "repeat"
NORMAL_SPEED = "normal_speed"
MAX_SPEED = "max_speed"
UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Command patterns
# ---------------------------------------------------------------------------

# Each intent maps to a list of trigger phrases.  Matching is case-insensitive
# and checks whether the user's utterance *starts with* one of the phrases or
# *contains* it as a full substring.
#
# Phrases are tried longest-first so "volume up" doesn't shadow "volume".
# Keep these ordered from most specific → least specific within each list.

COMMAND_PATTERNS: dict[str, list[str]] = {
    DESCRIBE: [
        "what do you see",
        "what can you see",
        "what's around me",
        "what is around me",
        "tell me what's here",
        "tell me what is here",
        "describe the scene",
        "describe what you see",
        "describe this",
        "describe",
        "look around",
        "what's here",
        "what is here",
        "surroundings",
    ],
    READ_TEXT: [
        "read the text",
        "read that text",
        "read the sign",
        "read that sign",
        "read this for me",
        "read that for me",
        "read it to me",
        "read out loud",
        "what does it say",
        "what does that say",
        "what does this say",
        "what does the sign say",
        "read that",
        "read this",
        "read aloud",
        "read",
    ],
    LOCATE: [
        "where am i right now",
        "where am i",
        "what's my location",
        "what is my location",
        "tell me my location",
        "give me my location",
        "current location",
        "my location",
        "location",
    ],
    CHECK_AHEAD: [
        "what's in front of me",
        "what is in front of me",
        "what's ahead of me",
        "what is ahead of me",
        "check for obstacles",
        "any obstacles ahead",
        "any obstacles",
        "is the path clear",
        "is it safe to walk",
        "is it safe ahead",
        "what's ahead",
        "what is ahead",
        "check ahead",
        "obstacles",
        "path check",
    ],
    HELP: [
        "i need help right now",
        "call for help",
        "get help",
        "i need help",
        "i need assistance",
        "help me please",
        "help me",
        "emergency",
        "sos",
        "help",
    ],
    LOUDER: [
        "set the volume to",
        "set volume to",
        "turn the volume up",
        "increase the volume",
        "increase volume",
        "turn volume up",
        "make it louder",
        "volume up",
        "speak louder",
        "speak up",
        "louder please",
        "louder",
        "more volume",
    ],
    SOFTER: [
        "turn the volume down",
        "decrease the volume",
        "decrease volume",
        "turn volume down",
        "make it quieter",
        "make it softer",
        "volume down",
        "speak softer",
        "speak quieter",
        "softer please",
        "quieter please",
        "lower volume",
        "lower the volume",
        "quieter",
        "softer",
    ],
    SLOWER: [
        "set the speed to",
        "set speed to",
        "speak more slowly",
        "speak slower please",
        "slow down please",
        "talk slower",
        "speak slower",
        "slow down",
        "go slower",
        "slower please",
        "slower",
        "not so fast",
    ],
    FASTER: [
        "speak more quickly",
        "speak faster please",
        "speed up please",
        "talk faster",
        "speak faster",
        "speed up",
        "go faster",
        "faster please",
        "faster",
        "hurry up",
        "quicker",
    ],
    MORE_DETAIL: [
        "give me more detail",
        "give me more details",
        "can you elaborate",
        "tell me more about it",
        "tell me more",
        "more detail please",
        "more details please",
        "be more detailed",
        "more information",
        "more detail",
        "more details",
        "elaborate",
        "expand on that",
    ],
    LESS_DETAIL: [
        "give me less detail",
        "keep it short",
        "keep it simple",
        "keep it brief",
        "be more brief",
        "less detail please",
        "be more concise",
        "less information",
        "less detail",
        "less details",
        "brief",
        "shorter",
        "summarize",
        "summary",
    ],
    REMEMBER: [
        "remember this place",
        "remember this location",
        "remember this spot",
        "save this location",
        "save this place",
        "bookmark this",
        "save this",
        "remember this",
        "mark this",
        "bookmark",
    ],
    STOP: [
        "stop talking",
        "stop speaking",
        "please stop",
        "please be quiet",
        "be quiet",
        "shut up",
        "quiet please",
        "silence please",
        "enough",
        "silence",
        "quiet",
        "stop",
        "hush",
    ],
    IDENTIFY: [
        "what is this thing",
        "what's this thing",
        "what am i holding",
        "what am i looking at",
        "what is this object",
        "identify this object",
        "identify this",
        "identify that",
        "what is this",
        "what is that",
        "what's this",
        "what's that",
        "identify",
    ],
    NAVIGATE: [
        "start navigation mode",
        "turn on navigation",
        "navigation mode",
        "navigate me",
        "guide me home",
        "guide me there",
        "guide me to",
        "take me to",
        "guide me",
        "navigate to",
        "navigate",
    ],
    REPEAT: [
        "say that again",
        "repeat that please",
        "what did you say",
        "what was that",
        "can you repeat",
        "come again",
        "repeat that",
        "say again",
        "repeat please",
        "one more time",
        "pardon",
        "repeat",
    ],
    NORMAL_SPEED: [
        "set speed to normal",
        "reset the speed",
        "go back to normal speed",
        "normal speed please",
        "default speed",
        "normal speed",
        "reset speed",
        "regular speed",
        "standard speed",
    ],
    MAX_SPEED: [
        "set speed to maximum",
        "go to max speed",
        "go to maximum speed",
        "maximum speed please",
        "fastest speed",
        "max speed",
        "maximum speed",
        "full speed",
    ],
}

# Pre-compile a lookup sorted by descending phrase length (longest match wins).
_SORTED_PATTERNS: list[tuple[str, str]] = sorted(
    ((phrase.lower(), intent) for intent, phrases in COMMAND_PATTERNS.items() for phrase in phrases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# Regex for extracting a number from text (e.g. "set volume to 80").
_NUMBER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")


# ---------------------------------------------------------------------------
# Parameter extraction helpers
# ---------------------------------------------------------------------------

def _extract_number(text: str) -> float | None:
    """Return the first number found in *text*, or ``None``."""
    m = _NUMBER_RE.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _extract_parameters(text: str, intent: str) -> dict[str, object]:
    """Extract intent-specific parameters from the user's utterance."""
    params: dict[str, object] = {}

    if intent in {LOUDER, SOFTER}:
        num = _extract_number(text)
        if num is not None:
            # Normalise percentage values to 0.0-1.0 range.
            params["value"] = num / 100.0 if num > 1.0 else num

    elif intent in {FASTER, SLOWER}:
        num = _extract_number(text)
        if num is not None:
            params["value"] = num

    elif intent == NAVIGATE:
        # Try to capture a destination after "navigate to" / "guide me to" / "take me to".
        for prefix in ("navigate to ", "guide me to ", "take me to "):
            lower = text.lower()
            idx = lower.find(prefix)
            if idx != -1:
                dest = text[idx + len(prefix) :].strip()
                if dest:
                    params["destination"] = dest
                break

    elif intent == REMEMBER:
        # Anything after the trigger phrase is treated as a label.
        for trigger in ("remember this as ", "save this as ", "bookmark as "):
            lower = text.lower()
            idx = lower.find(trigger)
            if idx != -1:
                label = text[idx + len(trigger) :].strip()
                if label:
                    params["label"] = label
                break

    return params


# ---------------------------------------------------------------------------
# Command parser
# ---------------------------------------------------------------------------

class CommandParser:
    """Fast, offline command parser — no ML, pure pattern matching.

    Usage::

        parser = CommandParser()
        cmd = parser.parse("what do you see")
        assert cmd.intent == "describe"
    """

    def parse(self, text: str) -> VoiceCommand:
        """Parse free-form *text* into a :class:`VoiceCommand`.

        Returns a command with ``intent=UNKNOWN`` when no pattern matches.
        """
        if not text or not text.strip():
            return VoiceCommand(
                raw_text=text or "",
                intent=UNKNOWN,
                confidence=0.0,
                timestamp=time.time(),
            )

        intent, confidence = self._match_pattern(text)
        parameters = _extract_parameters(text, intent)

        cmd = VoiceCommand(
            raw_text=text,
            intent=intent,
            confidence=confidence,
            parameters=parameters,
            timestamp=time.time(),
        )
        logger.debug("Parsed %r → intent=%s conf=%.2f params=%s", text, intent, confidence, parameters)
        return cmd

    # -- Pattern matching ----------------------------------------------------

    @staticmethod
    def _match_pattern(text: str) -> tuple[str, float]:
        """Return ``(intent, confidence)`` for the best-matching pattern.

        Confidence heuristic:
        * 1.0 — the entire utterance *is* a known phrase (exact match).
        * 0.9 — the utterance *starts with* a known phrase.
        * 0.7 — the utterance *contains* a known phrase.
        * Falls back to ``(UNKNOWN, 0.0)`` when nothing matches.
        """
        normalised = text.lower().strip()

        # Pass 1: exact match.
        for phrase, intent in _SORTED_PATTERNS:
            if normalised == phrase:
                return intent, 1.0

        # Pass 2: starts-with match (longest phrase wins).
        for phrase, intent in _SORTED_PATTERNS:
            if normalised.startswith(phrase):
                return intent, 0.9

        # Pass 3: substring / contains match.
        for phrase, intent in _SORTED_PATTERNS:
            if phrase in normalised:
                return intent, 0.7

        return UNKNOWN, 0.0
