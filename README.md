# Handrail

Computer-use automation for legacy back-office apps: an LLM discovers a flow once, it is saved
as a typed capability artifact, and deterministic replay runs it in production.

**Status:** phase 1 of 9 (foundations): artifact and result schema, redaction, structured
logging, configuration, CI.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
cp .env.example .env    # keys are only needed from phase 6 (discovery)
```

## Checks

```
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run handrail schema check
```

Tests make no outbound network calls (enforced with `pytest-socket`); only localhost is allowed.

## Running without live services

Everything in phase 1 runs offline.

```
uv run handrail artifact validate artifacts/mockbank.member.read_savings_balance/1.0.0.json
uv run handrail schema export     # regenerate /schema after changing the models
```

## Demo

Added in phase 8: discover a goal, replay the resulting artifact, a failing replay, and a
human handoff.

## Layout

| Path | Contents |
| --- | --- |
| `src/handrail/schema/` | Artifact and result models, hashing, lifecycle, JSON Schema export |
| `src/handrail/redaction/` | PII patterns, registered-value masking, structlog processor |
| `src/handrail/obs/` | JSONL events with correlation IDs |
| `src/handrail/config.py` | Settings from environment / `.env` |
| `schema/` | Published JSON Schema (checked in CI) |
| `artifacts/<id>/<version>.json` | Capability artifacts |
