"""SightEngine — the main orchestrator for Atlas Sight."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from atlas_sight.config import ContentType, Mode, SightConfig, Verbosity
from atlas_sight.core.context import ContextTracker
from atlas_sight.core.scene import SceneAnalyzer
from atlas_sight.data.history import SessionHistory
from atlas_sight.data.models import Gesture, GestureType, Obstacle, VoiceCommand

if TYPE_CHECKING:
    from atlas_sight.interaction.audio_cues import AudioCues
    from atlas_sight.interaction.gestures import GestureHandler
    from atlas_sight.interaction.haptics import HapticFeedback
    from atlas_sight.modes.emergency import EmergencyMode
    from atlas_sight.modes.explore import ExploreMode
    from atlas_sight.modes.identify import IdentifyMode
    from atlas_sight.modes.navigate import NavigateMode
    from atlas_sight.modes.read import ReadMode
    from atlas_sight.navigation.obstacle import ObstacleWarner
    from atlas_sight.navigation.orientation import OrientationHelper
    from atlas_sight.vision.camera import CameraManager
    from atlas_sight.vision.detector import ObjectDetector
    from atlas_sight.vision.ocr import TextReader
    from atlas_sight.vision.vlm import VisionLM
    from atlas_sight.voice.commands import CommandParser
    from atlas_sight.voice.listener import VoiceListener
    from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)

# Mode cycle order (emergency is excluded — activated explicitly)
_CYCLEABLE_MODES: list[Mode] = [
    Mode.EXPLORE,
    Mode.READ,
    Mode.NAVIGATE,
    Mode.IDENTIFY,
]


class SightEngine:
    """Main orchestrator that ties every Atlas Sight subsystem together.

    This is the brain of the accessibility assistant.  Every voice command
    and gesture flows through here, gets routed to the right handler, and
    results in spoken output the user can hear.

    **Design principle:** a blind person cannot see stack traces.  Every
    public method catches exceptions and speaks a human-friendly error
    message so the user is never left in silence.
    """

    def __init__(self, config: SightConfig | None = None) -> None:
        self._config = config or SightConfig()
        self._running = False

        # Subsystem references (populated in _init_subsystems)
        self._camera: CameraManager | None = None
        self._vlm: VisionLM | None = None
        self._ocr: TextReader | None = None
        self._detector: ObjectDetector | None = None
        self._speaker: Speaker | None = None
        self._listener: VoiceListener | None = None
        self._command_parser: CommandParser | None = None
        self._gesture_handler: GestureHandler | None = None
        self._haptics: HapticFeedback | None = None
        self._audio_cues: AudioCues | None = None
        self._orientation: OrientationHelper | None = None
        self._obstacle_warner: ObstacleWarner | None = None

        # Core orchestration components
        self._history: SessionHistory | None = None
        self._context: ContextTracker | None = None
        self._scene_analyzer: SceneAnalyzer | None = None

        # Modes
        self._modes: dict[Mode, ExploreMode | ReadMode | NavigateMode | IdentifyMode | EmergencyMode] = {}
        self._current_mode: ExploreMode | ReadMode | NavigateMode | IdentifyMode | EmergencyMode | None = None
        self._current_mode_enum: Mode = self._config.initial_mode

    # ==================================================================
    # Lifecycle
    # ==================================================================

    async def start(self) -> None:
        """Initialise all subsystems, load models, start listeners.

        Announces "Atlas Sight is ready" when everything is up.
        """
        if self._running:
            logger.warning("Engine already running")
            return

        logger.info("Starting Atlas Sight engine...")
        try:
            self._config.load_preferences()
            await self._init_subsystems()
            self._setup_callbacks()
            self._running = True

            await self._listener.start()

            await self._play_cue("ready")
            await self._speak("Atlas Sight is ready.")
            logger.info(
                "Atlas Sight engine started in %s mode",
                self._current_mode_enum.value,
            )
        except Exception as exc:
            logger.critical("Failed to start engine: %s", exc, exc_info=True)
            if self._speaker:
                try:
                    await self._speak(
                        "Atlas Sight failed to start. Please check the logs."
                    )
                except Exception:
                    pass
            raise

    async def stop(self) -> None:
        """Graceful shutdown — announce, then tear down subsystems."""
        if not self._running:
            return

        logger.info("Shutting down Atlas Sight engine...")
        self._running = False

        try:
            await self._speak("Atlas Sight shutting down.")
        except Exception:
            logger.warning("Could not announce shutdown", exc_info=True)

        # Tear down in reverse-dependency order
        for name, subsystem in [
            ("listener", self._listener),
            ("gesture_handler", self._gesture_handler),
            ("camera", self._camera),
        ]:
            if subsystem is None:
                continue
            try:
                await subsystem.stop()
            except Exception:
                logger.warning("Error stopping %s", name, exc_info=True)

        logger.info("Atlas Sight engine stopped")

    # ==================================================================
    # Public actions — voice / gesture entry points
    # ==================================================================

    async def process_voice(self, command: VoiceCommand) -> None:
        """Route a parsed voice command to the appropriate handler."""
        if not self._running:
            return
        try:
            await self._handle_voice_command(command)
        except Exception as exc:
            logger.error("Voice command failed: %s", exc, exc_info=True)
            await self._speak(
                "Sorry, something went wrong processing that command."
            )

    async def process_gesture(self, gesture: Gesture) -> None:
        """Route a gesture event to the appropriate handler."""
        if not self._running:
            return
        try:
            await self._handle_gesture(gesture)
        except Exception as exc:
            logger.error("Gesture handling failed: %s", exc, exc_info=True)
            await self._speak("Sorry, I couldn't process that gesture.")

    # ==================================================================
    # Public actions — scene & navigation
    # ==================================================================

    async def describe_scene(self, detail_level: Verbosity | None = None) -> None:
        """Capture → analyse → speak a scene description."""
        verbosity = detail_level or self._config.verbosity

        image = await self._capture()
        if image is None:
            await self._speak("I can't access the camera right now.")
            return

        context = self._context.get_context_prompt()
        scene = await self._scene_analyzer.analyze(
            image, verbosity=verbosity, context=context,
        )

        # Safety first — warn about obstacles before the description
        if scene.has_obstacles:
            warnings = self._format_obstacle_warnings(scene.obstacles)
            await self._play_cue("warning")
            await self._speak(warnings, ContentType.NAVIGATION)

        # Avoid boring the user with identical descriptions
        if self._context.was_recently_described(
            scene.description,
            threshold=self._config.history.dedup_similarity_threshold,
        ):
            scene_text = "The scene hasn't changed much. " + scene.description
        else:
            scene_text = scene.description

        await self._speak(scene_text, ContentType.DESCRIPTION)
        self._context.add(scene, scene_text, mode=self._current_mode_enum.value)

    async def read_text(self) -> None:
        """OCR the current view and speak detected text."""
        image = await self._capture()
        if image is None:
            await self._speak("I can't access the camera right now.")
            return

        text_blocks = await self._scene_analyzer.analyze_text(image)
        if not text_blocks:
            await self._speak("I don't see any text in the current view.")
            return

        # Read top-to-bottom
        sorted_blocks = sorted(
            text_blocks,
            key=lambda b: b.bbox.y_min if b.bbox else 0.0,
        )
        full_text = " ".join(b.text for b in sorted_blocks)
        await self._speak(full_text, ContentType.TEXT_READING)

    async def check_obstacles(self) -> None:
        """Scan for obstacles and warn the user."""
        image = await self._capture()
        if image is None:
            await self._speak("I can't access the camera right now.")
            return

        obstacles = await self._scene_analyzer.analyze_obstacles(image)
        if not obstacles:
            await self._play_cue("clear")
            await self._speak("The path ahead looks clear.", ContentType.NAVIGATION)
            return

        await self._speak(
            self._format_obstacle_warnings(obstacles), ContentType.NAVIGATION,
        )

        danger = [o for o in obstacles if o.is_dangerous]
        if danger:
            await self._play_cue("danger")
            if self._haptics:
                try:
                    await self._haptics.vibrate("danger")
                except Exception:
                    logger.debug("Haptic feedback unavailable", exc_info=True)

    async def emergency_locate(self) -> None:
        """Emergency mode — detailed surroundings for orientation."""
        await self._play_cue("emergency")
        await self._speak(
            "Emergency mode. Scanning your surroundings now.",
            ContentType.ALERT,
        )
        await self.describe_scene(detail_level=Verbosity.DETAILED)

    # ==================================================================
    # Public actions — settings
    # ==================================================================

    async def set_mode(self, mode: Mode) -> None:
        """Switch interaction mode and announce the change."""
        if mode == self._current_mode_enum:
            await self._speak(f"Already in {mode.value} mode.")
            return

        prev = self._current_mode_enum
        self._current_mode_enum = mode
        self._current_mode = self._modes.get(mode)

        await self._play_cue("mode_change")
        await self._speak(f"Switched to {mode.value} mode.")
        logger.info("Mode changed: %s → %s", prev.value, mode.value)

    async def adjust_speed(self, delta: float) -> None:
        """Change TTS speaking speed by *delta*."""
        profile = self._config.voice.speed_profile
        old = profile.preferred
        new_speed = max(
            self._config.voice.min_speed,
            min(self._config.voice.max_speed, old + delta),
        )
        if new_speed == old:
            limit = "fastest" if delta > 0 else "slowest"
            await self._speak(f"Already at {limit} speed.")
            return
        profile.update_preferred(
            new_speed,
            min_speed=self._config.voice.min_speed,
            max_speed=self._config.voice.max_speed,
        )
        self._config.voice.speed = profile.preferred
        if self._speaker:
            self._speaker.set_speed(profile.preferred)
        self._config.save_preferences()
        await self._speak(f"Speed set to {profile.preferred:.1f}x.")

    async def normal_speed(self) -> None:
        """Reset speech speed to 1.0× (the default for new users)."""
        if self._speaker:
            self._speaker.reset_speed()
            self._config.voice.speed = self._speaker.speed
            self._config.voice.speed_profile.preferred = 1.0
            self._config.save_preferences()
        await self._speak("Speed reset to normal.")

    async def max_speed(self) -> None:
        """Jump to the user's saved maximum speed."""
        if self._speaker:
            self._speaker.go_max_speed()
            self._config.voice.speed = self._speaker.speed
            self._config.save_preferences()
        saved = self._config.voice.speed_profile.saved_max
        await self._speak(f"Speed set to {saved:.1f}x.")

    async def adjust_volume(self, delta: float) -> None:
        """Change TTS volume by *delta*."""
        voice = self._config.voice
        new_volume = max(0.0, min(1.0, voice.volume + delta))
        if new_volume == voice.volume:
            limit = "maximum" if delta > 0 else "minimum"
            await self._speak(f"Already at {limit} volume.")
            return
        voice.volume = new_volume
        if self._speaker:
            self._speaker.set_volume(new_volume)
        self._config.save_preferences()
        await self._speak(f"Volume set to {int(new_volume * 100)} percent.")

    async def set_verbosity(self, verbosity: Verbosity) -> None:
        """Change how much detail descriptions include."""
        self._config.verbosity = verbosity
        await self._speak(f"Detail level set to {verbosity.value}.")

    async def remember_scene(self) -> None:
        """Bookmark the current scene so the user can revisit it."""
        entry = self._history.bookmark_last()
        if entry:
            await self._play_cue("bookmark")
            await self._speak("Scene bookmarked.")
        else:
            await self._speak(
                "Nothing to bookmark yet.  Describe a scene first."
            )

    async def repeat_last(self) -> None:
        """Repeat the last spoken description."""
        last = self._context.last_description
        if last:
            await self._speak(last)
        else:
            await self._speak("Nothing to repeat yet.")

    # ==================================================================
    # Private — initialisation
    # ==================================================================

    async def _init_subsystems(self) -> None:
        """Create every component instance and load ML models."""
        # Runtime imports keep the module importable even when subsystem
        # packages are not yet installed or fully implemented.
        from atlas_sight.interaction.audio_cues import AudioCues
        from atlas_sight.interaction.gestures import GestureHandler
        from atlas_sight.interaction.haptics import HapticFeedback
        from atlas_sight.modes.emergency import EmergencyMode
        from atlas_sight.modes.explore import ExploreMode
        from atlas_sight.modes.identify import IdentifyMode
        from atlas_sight.modes.navigate import NavigateMode
        from atlas_sight.modes.read import ReadMode
        from atlas_sight.navigation.obstacle import ObstacleWarner
        from atlas_sight.navigation.orientation import OrientationHelper
        from atlas_sight.vision.camera import CameraManager
        from atlas_sight.vision.detector import ObjectDetector
        from atlas_sight.vision.ocr import TextReader
        from atlas_sight.vision.vlm import VisionLM
        from atlas_sight.voice.commands import CommandParser
        from atlas_sight.voice.listener import VoiceListener
        from atlas_sight.voice.speaker import Speaker

        cfg = self._config

        # -- Vision --
        self._camera = CameraManager(cfg.vision)
        self._vlm = VisionLM(cfg.vision)
        self._ocr = TextReader(cfg.vision)
        self._detector = ObjectDetector(cfg.vision)

        # -- Voice --
        self._speaker = Speaker(cfg.voice)
        self._listener = VoiceListener(cfg.voice)
        self._command_parser = CommandParser()

        # -- Interaction --
        self._gesture_handler = GestureHandler()
        self._haptics = HapticFeedback()
        self._audio_cues = AudioCues(cfg.audio_cues)

        # -- Navigation --
        self._orientation = OrientationHelper()
        self._obstacle_warner = ObstacleWarner(cfg.navigation)

        # -- Core orchestration --
        self._history = SessionHistory(cfg.history)
        self._context = ContextTracker(self._history)
        self._scene_analyzer = SceneAnalyzer(
            vlm=self._vlm,
            ocr=self._ocr,
            detector=self._detector,
            obstacle_warner=self._obstacle_warner,
        )

        # -- Interaction modes --
        self._modes = {
            Mode.EXPLORE: ExploreMode(self._scene_analyzer, self._speaker),
            Mode.READ: ReadMode(self._ocr, self._speaker),
            Mode.NAVIGATE: NavigateMode(
                self._orientation, self._obstacle_warner, self._speaker,
            ),
            Mode.IDENTIFY: IdentifyMode(self._vlm, self._speaker),
            Mode.EMERGENCY: EmergencyMode(
                self._scene_analyzer, self._speaker, self._orientation,
            ),
        }
        self._current_mode = self._modes.get(self._current_mode_enum)

        # Load ML models concurrently (don't let one slow model block others)
        results = await asyncio.gather(
            self._vlm.load(),
            self._ocr.load(),
            self._detector.load(),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                model_name = ("VLM", "OCR", "detector")[i]
                logger.error("Failed to load %s model: %s", model_name, result)

        await self._camera.start()

    def _setup_callbacks(self) -> None:
        """Wire voice listener and gesture handler to our dispatch methods."""
        self._listener.on_command = self._on_voice_command
        self._gesture_handler.on_gesture = self._on_gesture

    # ==================================================================
    # Private — sync callback wrappers
    # ==================================================================

    def _on_voice_command(self, command: VoiceCommand) -> None:
        """Sync callback from the voice listener — schedules async handler."""
        asyncio.ensure_future(self.process_voice(command))

    def _on_gesture(self, gesture: Gesture) -> None:
        """Sync callback from the gesture handler — schedules async handler."""
        asyncio.ensure_future(self.process_gesture(gesture))

    # ==================================================================
    # Private — command dispatch
    # ==================================================================

    async def _handle_voice_command(self, command: VoiceCommand) -> None:
        """Big dispatch switch — maps voice intents to engine methods."""
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
        )

        intent = command.intent
        logger.info(
            "Voice command: %r (intent=%s, confidence=%.2f)",
            command.raw_text,
            intent,
            command.confidence,
        )

        dispatch: dict[str, object] = {
            DESCRIBE: lambda: self.describe_scene(),
            READ_TEXT: lambda: self.read_text(),
            CHECK_AHEAD: lambda: self.check_obstacles(),
            LOCATE: lambda: self.emergency_locate(),
            IDENTIFY: lambda: self.describe_scene(detail_level=Verbosity.DETAILED),
            NAVIGATE: lambda: self.set_mode(Mode.NAVIGATE),
            LOUDER: lambda: self.adjust_volume(self._config.voice.volume_step),
            SOFTER: lambda: self.adjust_volume(-self._config.voice.volume_step),
            FASTER: lambda: self.adjust_speed(self._config.voice.speed_step),
            SLOWER: lambda: self.adjust_speed(-self._config.voice.speed_step),
            NORMAL_SPEED: lambda: self.normal_speed(),
            MAX_SPEED: lambda: self.max_speed(),
            MORE_DETAIL: lambda: self.set_verbosity(Verbosity.DETAILED),
            LESS_DETAIL: lambda: self.set_verbosity(Verbosity.BRIEF),
            REMEMBER: lambda: self.remember_scene(),
            REPEAT: lambda: self.repeat_last(),
            STOP: lambda: self._speak("Okay, stopping."),
            HELP: lambda: self._speak_help(),
        }

        handler = dispatch.get(intent)
        if handler is not None:
            await handler()
        elif intent == UNKNOWN:
            await self._speak(
                "I didn't understand that. Say 'help' for available commands."
            )
        else:
            logger.warning("Unhandled voice intent: %s", intent)
            await self._speak("I'm not sure how to handle that yet.")

    async def _handle_gesture(self, gesture: Gesture) -> None:
        """Map gesture types to engine actions."""
        logger.info("Gesture: %s", gesture.gesture_type.value)

        gesture_map: dict[GestureType, object] = {
            GestureType.DOUBLE_TAP: lambda: self.describe_scene(),
            GestureType.SWIPE_RIGHT: lambda: self.set_mode(self._next_mode(1)),
            GestureType.SWIPE_LEFT: lambda: self.set_mode(self._next_mode(-1)),
            GestureType.SWIPE_UP: lambda: self.adjust_volume(
                self._config.voice.volume_step,
            ),
            GestureType.SWIPE_DOWN: lambda: self.adjust_volume(
                -self._config.voice.volume_step,
            ),
            GestureType.SHAKE: lambda: self.emergency_locate(),
            GestureType.LONG_PRESS: lambda: self.read_text(),
            GestureType.TWO_FINGER_TAP: lambda: self.check_obstacles(),
        }

        handler = gesture_map.get(gesture.gesture_type)
        if handler is not None:
            await handler()
        else:
            logger.debug("Unmapped gesture: %s", gesture.gesture_type.value)

    # ==================================================================
    # Private — helpers
    # ==================================================================

    async def _capture(self) -> bytes | None:
        """Capture a single frame from the camera."""
        try:
            return await self._camera.capture()
        except Exception:
            logger.error("Camera capture failed", exc_info=True)
            return None

    async def _speak(
        self,
        text: str,
        content_type: ContentType = ContentType.GENERAL,
    ) -> None:
        """Speak *text* to the user via TTS.  Never raises."""
        if not text or self._speaker is None:
            return
        try:
            await self._speaker.say(text, content_type=content_type)
        except Exception:
            # Last resort — log it.  We can't speak the error about speaking.
            logger.error("TTS failed for: %s", text[:80], exc_info=True)

    async def _play_cue(self, cue_name: str) -> None:
        """Play an audio cue if the subsystem is available."""
        if self._audio_cues is None:
            return
        try:
            await self._audio_cues.play(cue_name)
        except Exception:
            logger.debug("Audio cue %r unavailable", cue_name, exc_info=True)

    async def _speak_help(self) -> None:
        """Speak the list of available voice commands."""
        await self._speak(
            "Available commands: "
            "describe scene, read text, check ahead, "
            "louder, softer, faster, slower, "
            "normal speed, max speed, "
            "more detail, less detail, "
            "remember this, repeat, "
            "identify, navigate, help."
        )

    def _next_mode(self, direction: int) -> Mode:
        """Cycle through non-emergency modes."""
        try:
            idx = _CYCLEABLE_MODES.index(self._current_mode_enum)
        except ValueError:
            idx = 0
        return _CYCLEABLE_MODES[(idx + direction) % len(_CYCLEABLE_MODES)]

    @staticmethod
    def _format_obstacle_warnings(obstacles: list[Obstacle]) -> str:
        """Format obstacles into a spoken warning string.

        Dangerous obstacles are announced first, then sorted by distance.
        """
        if not obstacles:
            return "Path is clear."

        sorted_obs = sorted(
            obstacles,
            key=lambda o: (0 if o.is_dangerous else 1, o.distance_m),
        )

        parts: list[str] = []
        for obs in sorted_obs:
            if obs.distance_m >= 1.0:
                distance = f"{obs.distance_m:.1f} meters"
            else:
                distance = f"{int(obs.distance_m * 100)} centimeters"

            if obs.is_dangerous:
                parts.append(
                    f"Warning! {obs.label} {distance} ahead, {obs.direction}."
                )
            else:
                parts.append(
                    f"{obs.label} {distance} ahead, {obs.direction}."
                )

        return " ".join(parts)
