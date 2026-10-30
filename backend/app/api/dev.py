"""Dev-only helpers for the walking skeleton (test audio clip for the browser player)."""

from fastapi import APIRouter, Query, Request, Response

from app.speech.tts import build_tts

router = APIRouter(prefix="/dev", tags=["dev"])

SAMPLE = {"te-IN": "నమస్కారం, నేను హెర్మియన్.", "hi-IN": "नमस्ते, मैं हर्मियन हूँ।"}


@router.get("/tts-test", response_class=Response)
async def tts_test(request: Request, lang: str = Query("te-IN", pattern="^(te-IN|hi-IN)$")) -> Response:
    wav = await build_tts(request.app.state.settings).synthesize(SAMPLE[lang], lang)
    return Response(content=wav, media_type="audio/wav")
