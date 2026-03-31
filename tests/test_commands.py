"""Tests for atlas_sight.voice.commands.CommandParser."""
from __future__ import annotations

import pytest

from atlas_sight.voice.commands import (
    CHECK_AHEAD,
    DESCRIBE,
    FASTER,
    HELP,
    IDENTIFY,
    LESS_DETAIL,
    LOCATE,
    LOUDER,
    MAX_SPEED,
    MORE_DETAIL,
    NAVIGATE,
    NORMAL_SPEED,
    READ_TEXT,
    REMEMBER,
    REPEAT,
    SLOWER,
    SOFTER,
    STOP,
    UNKNOWN,
    CommandParser,
)


@pytest.fixture()
def parser() -> CommandParser:
    return CommandParser()


# ---------------------------------------------------------------------------
# Describe
# ---------------------------------------------------------------------------


class TestDescribeIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("describe").intent == DESCRIBE

    def test_what_do_you_see(self, parser: CommandParser):
        assert parser.parse("what do you see").intent == DESCRIBE

    def test_look_around(self, parser: CommandParser):
        assert parser.parse("look around").intent == DESCRIBE

    def test_whats_around_me(self, parser: CommandParser):
        assert parser.parse("what's around me").intent == DESCRIBE

    def test_describe_the_scene(self, parser: CommandParser):
        assert parser.parse("describe the scene").intent == DESCRIBE

    def test_surroundings(self, parser: CommandParser):
        assert parser.parse("surroundings").intent == DESCRIBE


# ---------------------------------------------------------------------------
# Read text
# ---------------------------------------------------------------------------


class TestReadTextIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("read").intent == READ_TEXT

    def test_read_the_text(self, parser: CommandParser):
        assert parser.parse("read the text").intent == READ_TEXT

    def test_what_does_it_say(self, parser: CommandParser):
        assert parser.parse("what does it say").intent == READ_TEXT

    def test_read_the_sign(self, parser: CommandParser):
        assert parser.parse("read the sign").intent == READ_TEXT


# ---------------------------------------------------------------------------
# Locate
# ---------------------------------------------------------------------------


class TestLocateIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("location").intent == LOCATE

    def test_where_am_i(self, parser: CommandParser):
        assert parser.parse("where am i").intent == LOCATE

    def test_whats_my_location(self, parser: CommandParser):
        assert parser.parse("what's my location").intent == LOCATE


# ---------------------------------------------------------------------------
# Check ahead
# ---------------------------------------------------------------------------


class TestCheckAheadIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("check ahead").intent == CHECK_AHEAD

    def test_obstacles(self, parser: CommandParser):
        assert parser.parse("obstacles").intent == CHECK_AHEAD

    def test_is_the_path_clear(self, parser: CommandParser):
        assert parser.parse("is the path clear").intent == CHECK_AHEAD

    def test_whats_ahead(self, parser: CommandParser):
        assert parser.parse("what's ahead").intent == CHECK_AHEAD


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelpIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("help").intent == HELP

    def test_emergency(self, parser: CommandParser):
        assert parser.parse("emergency").intent == HELP

    def test_sos(self, parser: CommandParser):
        assert parser.parse("sos").intent == HELP

    def test_i_need_help(self, parser: CommandParser):
        assert parser.parse("i need help").intent == HELP


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------


class TestVolumeIntents:
    def test_louder(self, parser: CommandParser):
        assert parser.parse("louder").intent == LOUDER

    def test_volume_up(self, parser: CommandParser):
        assert parser.parse("volume up").intent == LOUDER

    def test_speak_louder(self, parser: CommandParser):
        assert parser.parse("speak louder").intent == LOUDER

    def test_softer(self, parser: CommandParser):
        assert parser.parse("softer").intent == SOFTER

    def test_volume_down(self, parser: CommandParser):
        assert parser.parse("volume down").intent == SOFTER

    def test_quieter(self, parser: CommandParser):
        assert parser.parse("quieter").intent == SOFTER


# ---------------------------------------------------------------------------
# Speed
# ---------------------------------------------------------------------------


class TestSpeedIntents:
    def test_slower(self, parser: CommandParser):
        assert parser.parse("slower").intent == SLOWER

    def test_slow_down(self, parser: CommandParser):
        assert parser.parse("slow down").intent == SLOWER

    def test_faster(self, parser: CommandParser):
        assert parser.parse("faster").intent == FASTER

    def test_speed_up(self, parser: CommandParser):
        assert parser.parse("speed up").intent == FASTER

    def test_hurry_up(self, parser: CommandParser):
        assert parser.parse("hurry up").intent == FASTER


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


class TestDetailIntents:
    def test_more_detail(self, parser: CommandParser):
        assert parser.parse("more detail").intent == MORE_DETAIL

    def test_elaborate(self, parser: CommandParser):
        assert parser.parse("elaborate").intent == MORE_DETAIL

    def test_tell_me_more(self, parser: CommandParser):
        assert parser.parse("tell me more").intent == MORE_DETAIL

    def test_less_detail(self, parser: CommandParser):
        assert parser.parse("less detail").intent == LESS_DETAIL

    def test_brief(self, parser: CommandParser):
        assert parser.parse("brief").intent == LESS_DETAIL

    def test_summarize(self, parser: CommandParser):
        assert parser.parse("summarize").intent == LESS_DETAIL


# ---------------------------------------------------------------------------
# Remember / Stop / Identify / Navigate / Repeat
# ---------------------------------------------------------------------------


class TestOtherIntents:
    def test_remember(self, parser: CommandParser):
        assert parser.parse("remember this").intent == REMEMBER

    def test_bookmark(self, parser: CommandParser):
        assert parser.parse("bookmark").intent == REMEMBER

    def test_stop(self, parser: CommandParser):
        assert parser.parse("stop").intent == STOP

    def test_be_quiet(self, parser: CommandParser):
        assert parser.parse("be quiet").intent == STOP

    def test_identify(self, parser: CommandParser):
        assert parser.parse("identify").intent == IDENTIFY

    def test_what_is_this(self, parser: CommandParser):
        assert parser.parse("what is this").intent == IDENTIFY

    def test_navigate(self, parser: CommandParser):
        assert parser.parse("navigate").intent == NAVIGATE

    def test_guide_me(self, parser: CommandParser):
        assert parser.parse("guide me").intent == NAVIGATE

    def test_repeat(self, parser: CommandParser):
        assert parser.parse("repeat").intent == REPEAT

    def test_say_again(self, parser: CommandParser):
        assert parser.parse("say again").intent == REPEAT


# ---------------------------------------------------------------------------
# Unknown
# ---------------------------------------------------------------------------


class TestUnknownIntent:
    def test_gibberish(self, parser: CommandParser):
        cmd = parser.parse("xyzzy foobar baz")
        assert cmd.intent == UNKNOWN
        assert cmd.confidence == 0.0

    def test_empty_string(self, parser: CommandParser):
        cmd = parser.parse("")
        assert cmd.intent == UNKNOWN
        assert cmd.confidence == 0.0

    def test_whitespace_only(self, parser: CommandParser):
        cmd = parser.parse("   ")
        assert cmd.intent == UNKNOWN
        assert cmd.confidence == 0.0


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    def test_upper(self, parser: CommandParser):
        assert parser.parse("DESCRIBE").intent == DESCRIBE

    def test_mixed(self, parser: CommandParser):
        assert parser.parse("What Do You See").intent == DESCRIBE

    def test_read_upper(self, parser: CommandParser):
        assert parser.parse("READ THE TEXT").intent == READ_TEXT


# ---------------------------------------------------------------------------
# Parameter extraction
# ---------------------------------------------------------------------------


class TestParameterExtraction:
    def test_volume_percentage(self, parser: CommandParser):
        cmd = parser.parse("set volume to 80")
        assert cmd.intent == LOUDER
        assert cmd.parameters.get("value") == pytest.approx(0.8)

    def test_speed_value(self, parser: CommandParser):
        cmd = parser.parse("set speed to 1.5")
        assert cmd.intent == SLOWER
        assert cmd.parameters.get("value") == pytest.approx(1.5)

    def test_navigate_destination(self, parser: CommandParser):
        cmd = parser.parse("navigate to the grocery store")
        assert cmd.intent == NAVIGATE
        assert cmd.parameters.get("destination") == "the grocery store"

    def test_navigate_no_destination(self, parser: CommandParser):
        cmd = parser.parse("navigate")
        assert cmd.intent == NAVIGATE
        assert "destination" not in cmd.parameters


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------


class TestConfidenceLevels:
    def test_exact_match_confidence(self, parser: CommandParser):
        cmd = parser.parse("describe")
        assert cmd.confidence == 1.0

    def test_starts_with_confidence(self, parser: CommandParser):
        cmd = parser.parse("describe now please")
        assert cmd.confidence == 0.9

    def test_contains_confidence(self, parser: CommandParser):
        cmd = parser.parse("can you please describe what you see")
        assert cmd.confidence == 0.7


# ---------------------------------------------------------------------------
# Normal speed / Max speed
# ---------------------------------------------------------------------------


class TestNormalSpeedIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("normal speed").intent == NORMAL_SPEED

    def test_reset_speed(self, parser: CommandParser):
        assert parser.parse("reset speed").intent == NORMAL_SPEED

    def test_default_speed(self, parser: CommandParser):
        assert parser.parse("default speed").intent == NORMAL_SPEED

    def test_go_back_to_normal(self, parser: CommandParser):
        assert parser.parse("go back to normal speed").intent == NORMAL_SPEED

    def test_case_insensitive(self, parser: CommandParser):
        assert parser.parse("Normal Speed").intent == NORMAL_SPEED


class TestMaxSpeedIntent:
    def test_exact(self, parser: CommandParser):
        assert parser.parse("max speed").intent == MAX_SPEED

    def test_maximum_speed(self, parser: CommandParser):
        assert parser.parse("maximum speed").intent == MAX_SPEED

    def test_full_speed(self, parser: CommandParser):
        assert parser.parse("full speed").intent == MAX_SPEED

    def test_fastest_speed(self, parser: CommandParser):
        assert parser.parse("fastest speed").intent == MAX_SPEED

    def test_go_to_max(self, parser: CommandParser):
        assert parser.parse("go to max speed").intent == MAX_SPEED
