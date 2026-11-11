from __future__ import annotations

import io

import numpy as np
import soundfile as sf


def register(client, wav_bytes, voice_id="narrator", headers=None, **fields):
    data = {"id": voice_id, "ref_text": "This is a short reference clip.", **fields}
    return client.post(
        "/voices",
        data=data,
        files={"ref_audio": ("ref.wav", wav_bytes, "audio/wav")},
        headers=headers or {},
    )


def test_health_is_public(make_client):
    client = make_client(api_key="secret")
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["voices"] == 0
    assert body["model_loaded"] is False


def test_routes_require_key_when_configured(make_client):
    client = make_client(api_key="secret")
    assert client.get("/voices").status_code == 401
    assert client.get("/voices", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/voices", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.get("/voices", headers={"X-API-Key": "secret"}).status_code == 200


def test_no_auth_when_key_is_empty(make_client):
    client = make_client()
    assert client.get("/voices").status_code == 200


def test_register_list_and_delete_voice(make_client, wav_bytes):
    client = make_client()
    res = register(client, wav_bytes, name="Narrator", language="en")
    assert res.status_code == 201, res.text
    voice = res.json()
    assert voice["id"] == "narrator"
    assert voice["name"] == "Narrator"
    assert voice["language"] == "en"
    assert voice["ref_seconds"] == 3.0
    assert "prompt" not in voice and "ref_audio" not in voice  # internal paths stay private

    assert [v["id"] for v in client.get("/voices").json()["voices"]] == ["narrator"]
    assert client.delete("/voices/narrator").status_code == 200
    assert client.get("/voices").json()["voices"] == []
    assert client.delete("/voices/narrator").status_code == 404


def test_invalid_voice_id_is_rejected(make_client, wav_bytes):
    client = make_client()
    res = register(client, wav_bytes, voice_id="../etc/passwd")
    assert res.status_code == 400
    assert "voice id" in res.json()["detail"]


def test_reference_clip_length_is_checked(make_client):
    client = make_client()
    buf = io.BytesIO()
    sf.write(buf, np.zeros(1000, dtype=np.int16), 24000, format="WAV")  # 0.04 s
    res = register(client, buf.getvalue())
    assert res.status_code == 400
    assert "too short" in res.json()["detail"]


def test_speak_returns_audio_with_timing_headers(make_client, wav_bytes):
    client = make_client()
    register(client, wav_bytes, language="pt")
    res = client.post("/speak", json={"voice": "narrator", "text": "Hello there.", "format": "wav", "seed": 7})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "audio/wav"
    assert float(res.headers["x-audio-duration"]) == 1.0
    assert "x-gen-time" in res.headers
    audio, sr = sf.read(io.BytesIO(res.content))
    assert sr == 24000 and len(audio) == 24000
    # The voice's registered language is used when the request does not set one.
    assert client.calls["synthesize"][-1] == {"text": "Hello there.", "language": "pt", "speed": 1.0, "seed": 7}


def test_speak_unknown_voice_is_404(make_client):
    client = make_client()
    res = client.post("/speak", json={"voice": "nobody", "text": "Hi"})
    assert res.status_code == 404


def test_speak_validates_input(make_client, wav_bytes):
    client = make_client()
    register(client, wav_bytes)
    assert client.post("/speak", json={"voice": "narrator", "text": ""}).status_code == 422
    assert client.post("/speak", json={"voice": "narrator", "text": "hi", "speed": 5}).status_code == 422
    assert client.post("/speak", json={"voice": "narrator", "text": "hi", "format": "aac"}).status_code == 422


def test_openai_compatible_endpoint(make_client, wav_bytes):
    client = make_client()
    register(client, wav_bytes)
    res = client.post(
        "/v1/audio/speech",
        json={"model": "omnivoice", "input": "Hello", "voice": "narrator", "response_format": "flac", "speed": 9},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "audio/flac"
    assert client.calls["synthesize"][-1]["speed"] == 2.0  # clamped to the supported range


def test_legacy_env_prefix_still_works(monkeypatch):
    import importlib

    from app import config

    monkeypatch.delenv("VOICE_API_KEY", raising=False)
    monkeypatch.setenv("COUNCIL_API_KEY", "legacy")
    importlib.reload(config)
    assert config.API_KEY == "legacy"
