from __future__ import annotations

import pytest


@pytest.fixture()
def engine(make_client):
    make_client()  # installs the torch stub and reloads the app modules
    from app import engine

    return engine


@pytest.mark.parametrize(
    ("given", "expected"),
    [("pt-BR", "pt"), ("en_US", "en"), ("EN", "en"), ("auto", None), ("", None), (None, None),
     ("Portuguese", "Portuguese")],
)
def test_normalize_language(engine, given, expected):
    assert engine.normalize_language(given) == expected


def test_encode_rejects_unknown_format(engine):
    import numpy as np

    from tests.conftest import FakeAudio

    with pytest.raises(ValueError):
        engine.encode(FakeAudio(np.zeros(10, dtype=np.float32)), 24000, "aac")
