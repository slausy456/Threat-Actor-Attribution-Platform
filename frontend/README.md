# React frontend

React + TypeScript + Vite frontend for the existing FastAPI service. The frontend is a separate app; backend code and response contracts are unchanged.

## Development

Start FastAPI in one terminal:

```bash
cd backend
../.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Create the environment and install backend dependencies from the repository
root first if needed: `python -m venv .venv` followed by
`.venv/bin/python -m pip install -r backend/requirements.txt`. The stylometry
service imports scikit-learn at API startup, so running Uvicorn from a Python
interpreter without the backend requirements installed will make the API exit.

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the UI at `http://localhost:5173` and proxies `/api/*` requests to `http://127.0.0.1:8000/*`. For a separate API host, set `VITE_API_BASE_URL` (the API must allow browser CORS in that deployment).

## Routes

- `/` Overview and candidate leads
- `/search` Persona search
- `/compare` Pair comparison, pillar scores, and evidence
- `/timeline` Dataset activity and persona lifetimes
- `/graph` Candidate relationship constellation
- `/export` JSON, CSV, and Markdown export
- `/background-demo` full-screen animated plasma background preview

The dashboard backdrop uses a procedural React Three Fiber shader with a Three.js renderer and drei helpers. The standalone `/background-demo` route previews it without the dashboard chrome. Mouse movement produces restrained parallax; the canvas is capped at 1.35 device pixel ratio and uses adaptive DPR for slower devices.
