"""Live checks against real external services (costs a few credits).

Run: `make smoke` (or `uv run python -m scripts.smoke`). Ignores USE_FAKE_* flags.
1. OpenRouter: one chat call to LLM_MODEL.
2. Sarvam TTS (bulbul:v4-flash): Telugu sentence -> scripts/out/smoke_te.wav (16 kHz).
3. Sarvam STT (saaras:v3-realtime): that WAV -> transcript + detected language.
"""

import asyncio
import os
import sys
import wave
from pathlib import Path

from app.agent.llm_client import OpenRouterClient
from app.agent.loop import SKELETON_SYSTEM_PROMPT
from app.config import Settings
from app.speech.stt import SarvamRealtimeSTT
from app.speech.tts import SarvamTTS

OUT = Path(__file__).parent / "out"
TELUGU = "నమస్కారం, ఈ చొక్కా ధర ₹850."


async def main() -> int:
    os.environ["USE_FAKE_LLM"] = os.environ["USE_FAKE_SPEECH"] = "false"
    try:
        settings = Settings()
    except Exception as exc:
        print(f"FAIL config: {exc}")
        return 1
    failed = False

    try:
        resp = await OpenRouterClient(settings).complete(
            [{"role": "system", "content": SKELETON_SYSTEM_PROMPT}, {"role": "user", "content": "Namaskaram"}]
        )
        print(f"OK   openrouter model={resp.model} latency_ms={resp.latency_ms} reply={resp.text!r}")
    except Exception as exc:
        failed = True
        print(f"FAIL openrouter: {exc}")

    wav_path = OUT / "smoke_te.wav"
    try:
        OUT.mkdir(exist_ok=True)
        wav_path.write_bytes(await SarvamTTS(settings).synthesize(TELUGU, "te-IN", sample_rate=16_000))
        with wave.open(str(wav_path)) as w:
            print(f"OK   sarvam tts -> {wav_path} ({w.getnframes() / w.getframerate():.1f}s)")
    except Exception as exc:
        failed = True
        print(f"FAIL sarvam tts: {exc}")

    if wav_path.exists():
        try:
            with wave.open(str(wav_path)) as w:
                pcm = w.readframes(w.getnframes())
            t = await SarvamRealtimeSTT(settings).transcribe_pcm(pcm)
            print(f"OK   sarvam stt language={t.language} text={t.text!r}")
        except Exception as exc:
            failed = True
            print(f"FAIL sarvam stt: {exc}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
