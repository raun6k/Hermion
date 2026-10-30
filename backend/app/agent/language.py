"""Turn-language resolution (docs/engine.md#prompt). Pure: no hardcoded language list."""

from app import languages


def resolve_turn_language(
    *,
    pinned: str | None,
    stt_language: str | None,
    text: str,
    session_language: str | None,
    shop_languages: list[str],
) -> str | None:
    """First match wins: customer pin, this turn's STT language, native-script keypad text, then the
    session's current language (Latin text keeps it). None = nothing known yet (first turn)."""
    if pinned and languages.is_supported(pinned):
        return pinned
    if stt_language and languages.is_supported(stt_language):
        return stt_language
    if scripted := languages.script_language(text, session_language, shop_languages):
        return scripted
    return session_language
