"""Turn-language resolution (docs/engine.md#prompt). Pure: no hardcoded language list."""

import re
from collections.abc import Iterable

from app import languages


def resolve_turn_language(
    *,
    stt_language: str | None,
    text: str,
    session_language: str | None,
    shop_languages: list[str],
) -> str | None:
    """First match wins: this turn's STT language (the customer may switch any time), native-script
    text, then the session's current language (Latin text keeps it). None = nothing known yet."""
    if stt_language and languages.is_supported(stt_language):
        return stt_language
    if scripted := languages.script_language(text, session_language, shop_languages):
        return scripted
    return session_language


def matches_language_script(text: str, code: str | None, product_names: Iterable[str] = ()) -> bool:
    """Reject a reply mostly in another script when the turn language is known."""
    if not code or not languages.is_supported(code):
        return True
    had_letters = any(c.isalpha() for c in text)
    lang = languages.LANGUAGES[code]
    if lang.script != "Latin":
        # Only exempt consecutive words actually present in a returned catalog name.
        for name in product_names:
            words = re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", name)
            for size in range(len(words), 1, -1):
                for start in range(len(words) - size + 1):
                    phrase = r"\s+".join(re.escape(word) for word in words[start : start + size])
                    text = re.sub(r"(?<!\w)" + phrase + r"(?!\w)", " ", text, flags=re.IGNORECASE)
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return not had_letters
    lo, hi = lang.block
    return sum(lo <= ord(c) <= hi for c in letters) / len(letters) >= 0.6
