"""Root pytest configuration.

Keep the vendored GSD tree (``flowstate/vendor/``) out of test collection. It is
third-party Node data (JS/mjs/cjs/markdown/JSON), never Python that pytest should
import or run. Excluding it here guarantees no vendored file is ever executed in the
test process (threat T-15-03) and keeps collection fast.
"""

collect_ignore_glob = ["flowstate/vendor/*"]
