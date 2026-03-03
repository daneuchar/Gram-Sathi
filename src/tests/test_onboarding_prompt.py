import pytest
from app.pipeline.nova_client import ONBOARDING_PROMPT, extract_profile_marker


def test_onboarding_prompt_exists():
    assert "<<<PROFILE:" in ONBOARDING_PROMPT
    assert "name" in ONBOARDING_PROMPT
    assert "state" in ONBOARDING_PROMPT
    assert "district" in ONBOARDING_PROMPT


def test_extract_profile_marker_found():
    response = 'Welcome! <<<PROFILE:{"name":"Ramesh","state":"Tamil Nadu","district":"Coimbatore"}>>> How can I help?'
    profile, clean = extract_profile_marker(response)
    assert profile == {"name": "Ramesh", "state": "Tamil Nadu", "district": "Coimbatore"}
    assert "<<<PROFILE:" not in clean
    assert "How can I help?" in clean


def test_extract_profile_marker_not_found():
    response = "Hello, how can I help you today?"
    profile, clean = extract_profile_marker(response)
    assert profile is None
    assert clean == response


def test_extract_profile_marker_strips_whitespace():
    response = "Great!  <<<PROFILE:{\"name\":\"Anita\",\"state\":\"Punjab\",\"district\":\"Ludhiana\"}>>>\n\nNamaste Anita!"
    profile, clean = extract_profile_marker(response)
    assert profile["name"] == "Anita"
    assert "<<<PROFILE:" not in clean
    assert "Namaste Anita!" in clean
    assert "Great!" in clean


def test_extract_profile_marker_malformed_json():
    response = "Here <<<PROFILE:{name: Ramesh, state: TN}>>> done"
    profile, clean = extract_profile_marker(response)
    assert profile is None
    assert "<<<PROFILE:" not in clean  # marker must be stripped even on parse failure
    assert "done" in clean
