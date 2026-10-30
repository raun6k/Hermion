"""Dev-only helpers for the walking skeleton (test audio clip for the browser player)."""

from fastapi import APIRouter, Query, Request, Response

from app import languages
from app.schemas.common import AppError
from app.speech.tts import build_tts

router = APIRouter(prefix="/dev", tags=["dev"])


@router.get("/tts-test", response_class=Response)
async def tts_test(request: Request, lang: str = Query("te-IN")) -> Response:
    """Speak the sample greeting for any supported language (see app/languages.py)."""
    if not languages.is_supported(lang):
        raise AppError(
            "UNSUPPORTED_LANGUAGE", f"{lang} is not supported; use one of {', '.join(languages.LANGUAGES)}"
        )
    wav = await build_tts(request.app.state.settings).synthesize(languages.LANGUAGES[lang].sample, lang)
    return Response(content=wav, media_type="audio/wav")
