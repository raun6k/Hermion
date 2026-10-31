"""Turn-taking rules: how long to wait after the customer's last words, and whether VAD speech is a
real interruption. Pure functions. Spec: docs/voice.md#turn-taking."""

import re

# Words that usually mean the customer is not done ("and", "but", "toh", "aur", ...).
CONNECTORS = frozenset(
    {"and", "but", "or", "so", "because", "if", "with", "for", "to", "the", "a", "toh", "aur",
     "lekin", "magar", "ki", "par", "mein", "ka", "ke", "kya"}
)  # fmt: skip
_TOKEN = re.compile(r"\w+", re.UNICODE)
_SENTENCE_END = re.compile(r"[.!?।？]\s*$")

# Sarvam's first partial lands ~1 s after VAD speech_start, so a shorter window misses real interruptions.
BARGE_IN_WINDOW_S = 1.5
BARGE_IN_MIN_TOKENS = 2


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text)


def endpoint_delay_ms(text: str, base_ms: int, short_ms: int, long_ms: int) -> int:
    """Wait longer when the thought looks unfinished (mid-clause, connector or trailing number), shorter
    after a complete sentence or question. `base_ms == 0` disables waiting (tests)."""
    if base_ms == 0:
        return 0
    words = tokens(text)
    if not words:
        return base_ms
    last = words[-1].lower()
    # Checked before punctuation: STT often ends every final with a full stop ("a shirt and.").
    if last in CONNECTORS or last.isdigit():
        return long_ms
    if _SENTENCE_END.search(text.strip()):
        return short_ms
    return base_ms


class BargeInGate:
    """VAD speech only counts as an interruption if a partial transcript with real words follows quickly.
    Noise never stops Hermion, and neither does a single-token transcript."""

    def __init__(self, window_s: float = BARGE_IN_WINDOW_S, min_tokens: int = BARGE_IN_MIN_TOKENS) -> None:
        self._window, self._min = window_s, min_tokens
        self._started: float | None = None

    def start(self, now: float) -> None:
        self._started = now

    def end(self) -> None:
        self._started = None

    def partial(self, text: str, now: float) -> bool:
        """True once per speech start, when this partial confirms a real interruption."""
        if self._started is None or now - self._started > self._window:
            return False
        if len(tokens(text)) < self._min:
            return False
        self._started = None
        return True
