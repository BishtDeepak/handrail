# Handrail

Computer-use automation for legacy back-office apps: an LLM discovers a flow once, it is saved
as a typed capability artifact, and deterministic replay runs it in production.

**Status:** phases 1-3 of 9 done: foundations (schema, redaction, logging, CI), MockBank
target app with fault injection, and the Playwright surface with locator chains.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run playwright install chromium
cp .env.example .env    # API keys are only needed from phase 6 (discovery)
```

If Chromium is already installed elsewhere, set `BROWSER_EXECUTABLE` in `.env` instead.

## Checks

```
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run handrail schema check
```

Tests make no outbound network calls (enforced with `pytest-socket`); only localhost is allowed.

## Running without live services

Everything so far runs offline.

```
uv run mockbank                   # http://127.0.0.1:8765  (sign in: operator / mockbank-demo)
uv run handrail artifact validate artifacts/mockbank.member.read_savings_balance/1.0.0.json
uv run handrail schema export     # regenerate /schema after changing the models
```

### MockBank

A deliberately legacy member-services app: a frameset shell (`nav` + `main`), table layouts,
inputs without labels or IDs, and no test IDs. Deep links such as `/members/search` return the
frameset with that page in `main`.

- **Members:** `48213` and `36620` (found), `51007` (access denied), `99999` (not found),
  `00000` (app-side validation error). All personal data is synthetic.
- **Flows:** search → member detail (share balances) → open sub-account → review → **Submit**
  (irreversible) → confirmation number.
- **Faults:** toggle by hand at `/__mockbank/`, or via `PATCH /__mockbank/faults` with JSON:
  interstitial and unknown dialogs, slow and transient-503 loads, HTTP 500, blank frame,
  renamed/disabled/duplicated/late buttons, reordered rows, wrong landing page, permission
  denial, hostile off-allowlist content, session expiry, version string.

## Demo

Added in phase 8: discover a goal, replay the resulting artifact, a failing replay, and a
human handoff.

## Layout

| Path | Contents |
| --- | --- |
| `src/handrail/schema/` | Artifact and result models, hashing, lifecycle, JSON Schema export |
| `src/handrail/redaction/` | PII patterns, registered-value masking, structlog processor |
| `src/handrail/obs/` | JSONL events with correlation IDs |
| `src/handrail/surface/` | `Surface` protocol; Playwright implementation; desktop stub |
| `mockbank/` | Target app, fault switches, synthetic seed data |
| `src/handrail/config.py` | Settings from environment / `.env` |
| `schema/` | Published JSON Schema (checked in CI) |
| `artifacts/<id>/<version>.json` | Capability artifacts |
