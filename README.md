# EchoWhale

EchoWhale is an image-grounded English conversation coach. Users upload a real-world photo, the system infers the likely scene, starts a role-based dialogue, and returns learning feedback focused on practical spoken English.

## Repository layout

- `api/`: modular FastAPI backend with scene, coach, feedback, and session engines
- `frontend/`: React + Vite demo client for upload, practice, and history
- `docs/`: product, architecture, and governance documentation
- `tests/`: backend-heavy regression and contract tests
- `tools/`: repo-local governance and collaboration tools

## Quick start

### Backend

```bash
uv sync
uv run uvicorn api.main:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

In development, Vite proxies `/api/*` requests to `http://localhost:8001` by default.
If your backend runs elsewhere, set `VITE_API_PROXY_TARGET` before `npm run dev`.

## Current scope

This repository currently provides:

- a versioned API entrypoint with `/health` and shared response handling
- PostgreSQL-backed auth, media, session, history, and voice-agent persistence paths
- modular `scene / coach / feedback / session` engines with live-provider gates
- a React demo client wired to real upload, session, review, and history flows
- backend-heavy regression tests for contracts, repositories, services, and engine orchestration

The next step is continuing real-provider smoke coverage and system-level integration for the full `upload -> session -> voice -> review -> history` flow.

## Agent Collaboration

EchoWhale uses a repo-local control plane for agent and human collaboration.

### Control plane commands

```bash
uv run python -m tools.agent_ops check
uv run python -m tools.agent_ops render
uv run python -m tools.agent_ops bootstrap feature agent_governance_control_plane --module platform_foundation --owner codex
```

### Source of truth

- `docs/control/agent-control-plane.json`: single source of truth for system/module/feature/test-layer index data
- `docs/control/project-index.md`: human-readable control dashboard with a generated block
- `.codex/README.md`: repo-local agent workspace entry

When control-plane data changes, update the JSON first, then run `render`, then `check`.
