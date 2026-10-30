"""Live checks against real external services (costs a few credits).

Run: `make smoke [LANGS="kn-IN ta-IN"]` (or `uv run python -m scripts.smoke [code ...]`). Ignores USE_FAKE_*.
1. OpenRouter: one chat call to LLM_MODEL.
2. Per language (default: every language in SARVAM_TTS_SPEAKERS, else te-IN):
   Sarvam TTS (bulbul:v4-flash) sample + "₹850" -> scripts/out/smoke_<code>.wav (16 kHz), then
   Sarvam STT (saaras:v3-realtime, auto-detect) on that WAV -> transcript; detected language must match.
"""

import asyncio
import os
import sys
import wave
from pathlib import Path

from app import languages
from app.agent.llm_client import OpenRouterClient
from app.agent.loop import SKELETON_SYSTEM_PROMPT
from app.config import Settings
from app.speech.stt import SarvamRealtimeSTT
from app.speech.tts import SarvamTTS

OUT = Path(__file__).parent / "out"


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

    codes = sys.argv[1:] or list(settings.sarvam_tts_speakers) or ["te-IN"]
    OUT.mkdir(exist_ok=True)
    for code in codes:
        try:
            lang = languages.require(code)
            wav_path = OUT / f"smoke_{code}.wav"
            wav_path.write_bytes(await SarvamTTS(settings).synthesize(f"{lang.sample} ₹850.", code, 16_000))
            with wave.open(str(wav_path)) as w:
                seconds = w.getnframes() / w.getframerate()
                pcm = w.readframes(w.getnframes())
            t = await SarvamRealtimeSTT(settings).transcribe_pcm(pcm)
            ok = t.language == code
            failed |= not ok
            status = "OK  " if ok else "FAIL"
            print(f"{status} {code} tts {seconds:.1f}s -> stt language={t.language} text={t.text!r}")
        except Exception as exc:
            failed = True
            print(f"FAIL {code}: {exc}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
