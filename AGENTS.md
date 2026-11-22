# AGENTS.md

## Project Description

**Sovren** is a personal admin assistant built on a lightweight, framework-free Python agent runtime. It combines a multi-turn tool-calling orchestrator, semi-deterministic state workflows for untrusted inputs (such as email ingestion), scoped subagents, a deny-by-default policy engine, and checkpointed human-in-the-loop approvals, backed by a FastAPI API and a React + Vite frontend.

- **Detailed Architecture:** Refer to `DESIGN.md` for the heavy architecture and system design.
- **Alignment Note:** `DESIGN.md` and the codebase currently have contradictions and non-alignment; both are in the process of being updated. Treat `DESIGN.md` as directional architecture context and verify implementation details directly against the code when needed.

## Behavioral Preferences

- **Context Source:** The tech stack, environment setup, tools used, and a top-level directory structure will be provided in `AGENTS.md` itself. Do not infer or run bash commands to gather environment context or waste time checking virtual environments or libraries. For Python projects, refer to `pyproject.toml`.

- **Focused Execution & Multi-File Changes:** When I give you a task, focus on that specific task without deviating or doing unnecessary work. If a requirement is genuinely ambiguous, ask a brief clarifying question instead of guessing. For architectural or multi-file changes, briefly outline the plan and wait for my approval before writing code. Keep the explanation simple and concise, focusing on the high-level overview and system behavior—do not list file-by-file changes.

- **Simple Tasks or Changes:** Execute them quickly and immediately.

- **Coding Preferences:** I prefer minimal implementations of core modules. Do not add exception handling or other non-functional features in the initial iterations.

- **Tool Naming Convention:** All capabilities (atomic tools, workflow pipelines, and subagent spawning) are wired as standard `Tool` instances using consistent `snake_case` names:
  - **Read tools (`LEVEL_0`):** `<domain>_<read_verb>` (`list`, `get`, `search`) — e.g. `todo_list`, `email_get`
  - **Action / write tools (`LEVEL_2+`):** `<domain>_<action_verb>` (`create`, `update`, `delete`, `send`) — e.g. `todo_create`, `email_send`
  - **Pipeline / workflow tools:** `workflow_<name>` — e.g. `workflow_ingest_emails`
  - **Subagent spawner:** `spawn_subagent`

## Tech Stack and Setup Information

### Backend (`backend/`)

- **Runtime & Package Manager:** Python `>=3.12`, managed with `uv` (`backend/pyproject.toml`, `backend/uv.lock`).
- **Frameworks & Libraries:** FastAPI, Uvicorn, SQLModel + `aiosqlite` (SQLite), `openai` SDK, Pydantic / `pydantic-settings`, `sse-starlette`.
- **Dev & Testing:** `pytest`, `pytest-asyncio`, `httpx`, `ipykernel`.
- **Configuration:** Environment variables loaded from `backend/.env` via `app/config.py` (`DATABASE_URL`, `OPEN_ROUTER_API_KEY`, `MODEL`, `ENVIRONMENT`).
- **Commands (run from `backend/`):**
  - Start API server: `uv run uvicorn app.main:app --reload`

### Frontend (`frontend/`)

- **Stack:** React 19, TypeScript, Vite 8, Tailwind CSS v4 (`@tailwindcss/vite`), `oxlint` (`frontend/package.json`).
- **Dev Setup:** Vite dev server on port `5173`, proxying `/api` to `http://localhost:8000` (`frontend/vite.config.ts`).

## Directory Structure (High-Level Overview)

```text
sovren-dev/
├── AGENTS.md                  # Agent instructions, tech stack, and repo overview
├── DESIGN.md                  # Heavy architecture & system design (currently being aligned with code)
├── README.md
├── backend/
│   ├── pyproject.toml         # Python dependencies & pytest config
│   ├── uv.lock
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint, lifespan, CORS, router mounting
│   │   ├── config.py          # pydantic-settings configuration
│   │   ├── api/               # HTTP & SSE API routes
│   │   ├── approval/          # Human-in-the-loop approval manager
│   │   ├── core/              # Core models/schemas and LLM client
│   │   ├── db/                # SQLite/SQLModel database setup & ORM models
│   │   ├── events/            # Event bus for real-time updates (SSE)
│   │   ├── features/          # Predefined workflows (e.g., email triage)
│   │   ├── policy/            # Deny-by-default policy engine
│   │   ├── quarantine/        # Deterministic sanitization for untrusted inputs
│   │   ├── runtime/           # Orchestrator, state graph, subagent runner, tool runner
│   │   └── tools/             # Tool registry and built-in tools
│   └── notebooks/             # Scratch/experimental notebooks
└── frontend/
    ├── package.json           # Frontend dependencies & scripts
    ├── vite.config.ts         # Vite + Tailwind config & /api dev proxy
    ├── index.html
    ├── public/
    └── src/                   # React + TypeScript app (App.tsx, api.ts, types.ts)
```
