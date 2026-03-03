import pytest
from app.pipeline.pipeline import _classify_filler


def test_short_ack_is_none():
    assert _classify_filler("Yes") == "none"
    assert _classify_filler("Ok thank you") == "none"
    assert _classify_filler("Thanks") == "none"


def test_price_query_is_mandi():
    assert _classify_filler("What is the tomato price in Tamil Nadu?") == "mandi"
    assert _classify_filler("Mandi rate for onion today") == "mandi"
    assert _classify_filler("wheat price in Punjab") == "mandi"


def test_weather_query_is_weather():
    assert _classify_filler("Will it rain tomorrow in Chennai?") == "weather"
    assert _classify_filler("What is the weather forecast for my district?") == "weather"


def test_scheme_query_is_scheme():
    assert _classify_filler("Am I eligible for PM Kisan scheme?") == "scheme"
    assert _classify_filler("What government subsidies are available?") == "scheme"
    assert _classify_filler("Is this yojana available for me?") == "scheme"
    assert _classify_filler("Am I eligible for this?") == "scheme"


def test_open_question_is_generic():
    assert _classify_filler("Tell me about crop rotation for paddy") == "generic"
    assert _classify_filler("When should I sow wheat?") == "generic"
