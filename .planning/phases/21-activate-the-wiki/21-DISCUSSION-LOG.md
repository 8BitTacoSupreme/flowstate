# Phase 21: Activate the Wiki - Discussion Log

> **Audit trail only.** Not consumed by downstream agents (they read CONTEXT.md). Preserves the auto-mode selections.

**Date:** 2026-07-11
**Phase:** 21-activate-the-wiki
**Mode:** `--auto` (fully autonomous — all gray areas auto-selected to the recommended option, single pass, no user prompts)

---

All gray areas selected automatically (`[--auto] Selected all gray areas`). Each recommended default chosen without AskUserQuestion:

| Gray Area | Question | Selected (recommended default) |
|-----------|----------|--------------------------------|
| Distiller location (WIKI-03) | Where does the promoted distiller live? | Promote `bench/distiller.py` → `flowstate/distiller.py`; bench re-imports (no duplication) → **D-01/D-02** |
| Distill trigger (WIKI-03, scope fence) | Explicit command vs auto-at-end-of-run? | Explicit `flowstate distill` only; do NOT auto-invoke in `run_pipeline` (honors ROADMAP deferred fence) → **D-03** |
| Staleness signal (WIKI-03) | How is "regenerate only when memory changed" detected? | Mirror `pack.py`: `install_manifest kind="wiki"`, `memory.db` mtime vs manifest `created_at`; `is_wiki_stale` helper → **D-04** |
| Opt-in wiring (WIKI-04) | Flag name/default + how to include the layer | `wiki_layer` bool, default false; flag-off → `include_layers=None` (byte-identical); flag-on → full standard set ∪ `{"wiki"}`, NOT just `{"wiki"}` (else standard layers drop) → **D-05/D-06** |
| Degradation (WIKI-05) | Behavior when `[semantic]` absent | No-op + one-time warning naming `pip install flowstate[semantic]`; never crash → **D-07** |
| Dogfood test (WIKI-06) | Smoke-test shape + acceptance | Integration test against real `memory.db`; assert layer fires (corpus globbed + top-k injected), run green; skip gracefully if no corpus/semantic. Acceptance = "layer fires," not quality → **D-08** |

## Deferred Ideas

- Auto-distill at the end of every `run_pipeline` — deferred (ROADMAP fence); explicit `flowstate distill` ships this phase.
