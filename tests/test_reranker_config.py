import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.platform import config


def _load(overrides=None):
    with patch.dict(os.environ, overrides or {}, clear=True), patch(
        "dotenv.load_dotenv", return_value=False
    ):
        return importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_process_config():
    yield
    importlib.reload(config)


def test_reranker_config_defaults():
    loaded = _load()

    assert loaded.RERANKER_ENABLED is True
    assert loaded.RERANKER_BASE_URL == "http://127.0.0.1:11435"
    assert loaded.RERANKER_MODEL_PATH == str(
        loaded.BASE_DIR / "data" / "models" / "qwen3-reranker-0.6b-q8_0.gguf"
    )
    assert loaded.RERANKER_API_MODEL == ""
    assert loaded.KB_RERANK_CANDIDATES == 20
    assert loaded.RERANKER_CONNECT_TIMEOUT_SECONDS == 2.0
    assert loaded.RERANKER_READ_TIMEOUT_SECONDS == 60.0
    assert loaded.RERANKER_SERVER_BIN == ""


def test_reranker_config_valid_overrides():
    loaded = _load(
        {
            "RERANKER_ENABLED": "off",
            "RERANKER_BASE_URL": "http://localhost:11440/",
            "RERANKER_MODEL_PATH": "/tmp/model.gguf",
            "RERANKER_API_MODEL": "local-reranker",
            "KB_RERANK_CANDIDATES": "7",
            "RERANKER_CONNECT_TIMEOUT_SECONDS": "0.5",
            "RERANKER_READ_TIMEOUT_SECONDS": "12.25",
            "RERANKER_SERVER_BIN": "/tmp/llama-server",
        }
    )

    assert loaded.RERANKER_ENABLED is False
    assert loaded.RERANKER_BASE_URL == "http://localhost:11440"
    assert loaded.RERANKER_MODEL_PATH == "/tmp/model.gguf"
    assert loaded.RERANKER_API_MODEL == "local-reranker"
    assert loaded.KB_RERANK_CANDIDATES == 7
    assert loaded.RERANKER_CONNECT_TIMEOUT_SECONDS == 0.5
    assert loaded.RERANKER_READ_TIMEOUT_SECONDS == 12.25
    assert loaded.RERANKER_SERVER_BIN == "/tmp/llama-server"


@pytest.mark.parametrize(
    ("name", "bad_value", "constant", "default"),
    [
        ("RERANKER_ENABLED", "perhaps", "RERANKER_ENABLED", True),
        ("KB_RERANK_CANDIDATES", "many", "KB_RERANK_CANDIDATES", 20),
        ("KB_RERANK_CANDIDATES", "0", "KB_RERANK_CANDIDATES", 20),
        (
            "RERANKER_CONNECT_TIMEOUT_SECONDS",
            "soon",
            "RERANKER_CONNECT_TIMEOUT_SECONDS",
            2.0,
        ),
        (
            "RERANKER_CONNECT_TIMEOUT_SECONDS",
            "nan",
            "RERANKER_CONNECT_TIMEOUT_SECONDS",
            2.0,
        ),
        (
            "RERANKER_READ_TIMEOUT_SECONDS",
            "-1",
            "RERANKER_READ_TIMEOUT_SECONDS",
            60.0,
        ),
    ],
)
def test_invalid_reranker_values_warn_and_fall_back(name, bad_value, constant, default):
    with pytest.warns(RuntimeWarning, match=name):
        loaded = _load({name: bad_value})

    assert getattr(loaded, constant) == default
    assert Path(loaded.RERANKER_MODEL_PATH).name == "qwen3-reranker-0.6b-q8_0.gguf"
