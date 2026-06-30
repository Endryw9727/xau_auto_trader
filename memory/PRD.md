# PRD — Research Console (Quantitative Trading Research, READ-ONLY)

## Original Problem Statement
Full-stack "Research Console" for a quantitative trading research system (read-only, no real orders).
Python (FastAPI) backend exposing REST endpoints that call existing Python analysis modules; the real
statistics live in an EXTERNAL Python API connected later via `API_BASE_URL`. Frontend with 5 pages:
Data, Edge Lab, Significance Audit, Bot Diagnostics, AI Research. Significance Audit is the primary
verdict (highlights the `mtc_robust` column). AI Research connects multiple LLMs (Claude, GPT, Kimi)
with per-task routing in REPORT-ONLY mode (models receive only already-computed metrics, explain and
propose hypotheses, never compute stats or send orders). API keys in server-side env vars. Runs
(params + results) persisted in MongoDB. ABSOLUTE CONSTRAINT: the app can never arm execution nor set
`allow_real_live=true`.

## Architecture
- **Backend** FastAPI (`/api` prefix). Acts as a client: `proxy()` forwards to `API_BASE_URL` when set,
  else falls back to realistic MOCK data (`mock_data.py`). No statistical logic is reimplemented here.
  Files: `server.py`, `auth.py` (JWT), `analysis.py` (data/edge/bot/runs), `ai_research.py` (LLM),
  `mock_data.py`, `db.py`.
- **Frontend** React + Tailwind, dark Bloomberg/terminal theme (IBM Plex Mono/Sans). Pages under
  `src/pages/*`, shared `components/widgets.jsx`, `components/Layout.jsx`, `components/SafetyBanner.jsx`.
- **DB** MongoDB collections: `users`, `login_attempts`, `uploaded_instruments`, `runs`, `ai_conversations`.
- **Auth** JWT Bearer (token in body, stored in localStorage `rc_token`). Seeded admin.

## Safety (verified)
- `live_armed` always false; `/api/health` and `/api/safety` hardcode it. `allow_real_live` never settable.
- No arming endpoint exists anywhere. AI system prompt forbids computing stats or recommending live trading.

## Core Requirements (static)
- 5 pages; Significance Audit hero with highlighted `mtc_robust`.
- Endpoints: health, safety, instruments, data/{upload-csv,synthetic,fetch-yahoo},
  edge/{session-scan,ny-conditional,overnight,significance-audit}, bot/{rejection-taxonomy,
  market-structure,quality-review,demo-readiness}, runs, ai/{config,chat,conversations}.
- Multi-LLM routing (Claude Sonnet 4.6 + GPT-5.4/mini enabled; Kimi disabled placeholder).
- Run persistence; report-only AI.

## Implemented (2026-06-30)
- JWT auth (login/register/me/logout, brute-force lockout, seeded admin) — DONE.
- Mock/proxy analysis layer + all REST endpoints with run persistence — DONE.
- 5 frontend pages, terminal theme, persistent LIVE DISARMED banner — DONE.
- AI Research report-only multi-LLM (real Claude/GPT via Emergent Universal Key) — DONE.
- Tested: 26/26 backend pytest pass (incl. real LLM call); frontend e2e verified.

## Backlog / Next
- **P1**: Connect real external research API (set `API_BASE_URL`); verify proxy passthrough against real schemas.
- **P1**: Enable Kimi (Moonshot) once a Moonshot API key is provided.
- **P2**: Streaming AI responses (SSE) + retry/backoff on transient 502.
- **P2**: Run history viewer page (diff/compare runs); export audit table to CSV.
- **P2**: Per-user run isolation/filtering and pagination on /api/runs.
