import logging

import pytest

from app.biometrics import BiometricError, BiometricUnavailable, RealBiometrics
from app.config import Settings


def make_engine(monkeypatch, embed):
    """A RealBiometrics whose underlying audio/video embedding is replaced by `embed`."""
    monkeypatch.setattr("app.biometrics.audio.embed_audio", embed)
    monkeypatch.setattr("app.biometrics.video.embed_face", embed)
    return RealBiometrics(Settings.from_env())


def boom(*_args):
    raise RuntimeError("native library exploded: /usr/lib/secret/path")


def test_unexpected_library_failure_becomes_unavailable_not_a_crash(monkeypatch):
    engine = make_engine(monkeypatch, boom)
    with pytest.raises(BiometricUnavailable):
        engine.audio_embedding(b"x")
    with pytest.raises(BiometricUnavailable):
        engine.face_embedding(b"x")


def test_failure_is_logged_without_leaking_sample_data(monkeypatch, caplog):
    engine = make_engine(monkeypatch, boom)
    with caplog.at_level(logging.ERROR, logger="auth.audit"), pytest.raises(BiometricUnavailable):
        engine.audio_embedding(b"secret-recording-bytes")
    assert "RuntimeError" in caplog.text
    assert "secret-recording-bytes" not in caplog.text


def test_bad_sample_stays_a_client_error(monkeypatch):
    def bad_sample(*_args):
        raise BiometricError("Recording is too short")

    engine = make_engine(monkeypatch, bad_sample)
    with pytest.raises(BiometricError):
        engine.audio_embedding(b"x")


def test_missing_library_stays_unavailable(monkeypatch):
    def missing(*_args):
        raise BiometricUnavailable("ffmpeg is not installed")

    engine = make_engine(monkeypatch, missing)
    with pytest.raises(BiometricUnavailable):
        engine.face_embedding(b"x")


def test_successful_embedding_is_passed_through(monkeypatch):
    engine = make_engine(monkeypatch, lambda *_a: b"\x00\x01")
    assert engine.audio_embedding(b"x") == b"\x00\x01"
