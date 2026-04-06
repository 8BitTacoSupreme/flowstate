# Frameworx

## What This Is

Frameworx is a CLI tool that translates natural language prompts into validated Flink SQL queries. It connects to Kafka clusters and Schema Registry to discover available streams and their schemas, then uses LLM-powered generation to produce correct Flink SQL — letting anyone query streaming data without learning Flink SQL syntax. Initial target: Confluent Cloud.

## Core Value

A user can describe what they want from their streaming data in plain English and get a working Flink SQL query on the first attempt.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Connect to Confluent Cloud using API key/secret
- [ ] Discover Kafka topics and fetch schemas from Schema Registry
- [ ] Translate natural language prompts into Flink SQL
- [ ] Validate generated SQL against known schemas before submission
- [ ] Submit validated queries to Flink cluster and return results
- [ ] Self-healing retry: feed Flink errors back to LLM for auto-correction
- [ ] "Explore" mode: generate + explain SQL without deploying
- [ ] "Ship" mode: generate + validate + deploy to Flink
- [ ] Track first-attempt success rate as north star metric

### Out of Scope

- Self-managed Kafka/Flink clusters — Confluent Cloud only for v1
- Web UI or API server — CLI-only for v1
- OAuth/SSO — API key authentication only
- Kafka Streams or ksqlDB generation — Flink SQL only for v1
- Real-time monitoring or alerting rules — query generation only
- Mobile or desktop app

## Context

- **Problem**: Flink SQL has a brutal learning curve. Engineers must know topic names, navigate Schema Registry, understand Flink SQL dialect (watermarks, temporal joins, windowing), deploy to a cluster, and debug serialization issues. This gates streaming analytics behind the few people who know Flink SQL.
- **Insight**: LLMs can generate correct Flink SQL reliably when given explicit schema context — the context window is bounded and schemas are explicit.
- **Beachhead**: Confluent Cloud simplifies auth (single API key covers Kafka + Schema Registry), provides managed Flink with SQL submission API, and has rich, well-structured schema context.
- **Kill signal**: If first-attempt success rate on real-world schemas stays below 50% after 4 weeks, pivot to schema-aware query builder UI with LLM-assisted autocomplete.
- **Existing codebase**: This repo contains FlowState (the GrandSlam Orchestrator) — a Python CLI that unifies four agentic frameworks. Frameworx builds as a new project within the same development environment but is a separate product.

## Constraints

- **Tech stack**: Python CLI (Click + Rich), LLM via API (Claude/GPT-4), Confluent Cloud APIs
- **Auth simplicity**: Single Confluent Cloud API key/secret must be the only credential required for v1
- **Validation-first**: The schema-aware validation layer must be built before any UX polish — broken queries destroy trust
- **LLM agnostic**: Support at minimum Claude and GPT-4 as generation backends
- **Few-shot required**: Use curated few-shot examples for common Flink SQL patterns, not zero-shot generation

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Confluent Cloud first | Eliminates 60% of integration complexity (single auth, managed Flink, clean SR API) | — Pending |
| Python CLI (Click + Rich) | Matches existing dev environment, fast iteration, familiar tooling | — Pending |
| Explore mode before Ship mode | Build trust by letting users see/approve generated SQL before deployment | — Pending |
| Validation layer before UX | Broken queries destroy trust faster than ugly UX | — Pending |
| Few-shot over zero-shot | Tuned examples for common patterns (filtering, windowed aggregation, stream joins) produce better results | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-05 after initialization*
