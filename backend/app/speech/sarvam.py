"""Low-level Sarvam WebSocket helpers shared by stt.py and tts.py. Spec: docs/voice.md.

Server message envelopes are not fully documented, so parsing is tolerant: the event name may be
under "type" or "event", and payload fields may be top-level or under "data".
"""

import json
from typing import Any

SARVAM_WS = "wss://api.sarvam.ai"
AUTH_HEADER = "api-subscription-key"


class SarvamError(Exception):
    pass


def event_name(msg: dict[str, Any]) -> str:
    return str(msg.get("type") or msg.get("event") or "")


def payload(msg: dict[str, Any]) -> dict[str, Any]:
    data = msg.get("data")
    return data if isinstance(data, dict) else msg


def parse(raw: str | bytes) -> dict[str, Any]:
    msg = json.loads(raw)
    if not isinstance(msg, dict):
        raise SarvamError(f"unexpected message: {raw!r:.200}")
    return msg
