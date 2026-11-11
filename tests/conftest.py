"""Test fixtures.

The real engine needs torch and a 2.4 GB model. These tests replace the
engine's model-facing functions with fakes, so they run anywhere in seconds
and exercise the HTTP layer, auth, validation and the voice registry.
"""
from __future__ import annotations

import importlib
import sys
import types

import numpy as np
import pytest

SAMPLE_RATE = 24000


class FakeAudio:
    """Just enough of a torch.Tensor for app.main and app.engine.encode."""

    def __init__(self, samples: np.ndarray):
        self._samples = samples

    def numel(self) -> int:
        return self._samples.size

    def numpy(self) -> np.ndarray:
        return self._samples


def _install_torch_stub() -> None:
    try:
        import torch  # noqa: F401
    except ImportError:
        torch = types.ModuleType("torch")
        torch.Tensor = object
        torch.dtype = object
        torch.cuda = types.SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None)
        torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
        torch.manual_seed = lambda seed: None
        sys.modules["torch"] = torch


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    """Build a TestClient against a fresh data dir, optionally with an API key."""
    from fastapi.testclient import TestClient

    _install_torch_stub()

    def factory(api_key: str = ""):
        monkeypatch.setenv("VOICE_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("VOICE_PRELOAD", "0")
        monkeypatch.setenv("VOICE_CLEAN_REFS", "0")
        monkeypatch.setenv("VOICE_API_KEY", api_key)
        monkeypatch.delenv("COUNCIL_API_KEY", raising=False)

        from app import config, engine, main, voices
        for mod in (config, voices, engine, main):
            importlib.reload(mod)

        calls: dict[str, list] = {"synthesize": []}

        def fake_convert(src, dst):
            dst.write_bytes(src.read_bytes())

        def fake_encode_prompt(ref_wav, ref_text, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"prompt")

        def fake_synthesize(prompt_path, text, language, speed=1.0,
                            num_step=None, guidance_scale=None, seed=None):
            calls["synthesize"].append(
                {"text": text, "language": language, "speed": speed, "seed": seed}
            )
            samples = np.zeros(SAMPLE_RATE, dtype=np.float32)  # 1 s of silence
            return FakeAudio(samples), SAMPLE_RATE, 0.01

        monkeypatch.setattr(engine, "convert_to_wav", fake_convert)
        monkeypatch.setattr(engine, "encode_prompt", fake_encode_prompt)
        monkeypatch.setattr(engine, "synthesize", fake_synthesize)
        monkeypatch.setattr(engine, "resolve_device", lambda: "cpu")

        client = TestClient(main.app)
        client.__enter__()
        client.calls = calls
        return client

    return factory


@pytest.fixture()
def wav_bytes() -> bytes:
    """A 3-second mono 24 kHz WAV file."""
    import io

    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.zeros(SAMPLE_RATE * 3, dtype=np.int16), SAMPLE_RATE, format="WAV")
    return buf.getvalue()
