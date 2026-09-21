"""Model resolution must never invent a model name.

The metadata path used to fall back to a hardcoded ``llama3`` when the
provider config carried no model, which wedged jobs against an Ollama install
that never had that model. Resolution is now explicit model -> primary model
for the same provider -> clear typed error naming the missing config key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src.llm_manager import (  # noqa: E402
    LLMManager,
    LLMModelNotConfiguredError,
    LLMModelNotFoundError,
    OllamaProvider,
)


class _MissingModelClient:
    """Fake ollama client: chat reports the model missing, list reports what exists."""

    def chat(self, **kwargs):
        raise Exception("model 'llama3' not found")

    def list(self):
        return {"models": [{"model": "glm-5.3-flash:cloud"}]}


def test_explicit_model_wins() -> None:
    manager = LLMManager({
        "llm": {
            "primary": {
                "provider": "ollama",
                "ollama": {"host": "http://localhost:11434", "model": "explicit-model"},
            }
        }
    })

    assert manager.primary_provider is not None
    assert manager.primary_provider.model == "explicit-model"


def test_missing_model_falls_back_to_primary_model() -> None:
    manager = LLMManager({
        "llm": {
            "primary": {
                "provider": "ollama",
                "ollama": {"host": "http://localhost:11434", "model": "glm-5.3-flash:cloud"},
            },
            "fallback": {
                "enabled": True,
                "provider": "ollama",
                "ollama": {"host": "http://localhost:11434"},
            },
        }
    })

    assert len(manager.fallback_providers) == 1
    assert manager.fallback_providers[0].model == "glm-5.3-flash:cloud"


def test_missing_model_raises_typed_error_naming_the_config_key() -> None:
    manager = LLMManager({
        "llm": {"primary": {"provider": "ollama", "ollama": {"host": "http://localhost:11434"}}}
    })

    assert manager.primary_provider is None
    with pytest.raises(LLMModelNotConfiguredError) as excinfo:
        manager.chat([{"role": "user", "content": "hi"}])

    assert excinfo.value.config_key == "llm.primary.ollama.model"
    assert "llama3" not in str(excinfo.value)


def test_ollama_provider_never_invents_a_model() -> None:
    provider = OllamaProvider({"host": "http://localhost:11434"})

    assert provider.model == ""
    provider.ollama = object()
    with pytest.raises(LLMModelNotConfiguredError):
        provider.chat([{"role": "user", "content": "hi"}])


def test_model_not_found_raises_instead_of_exiting() -> None:
    provider = OllamaProvider({"host": "http://localhost:11434", "model": "llama3"})
    provider.ollama = _MissingModelClient()

    with pytest.raises(LLMModelNotFoundError) as excinfo:
        provider.chat([{"role": "user", "content": "hi"}])

    assert isinstance(excinfo.value, Exception)
    assert not isinstance(excinfo.value, SystemExit)
    assert excinfo.value.model == "llama3"
    assert excinfo.value.available_models == ["glm-5.3-flash:cloud"]


def test_builtin_defaults_do_not_invent_a_model() -> None:
    from ui.config_utils import BUILTIN_DEFAULTS

    assert "model" not in BUILTIN_DEFAULTS["llm"]["primary"]["ollama"]
    assert "model" not in BUILTIN_DEFAULTS["llm"]["fallback"]["ollama"]
