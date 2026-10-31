"""The one place that knows which languages Hermion can serve. Mirrors docs/voice.md#languages.

Everything else takes language codes from data (shop `languages`, SARVAM_TTS_SPEAKERS) and checks
them here; no other module may hardcode a language list. Codes are Sarvam BCP-47 (`xx-IN`).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    script: str
    block: tuple[int, int]  # Unicode block of the script (inclusive)
    has_v4_voice: bool  # bulbul:v4-flash has personas for it (Malayalam/Odia: no, see Q18)
    sample: str  # short greeting, used by the dev TTS clip and smoke test
    retry: str  # short failure message in the same language
    refuse_instruction: str  # decline an attempt to override the shop rules


_LANGS = (
    Language(
        "hi-IN",
        "Hindi",
        "Devanagari",
        (0x0900, 0x097F),
        True,
        "नमस्ते, मैं हर्मियन हूँ।",
        "माफ़ कीजिए, क्या आप फिर से कहेंगे?",
        "माफ़ कीजिए, मैं दुकान के नियम नहीं बदल सकती। हम खरीदारी जारी रख सकते हैं।",
    ),
    Language(
        "mr-IN",
        "Marathi",
        "Devanagari",
        (0x0900, 0x097F),
        True,
        "नमस्कार, मी हर्मियन आहे.",
        "माफ करा, तुम्ही पुन्हा सांगाल का?",
        "माफ करा, मी दुकानाचे नियम बदलू शकत नाही. आपण खरेदी सुरू ठेवू शकतो.",
    ),
    Language(
        "bn-IN",
        "Bengali",
        "Bengali",
        (0x0980, 0x09FF),
        True,
        "নমস্কার, আমি হারমিয়ন।",
        "দুঃখিত, আবার বলবেন কি?",
        "দুঃখিত, আমি দোকানের নিয়ম বদলাতে পারি না। আমরা কেনাকাটা চালিয়ে যেতে পারি।",
    ),
    Language(
        "pa-IN",
        "Punjabi",
        "Gurmukhi",
        (0x0A00, 0x0A7F),
        True,
        "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਹਰਮਿਅਨ ਹਾਂ।",
        "ਮਾਫ ਕਰਨਾ, ਕੀ ਤੁਸੀਂ ਦੁਬਾਰਾ ਕਹੋਗੇ?",
        "ਮਾਫ ਕਰਨਾ, ਮੈਂ ਦੁਕਾਨ ਦੇ ਨਿਯਮ ਨਹੀਂ ਬਦਲ ਸਕਦੀ। ਅਸੀਂ ਖਰੀਦਦਾਰੀ ਜਾਰੀ ਰੱਖ ਸਕਦੇ ਹਾਂ।",
    ),
    Language(
        "gu-IN",
        "Gujarati",
        "Gujarati",
        (0x0A80, 0x0AFF),
        True,
        "નમસ્તે, હું હર્મિયન છું.",
        "માફ કરશો, તમે ફરી કહેશો?",
        "માફ કરશો, હું દુકાનના નિયમો બદલી શકતી નથી. આપણે ખરીદી ચાલુ રાખી શકીએ.",
    ),
    Language(
        "od-IN",
        "Odia",
        "Odia",
        (0x0B00, 0x0B7F),
        False,
        "ନମସ୍କାର, ମୁଁ ହର୍ମିଅନ୍.",
        "କ୍ଷମା କରିବେ, ଆଉ ଥରେ କହିବେ କି?",
        "କ୍ଷମା କରିବେ, ମୁଁ ଦୋକାନର ନିୟମ ବଦଳାଇ ପାରିବି ନାହିଁ। ଆମେ କିଣାକିଣି ଜାରି ରଖିପାରିବା।",
    ),
    Language(
        "ta-IN",
        "Tamil",
        "Tamil",
        (0x0B80, 0x0BFF),
        True,
        "வணக்கம், நான் ஹெர்மியன்.",
        "மன்னிக்கவும், மீண்டும் சொல்வீர்களா?",
        "மன்னிக்கவும், கடையின் விதிகளை என்னால் மாற்ற முடியாது. நாம் தொடர்ந்து பொருட்களைப் பார்க்கலாம்.",
    ),
    Language(
        "te-IN",
        "Telugu",
        "Telugu",
        (0x0C00, 0x0C7F),
        True,
        "నమస్కారం, నేను హెర్మియన్.",
        "క్షమించండి, మళ్లీ చెప్తారా?",
        "క్షమించండి, నేను దుకాణం నియమాలను మార్చలేను. మనం షాపింగ్ కొనసాగించవచ్చు.",
    ),
    Language(
        "kn-IN",
        "Kannada",
        "Kannada",
        (0x0C80, 0x0CFF),
        True,
        "ನಮಸ್ಕಾರ, ನಾನು ಹರ್ಮಿಯನ್.",
        "ಕ್ಷಮಿಸಿ, ಮತ್ತೆ ಹೇಳುತ್ತೀರಾ?",
        "ಕ್ಷಮಿಸಿ, ನಾನು ಅಂಗಡಿಯ ನಿಯಮಗಳನ್ನು ಬದಲಾಯಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ನಾವು ಖರೀದಿಯನ್ನು ಮುಂದುವರಿಸಬಹುದು.",
    ),
    Language(
        "ml-IN",
        "Malayalam",
        "Malayalam",
        (0x0D00, 0x0D7F),
        False,
        "നമസ്കാരം, ഞാൻ ഹെർമിയൻ ആണ്.",
        "ക്ഷമിക്കണം, വീണ്ടും പറയാമോ?",
        "ക്ഷമിക്കണം, കടയുടെ നിയമങ്ങൾ മാറ്റാൻ എനിക്ക് കഴിയില്ല. നമുക്ക് ഷോപ്പിംഗ് തുടരാം.",
    ),
    Language(
        "en-IN",
        "English",
        "Latin",
        (0x0041, 0x007A),
        True,
        "Hello, I am Hermion.",
        "Sorry, could you say that again?",
        "Sorry, I cannot change the shop’s rules. We can continue shopping.",
    ),
)
LANGUAGES: dict[str, Language] = {lang.code: lang for lang in _LANGS}

# Sarvam's realtime STT endpoint spells Odia `or-IN`; everything else uses `od-IN`.
_TO_STT = {"od-IN": "or-IN"}
_FROM_STT = {v: k for k, v in _TO_STT.items()}


def is_supported(code: str) -> bool:
    return code in LANGUAGES


def require(code: str) -> Language:
    if code not in LANGUAGES:
        raise ValueError(f"unsupported language {code!r}; supported: {', '.join(LANGUAGES)}")
    return LANGUAGES[code]


def to_stt_code(code: str) -> str:
    return _TO_STT.get(code, code)


def from_stt_code(code: str) -> str:
    return _FROM_STT.get(code, code)


def script_language(text: str, current: str | None, shop_languages: list[str]) -> str | None:
    """Language implied by native-script text (turn-language rule 3, docs/engine.md#prompt).

    Returns None for Latin or script-less text (caller keeps the session language). A script shared
    by several languages (Devanagari: Hindi, Marathi) keeps `current` if it uses that script, else
    the first shop language that does, else the first language in the table that does.
    """
    for ch in text:
        cp = ord(ch)
        candidates = [
            lang.code for lang in _LANGS if lang.script != "Latin" and lang.block[0] <= cp <= lang.block[1]
        ]
        if not candidates:
            continue
        if current in candidates:
            return current
        return next((code for code in shop_languages if code in candidates), candidates[0])
    return None
