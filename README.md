# EchoWhale

EchoWhale is an image-grounded English conversation coach. Users upload a real-world photo, the system infers the likely scene, starts a role-based dialogue, and returns learning feedback focused on practical spoken English.

## Repository layout

- `api/`: modular FastAPI backend with scene, coach, feedback, and session engines
- `frontend/`: React + Vite demo client for upload, practice, and history
- `docs/`: product and architecture documentation
- `tests/`: backend test scaffolding

## Quick start

### Backend

```bash
uv sync
uv run uvicorn api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000`.

## Current scope

This scaffold provides:

- a versioned API entrypoint with `/health` and router scaffolding
- in-memory persistence for uploads and sessions
- mock storage and LLM integrations
- modular engine boundaries for future model swaps
- a lightweight React demo interface

The next step is replacing mock providers with real model and Cloudflare adapters.
