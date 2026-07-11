"""Memory-to-wiki distiller — thin re-export shim.

The distiller logic was promoted to the production module
``flowstate/distiller.py`` (Phase 21, D-01): it must import nothing from
``bench/`` so ``flowstate distill`` resolves on an installed wheel. This module
re-exports the promoted API so ``bench``-side callers and existing tests keep
working with no logic duplication.

Invoke via: python -m bench.distiller --root <project-root>
"""

from __future__ import annotations

import sys

from flowstate.distiller import *  # noqa: F403 — surface the full public API
from flowstate.distiller import (
    _ARTICLE_KINDS,
    _WIKI_CORPUS_REL,
    _article_filename,
    _densify,
    _locate_claude,
    _render_article,
    main,
)

__all__ = [
    "_ARTICLE_KINDS",
    "_WIKI_CORPUS_REL",
    "_article_filename",
    "_densify",
    "_locate_claude",
    "_render_article",
    "main",
]


if __name__ == "__main__":
    sys.exit(main())
