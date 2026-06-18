"""Tests for flowstate.embeddings — lazy embedding provider.

All tests run offline: no fastembed import, no model downloads, no network.
An injected deterministic fake embed_fn is used throughout.
"""

from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_embed_fn(dim: int = 4):
    """Return a deterministic embed_fn that produces vectors of the given dim."""
    call_count = []  # mutable container so tests can inspect call count

    def embed_fn(texts: list[str]) -> list[list[float]]:
        call_count.append(1)
        return [[float(i) / (dim * 10) for i in range(dim)] for _ in texts]

    embed_fn.call_count = call_count  # type: ignore[attr-defined]
    return embed_fn


# ---------------------------------------------------------------------------
# Import guard — must succeed with fastembed absent
# ---------------------------------------------------------------------------


def test_import_succeeds_without_fastembed(monkeypatch):
    """Importing flowstate.embeddings must NOT raise even when fastembed is absent."""
    real_import = builtins.__import__

    def block_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    # Pop any cached copy of the module under test first.
    monkeypatch.delitem(sys.modules, "flowstate.embeddings", raising=False)
    monkeypatch.setattr(builtins, "__import__", block_fastembed)
    sys.modules.pop("fastembed", None)

    # Should not raise.
    import flowstate.embeddings  # noqa: F401 (re-imported intentionally)

    # Restore the real module for other tests.
    monkeypatch.delitem(sys.modules, "flowstate.embeddings", raising=False)


# ---------------------------------------------------------------------------
# available() — absent fastembed path
# ---------------------------------------------------------------------------


def test_available_returns_false_when_fastembed_absent(monkeypatch):
    """get_embedder().available() returns False (not raise) when fastembed is absent."""
    import flowstate.embeddings as emb

    real_import = builtins.__import__

    def block_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_fastembed)
    sys.modules.pop("fastembed", None)

    provider = emb.get_embedder()
    result = provider.available()

    assert isinstance(result, bool)
    assert result is False


def test_embed_returns_empty_list_when_fastembed_absent(monkeypatch):
    """embed() returns [] and does not raise when fastembed is absent."""
    import flowstate.embeddings as emb

    real_import = builtins.__import__

    def block_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_fastembed)
    sys.modules.pop("fastembed", None)

    provider = emb.get_embedder()
    result = provider.embed(["hello", "world"])

    assert result == []


# ---------------------------------------------------------------------------
# Injected embed_fn path
# ---------------------------------------------------------------------------


def test_available_returns_true_with_injected_embed_fn():
    """available() is True when an embed_fn is injected."""
    import flowstate.embeddings as emb

    fake = _make_fake_embed_fn(dim=4)
    provider = emb.get_embedder(embed_fn=fake)

    assert provider.available() is True


def test_embed_returns_fake_vectors_with_injected_fn():
    """embed() returns the fake vectors when an embed_fn is injected."""
    import flowstate.embeddings as emb

    fake = _make_fake_embed_fn(dim=3)
    provider = emb.get_embedder(embed_fn=fake)

    result = provider.embed(["hello"])

    assert len(result) == 1
    assert len(result[0]) == 3


def test_embed_multiple_texts_with_injected_fn():
    """embed() handles multiple texts correctly."""
    import flowstate.embeddings as emb

    fake = _make_fake_embed_fn(dim=2)
    provider = emb.get_embedder(embed_fn=fake)

    result = provider.embed(["a", "b", "c"])

    assert len(result) == 3
    for vec in result:
        assert len(vec) == 2
        assert all(isinstance(v, float) for v in vec)


def test_dim_derived_from_injected_fn():
    """dim equals the vector length of the injected embed_fn, not _DEFAULT_DIM."""
    import flowstate.embeddings as emb

    fake = _make_fake_embed_fn(dim=7)
    provider = emb.get_embedder(embed_fn=fake)

    assert provider.dim == 7


def test_dim_with_two_element_vector():
    """dim == 2 for a 2-element vector embed_fn."""
    import flowstate.embeddings as emb

    provider = emb.get_embedder(embed_fn=lambda t: [[1.0, 0.0]])

    assert provider.dim == 2


def test_embed_explicit_vectors_via_lambda():
    """Acceptance criterion: lambda embed_fn returning [[1.0, 0.0]]."""
    import flowstate.embeddings as emb

    provider = emb.get_embedder(embed_fn=lambda t: [[1.0, 0.0]])

    assert provider.embed(["x"]) == [[1.0, 0.0]]
    assert provider.available() is True


# ---------------------------------------------------------------------------
# dim — absent fastembed path
# ---------------------------------------------------------------------------


def test_dim_returns_default_when_fastembed_absent(monkeypatch):
    """dim returns _DEFAULT_DIM (384) and does not raise when fastembed is absent."""
    import flowstate.embeddings as emb

    real_import = builtins.__import__

    def block_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_fastembed)
    sys.modules.pop("fastembed", None)

    provider = emb.get_embedder()

    assert provider.dim == emb._DEFAULT_DIM


# ---------------------------------------------------------------------------
# Model-name precedence
# ---------------------------------------------------------------------------


def test_model_name_env_var_wins(monkeypatch):
    """FLOWSTATE_EMBED_MODEL env var overrides config.json and the default."""
    import flowstate.embeddings as emb

    monkeypatch.setenv("FLOWSTATE_EMBED_MODEL", "custom/model-env")
    provider = emb.get_embedder()

    assert provider.model_name == "custom/model-env"


def test_model_name_config_json_used_when_env_absent(monkeypatch, tmp_path: Path):
    """embed_model in config.json is used when env var is absent."""
    import flowstate.embeddings as emb

    monkeypatch.delenv("FLOWSTATE_EMBED_MODEL", raising=False)

    planning_dir = tmp_path / ".planning"
    planning_dir.mkdir()
    config = planning_dir / "config.json"
    config.write_text(json.dumps({"embed_model": "custom/model-cfg"}))

    provider = emb.get_embedder(root=tmp_path)

    assert provider.model_name == "custom/model-cfg"


def test_model_name_default_when_nothing_configured(monkeypatch, tmp_path: Path):
    """Default model name is BAAI/bge-small-en-v1.5 when env and config absent."""
    import flowstate.embeddings as emb

    monkeypatch.delenv("FLOWSTATE_EMBED_MODEL", raising=False)

    # tmp_path has no .planning/config.json
    provider = emb.get_embedder(root=tmp_path)

    assert provider.model_name == "BAAI/bge-small-en-v1.5"


def test_model_name_env_wins_over_config(monkeypatch, tmp_path: Path):
    """Env var beats config.json when both are set."""
    import flowstate.embeddings as emb

    monkeypatch.setenv("FLOWSTATE_EMBED_MODEL", "env/model")

    planning_dir = tmp_path / ".planning"
    planning_dir.mkdir()
    config = planning_dir / "config.json"
    config.write_text(json.dumps({"embed_model": "cfg/model"}))

    provider = emb.get_embedder(root=tmp_path)

    assert provider.model_name == "env/model"


def test_model_name_empty_env_falls_through_to_config(monkeypatch, tmp_path: Path):
    """Empty FLOWSTATE_EMBED_MODEL falls through to config.json value."""
    import flowstate.embeddings as emb

    monkeypatch.setenv("FLOWSTATE_EMBED_MODEL", "")  # empty — should be skipped

    planning_dir = tmp_path / ".planning"
    planning_dir.mkdir()
    config = planning_dir / "config.json"
    config.write_text(json.dumps({"embed_model": "cfg/from-config"}))

    provider = emb.get_embedder(root=tmp_path)

    assert provider.model_name == "cfg/from-config"


def test_model_name_empty_config_falls_through_to_default(monkeypatch, tmp_path: Path):
    """Empty embed_model in config.json falls through to the default."""
    import flowstate.embeddings as emb

    monkeypatch.delenv("FLOWSTATE_EMBED_MODEL", raising=False)

    planning_dir = tmp_path / ".planning"
    planning_dir.mkdir()
    config = planning_dir / "config.json"
    config.write_text(json.dumps({"embed_model": ""}))  # empty — skipped

    provider = emb.get_embedder(root=tmp_path)

    assert provider.model_name == "BAAI/bge-small-en-v1.5"


def test_model_name_malformed_config_falls_through_to_default(monkeypatch, tmp_path: Path):
    """Malformed config.json falls through to the default."""
    import flowstate.embeddings as emb

    monkeypatch.delenv("FLOWSTATE_EMBED_MODEL", raising=False)

    planning_dir = tmp_path / ".planning"
    planning_dir.mkdir()
    config = planning_dir / "config.json"
    config.write_text("not valid json!!!")

    provider = emb.get_embedder(root=tmp_path)

    assert provider.model_name == "BAAI/bge-small-en-v1.5"


# ---------------------------------------------------------------------------
# Model caching — embed_fn injected path
# ---------------------------------------------------------------------------


def test_two_embed_calls_use_injected_fn_each_time():
    """Two embed() calls both use the injected embed_fn (no extra construction)."""
    import flowstate.embeddings as emb

    fake = _make_fake_embed_fn(dim=3)
    provider = emb.get_embedder(embed_fn=fake)

    provider.embed(["first"])
    provider.embed(["second"])

    # Both calls hit the embed_fn
    assert len(fake.call_count) == 2  # type: ignore[attr-defined]


def test_model_not_constructed_via_injected_fn(monkeypatch):
    """When an embed_fn is injected, TextEmbedding is never constructed."""
    import flowstate.embeddings as emb

    constructed = []

    class FakeTextEmbedding:
        def __init__(self, *args, **kwargs):
            constructed.append(1)

        def embed(self, texts):
            return iter([[0.0]])

    # Patch fastembed at the module level in embeddings
    monkeypatch.setattr("flowstate.embeddings.TextEmbedding", FakeTextEmbedding, raising=False)

    fake = _make_fake_embed_fn(dim=4)
    provider = emb.get_embedder(embed_fn=fake)
    provider.embed(["hello"])
    _ = provider.dim  # access dim too — assign to _ to satisfy B018

    assert constructed == [], "TextEmbedding should never be constructed with an injected embed_fn"


# ---------------------------------------------------------------------------
# Constants exposed by module
# ---------------------------------------------------------------------------


def test_module_constants_exist():
    """Module exports the required constants."""
    import flowstate.embeddings as emb

    assert hasattr(emb, "_EMBED_MODEL_ENV_VAR")
    assert emb._EMBED_MODEL_ENV_VAR == "FLOWSTATE_EMBED_MODEL"
    assert hasattr(emb, "_DEFAULT_EMBED_MODEL")
    assert emb._DEFAULT_EMBED_MODEL == "BAAI/bge-small-en-v1.5"
    assert hasattr(emb, "_DEFAULT_DIM")
    assert emb._DEFAULT_DIM == 384
