# 260525-o6h — SUMMARY

**Task:** Spike: confirm `claude --print` server-side prompt-cache behavior + document/wire findings.

**Outcome:** Branch B — cache is implicit and automatic; no CLI flag exists; no `BridgeConfig` field added. Documented on `ClaudeBridge`.

## Headline findings

- Anthropic's server-side prompt cache fires for back-to-back `claude --print` subprocesses with overlapping prefixes within the TTL window — confirmed empirically via `usage.cache_read_input_tokens` in `--output-format json`.
- Call 2 of an identical ~3.4k-token prefix saw **-32% wall-clock** (4.673s → 3.159s) and **-37% API duration** (3,884ms → 2,441ms).
- 1-hour TTL is active on this account (`ephemeral_1h_input_tokens: 20757`).
- No per-call cache flag exists on `claude --print` (v2.1.150). The only knobs are env vars (`ENABLE_PROMPT_CACHING_1H`, `FORCE_PROMPT_CACHING_5M`) and `--exclude-dynamic-system-prompt-sections` (n/a for FlowState — we pass `--system-prompt`).

## Implication for FlowState

Quick task **260525-m9v** already produced the conditions needed to benefit: the orchestrator builds one `prior_knowledge` block and threads the byte-identical string into every step's prompt within a single pipeline run. Server-side caching reuses it across Strategy/GSD/discipline calls inside the TTL — zero additional code required.

## Artifacts

- Findings: `.planning/quick/260525-o6h-spike-confirm-claude-print-server-side-p/260525-o6h-SPIKE.md`
- Docstring: `flowstate/bridge.py` (module docstring extended with "Prompt cache behavior" paragraph)

## Commits

- `1086a30` docs(quick/260525-o6h): SPIKE — claude --print prompt cache investigation
- `996049b` docs(quick/260525-o6h): document implicit prompt cache behavior on ClaudeBridge

## Verification

- Full test suite: 297 passing, 91.41% coverage (≥80% gate satisfied)
- No new runtime dependencies
- API spend: ~2 haiku calls, ~$0.01 total

## Plan reference

CAG considerations: `/Users/jhogan/.claude/plans/consider-how-and-if-witty-grove.md` §2 (now complete).
