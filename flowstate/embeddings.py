"""Optional lazy embedding provider backed by fastembed.

Exposes a graceful-degradation seam: importing this module NEVER requires
fastembed.  The embedder activates only when the ``[semantic]`` pip extra is
installed and an embed() call is made.  When absent every caller sees
``available() == False`` and gets ``[]`` from ``embed()``.

Public API::

    provider = get_embedder(root=Path("."))
    if provider.available():
        vectors = provider.embed(["some text"])
        print(f"dim={provider.dim}")

Model-name precedence (mirrors context_prefix._load_budget):
    1. ``FLOWSTATE_EMBED_MODEL`` env var (non-empty string)
    2. ``embed_model`` key in ``.planning/config.json`` (non-empty string)
    3. ``_DEFAULT_EMBED_MODEL`` constant (``BAAI/bge-small-en-v1.5``)
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module-level constants — these are the contract referenced by tests
# ---------------------------------------------------------------------------

_EMBED_MODEL_ENV_VAR = "FLOWSTATE_EMBED_MODEL"
_CONFIG_PATH = ".planning/config.json"
_DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_DIM = 384

# Module-level placeholder: populated lazily inside _ensure_model() so the
# name is accessible for monkeypatching in tests without requiring fastembed.
TextEmbedding: Any = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_model_name(root: Path | None) -> str:
    """Return the embedding model name using env > config.json > default precedence.

    Mirrors the logic of ``context_prefix._load_budget`` exactly:
    - Env var checked first; non-empty string wins.
    - ``embed_model`` key in ``.planning/config.json`` checked next;
      non-empty string wins.
    - Falls back to ``_DEFAULT_EMBED_MODEL``.
    """
    env_value = os.environ.get(_EMBED_MODEL_ENV_VAR)
    if env_value:
        return env_value

    config_path = root / _CONFIG_PATH if root is not None else Path(_CONFIG_PATH)

    if config_path.exists():
        try:
            data: dict[str, Any] = json.loads(config_path.read_text())
            value = data.get("embed_model")
            if isinstance(value, str) and value:
                return value
        except Exception:
            pass

    return _DEFAULT_EMBED_MODEL


# ---------------------------------------------------------------------------
# Embedder class
# ---------------------------------------------------------------------------


class Embedder:
    """Lazy fastembed-backed embedding provider with graceful degradation.

    Instantiate via ``get_embedder()``.  Do NOT construct directly in
    production code — the factory resolves the model name.

    An injected ``embed_fn`` (for tests) bypasses fastembed entirely.
    """

    def __init__(self, model_name: str, embed_fn: Callable | None = None) -> None:
        self.model_name = model_name
        self._embed_fn = embed_fn
        self._model: Any = None  # cached TextEmbedding instance
        self._unavailable: bool = False  # True after a failed load attempt

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _ensure_model(self) -> bool:
        """Try to load the fastembed model exactly once; cache the result.

        Returns True if the model is ready (or an embed_fn was injected),
        False when fastembed is absent or fails to load.  Never raises.
        """
        if self._embed_fn is not None:
            return True
        if self._model is not None:
            return True
        if self._unavailable:
            return False

        try:
            # Lazy import — intentional: importing this module must succeed
            # even when fastembed is not installed.
            from fastembed import TextEmbedding as _TextEmbedding

            # Also make it accessible at the module level for monkeypatching.
            global TextEmbedding  # type: ignore[name-defined]
            TextEmbedding = _TextEmbedding

            self._model = _TextEmbedding(self.model_name)
        except Exception:
            self._unavailable = True
            return False

        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def available(self) -> bool:
        """Return True iff the embedder can produce vectors.

        Triggers a one-time lazy load attempt.  Never raises.
        """
        return self._ensure_model()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` and return a list of float vectors.

        Returns ``[]`` when the embedder is unavailable (fastembed absent or
        failed to load).  Never raises.
        """
        if not self._ensure_model():
            return []

        if self._embed_fn is not None:
            return self._embed_fn(texts)

        # Real fastembed path — coerce numpy/generator to plain float lists.
        return [[float(x) for x in vec] for vec in self._model.embed(texts)]

    @property
    def dim(self) -> int:
        """Return the embedding dimension.

        - Injected embed_fn: derived from ``len(embed_fn([""])[0])`` — fully
          offline; never constructs the real fastembed model.
        - Real fastembed model: derived from a sentinel probe embed of ``[""]``.
        - Unavailable: returns ``_DEFAULT_DIM`` without raising.
        """
        if self._embed_fn is not None:
            result = self._embed_fn([""])
            if result:
                return len(result[0])
            return _DEFAULT_DIM

        if not self._ensure_model():
            return _DEFAULT_DIM

        # Probe the loaded model with an empty string to get the dimension.
        try:
            sentinel = next(iter(self._model.embed([""])))
            return len(sentinel)
        except Exception:
            return _DEFAULT_DIM


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_embedder(root: Path | None = None, *, embed_fn: Callable | None = None) -> Embedder:
    """Return a configured ``Embedder`` instance.

    Args:
        root:     Project root for resolving ``.planning/config.json``.
                  Defaults to ``None`` (resolved relative to cwd at call time).
        embed_fn: Injected callable ``(texts: list[str]) -> list[list[float]]``
                  for testing.  When provided, fastembed is never imported or
                  constructed.

    The model name is resolved via env > config.json > default precedence;
    no model is downloaded at construction time — only on first ``embed()``
    or ``available()`` probe.
    """
    model_name = _resolve_model_name(root)
    return Embedder(model_name=model_name, embed_fn=embed_fn)
