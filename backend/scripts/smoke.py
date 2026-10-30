"""Live checks against real external services (costs a few credits).

Run: `make smoke [LANGS="kn-IN ta-IN"]` (or `uv run python -m scripts.smoke [code ...]`). Ignores USE_FAKE_*.
1. OpenRouter: one chat call to LLM_MODEL.
2. Per language (default: every language in SARVAM_TTS_SPEAKERS, else te-IN):
   Sarvam TTS (bulbul:v4-flash) sample + "₹850" -> scripts/out/smoke_<code>.wav (16 kHz), then
   Sarvam STT (saaras:v3-realtime, auto-detect) on that WAV -> transcript; detected language must match.
3. Streaming: per-sentence TTS stream -> live STT session (partial/final/VAD callbacks) -> final text with
   the right language, for the first language; then Mayura translation of the sample to the other codes.
"""

import array
import asyncio
import os
import sys
import time
import wave
from pathlib import Path

from app import languages
from app.agent.llm_client import OpenRouterClient
from app.agent.loop import SKELETON_SYSTEM_PROMPT
from app.config import Settings
from app.speech.stt import SAMPLE_RATE, SarvamRealtimeSTT, STTCallbacks, Transcript
from app.speech.translate import SarvamTranslator
from app.speech.tts import SPEECH_SAMPLE_RATE, SarvamTTS, split_sentences

OUT = Path(__file__).parent / "out"


def _resample(pcm: bytes, src: int, dst: int) -> bytes:
    """Nearest-sample resampling of 16-bit mono PCM; good enough for a smoke test."""
    samples = array.array("h")
    samples.frombytes(pcm)
    out = array.array(
        "h", (samples[min(len(samples) - 1, int(i * src / dst))] for i in range(len(samples) * dst // src))
    )
    return out.tobytes()


async def _streaming(settings: Settings, code: str) -> bool:
    """TTS stream -> live STT session. Prints time to first audio and to final transcript."""
    lang = languages.require(code)
    text = f"{lang.sample} ₹850."
    started = time.perf_counter()
    pcm, first = bytearray(), None
    async for chunk in SarvamTTS(settings).stream(split_sentences(text), code):
        first = first or time.perf_counter() - started
        pcm += chunk
    events: list[str] = []
    finals: list[Transcript] = []

    async def on_final(t: Transcript) -> None:
        finals.append(t)

    async def mark(name: str) -> None:
        events.append(name)

    session = await SarvamRealtimeSTT(settings).open_stream(
        STTCallbacks(
            on_final=on_final,
            on_speech_start=lambda: mark("speech_start"),
            on_speech_end=lambda: mark("speech_end"),
            on_partial=lambda _t: mark("partial"),
            on_error=lambda m: mark(f"error:{m}"),
        ),
        "auto",
    )
    audio = _resample(bytes(pcm), SPEECH_SAMPLE_RATE, SAMPLE_RATE)
    chunk = SAMPLE_RATE * 2 // 10
    spoken_at = time.perf_counter()
    for i in range(0, len(audio), chunk):  # paced like a live mic
        await session.push_pcm(audio[i : i + chunk])
        await asyncio.sleep(0.1)
    for _ in range(60):
        if finals:
            break
        await asyncio.sleep(0.1)
    await session.close()
    ok = bool(finals) and finals[0].language == code
    got = finals[0] if finals else None
    print(
        f"{'OK  ' if ok else 'FAIL'} {code} stream: first_audio={first:.2f}s final_after_speech="
        f"{time.perf_counter() - spoken_at - len(audio) / chunk * 0.1:.2f}s events={sorted(set(events))} "
        f"language={got.language if got else None} text={got.text if got else None!r}"
    )
    return ok


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

    try:
        failed |= not await _streaming(settings, codes[0])
    except Exception as exc:
        failed = True
        print(f"FAIL {codes[0]} stream: {exc}")

    translator = SarvamTranslator(settings)
    for code in codes[:3]:
        try:
            lang = languages.require(code)
            target = "hi-IN" if code != "hi-IN" else "en-IN"
            out = await translator.translate(lang.sample, code, target)
            print(f"OK   translate {code} -> {target}: {out!r}")
        except Exception as exc:
            failed = True
            print(f"FAIL translate {code}: {exc}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
