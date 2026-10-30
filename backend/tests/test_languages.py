import re
import unicodedata

import pytest
from pydantic import ValidationError

from app import languages
from app.schemas.merchant import MerchantPatch


def test_registry_is_consistent() -> None:
    assert len(languages.LANGUAGES) == 11  # Bulbul's languages (docs/voice.md#languages)
    for code, lang in languages.LANGUAGES.items():
        assert re.fullmatch(r"[a-z]{2}-IN", code)
        if lang.script != "Latin":
            # every sample is written in its own script
            letters = [c for c in lang.sample if unicodedata.category(c).startswith("L")]
            assert all(lang.block[0] <= ord(c) <= lang.block[1] for c in letters), code


def test_odia_code_mapping_for_realtime_stt() -> None:
    assert languages.to_stt_code("od-IN") == "or-IN"
    assert languages.from_stt_code("or-IN") == "od-IN"
    assert languages.to_stt_code("auto") == "auto"
    assert languages.to_stt_code("te-IN") == "te-IN"


@pytest.mark.parametrize(
    ("text", "current", "shop", "expected"),
    [
        ("ఈ చొక్కా ఎంత?", None, [], "te-IN"),
        ("ಈ ಶರ್ಟ್ ಎಷ್ಟು?", "te-IN", [], "kn-IN"),
        ("shirt ఎంత", None, [], "te-IN"),  # Latin first, then Telugu
        ("এটা কত?", None, [], "bn-IN"),
        ("ഇത് എത്ര?", None, [], "ml-IN"),
        ("ଏହା କେତେ?", None, [], "od-IN"),
        ("यह कितने का है?", "mr-IN", ["hi-IN", "mr-IN"], "mr-IN"),  # shared script keeps current
        ("हे किती आहे?", "te-IN", ["te-IN", "mr-IN", "hi-IN"], "mr-IN"),  # first shop language with the script
        ("यह कितने का है?", None, [], "hi-IN"),  # table order when nothing else decides
        ("shirt price enta?", "te-IN", [], None),  # Latin: caller keeps session language
        ("850", None, [], None),
    ],
)
def test_script_language(text: str, current: str | None, shop: list[str], expected: str | None) -> None:
    assert languages.script_language(text, current, shop) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "at least one language"),
        (["hi-IN", "hi-IN"], "must not repeat"),
        (["hi"], "unsupported language"),
    ],
)
def test_shop_languages_are_validated(value: list[str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        MerchantPatch(languages=value)


def test_any_supported_shop_languages_accepted() -> None:
    assert MerchantPatch(languages=["ta-IN", "en-IN", "od-IN"]).languages == ["ta-IN", "en-IN", "od-IN"]
