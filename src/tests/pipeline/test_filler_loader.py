import pytest
from pathlib import Path
import app.pipeline.sarvam_tts as tts_mod


def _make_fake_fillers(tmp_path: Path) -> Path:
    filler_dir = tmp_path / "fillers"
    filler_dir.mkdir()
    (filler_dir / "hi_IN_generic_0_8000.raw").write_bytes(b"audio0")
    (filler_dir / "hi_IN_generic_1_8000.raw").write_bytes(b"audio1")
    (filler_dir / "hi_IN_mandi_0_8000.raw").write_bytes(b"mandi0")
    (filler_dir / "ta_IN_generic_0_8000.raw").write_bytes(b"ta_audio0")
    (filler_dir / "en_IN_generic_0_8000.raw").write_bytes(b"en_audio0")
    return filler_dir


def _setup(tmp_path, monkeypatch):
    filler_dir = _make_fake_fillers(tmp_path)
    monkeypatch.setattr(tts_mod, "FILLERS_DIR", filler_dir)
    monkeypatch.setattr(tts_mod, "FILLER_AUDIO", tts_mod._load_filler_cache())


def test_get_filler_audio_returns_bytes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = tts_mod.get_filler_audio("hi-IN", "generic", 8000)
    assert result in (b"audio0", b"audio1")


def test_get_filler_audio_category_mandi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = tts_mod.get_filler_audio("hi-IN", "mandi", 8000)
    assert result == b"mandi0"


def test_get_filler_audio_falls_back_to_generic(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = tts_mod.get_filler_audio("hi-IN", "weather", 8000)
    assert result in (b"audio0", b"audio1")


def test_get_filler_audio_none_category_returns_none(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = tts_mod.get_filler_audio("hi-IN", "none", 8000)
    assert result is None
