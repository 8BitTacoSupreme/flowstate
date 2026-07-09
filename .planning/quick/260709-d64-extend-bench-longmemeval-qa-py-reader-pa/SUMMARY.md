---
phase: 260709-d64
plan: "01"
status: complete
---

See 260709-d64-SUMMARY.md for full details.

LongMemEval reader path upgraded: `_READER_INSTRUCTION` constant with `{question_date}` framing, `--reader-provider openai` routing through `_openai_chat`, upfront canary guard before scoring loop, reader model auto-upgrade (sonnet → gpt-4-turbo). Default claude/claude path byte-identical. 32 tests passing, 92% coverage.
