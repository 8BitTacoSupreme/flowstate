---
status: complete
phase: quick-260619-nfe
plan: 01
subsystem: bench
tags: [grounding, rgb, embeddings, cosine-similarity, hard-negatives, fastembed]
completed: 2026-06-19
---

# Quick Task 260619-nfe: Hard-Negative Distractor Selection

**Opt-in `--hard-negatives` flag for RGB mode reorders distractors topically-nearest-first via cosine similarity, with soft-fail to id-order and fully offline tests using injected fake embed_fn.**

See `260619-nfe-SUMMARY.md` for full details.

## Commits

- `484b433` test(260619-nfe-01): add failing tests for _rank_by_similarity and embed_fn-aware _rgb_distractors (RED)
- `00ab722` feat(260619-nfe-01): add _rank_by_similarity and embed_fn-aware _rgb_distractors (GREEN)
- `cb67d45` test(260619-nfe-02): add failing tests for --hard-negatives flag and hard_negatives JSON key (RED)
- `831def6` feat(260619-nfe-02): thread embed_fn through RGB axes, add --hard-negatives CLI flag (GREEN)
