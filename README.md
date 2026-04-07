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

This scaffold provides:

- a versioned API entrypoint with `/health` and router scaffolding
- in-memory persistence for uploads and sessions
- mock storage and LLM integrations
- modular engine boundaries for future model swaps
- a lightweight React demo interface

The next step is replacing mock providers with real model and Cloudflare adapters.

cloudflared tunnel --url http://localhost:8001
codex resume 019d636e-11c2-7ff3-94c1-8b2ed7df579e