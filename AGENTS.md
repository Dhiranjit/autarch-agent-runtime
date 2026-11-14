# Agent Guidelines

- **Execution effort:** If I have asked something simple and direct, do not over analyze and perform/answer the query swiftly.
- **Strict Scope:** Touch only files directly relevant to the current task. Do not refactor unrelated code, add unsolicited features, or reformat untouched files.
- **YAGNI & Simplicity:** Write minimal, maintainable code that solves the immediate problem. Avoid speculative abstractions, premature generic patterns, or over-engineering for hypothetical future needs.
- **Execution Workflow:**
  - Direct fixes / local changes: Implement immediately without ceremony.
  - Structural / multi-file architectural additions: Outline a brief bulleted plan first and wait for approval.
- **Context & Conventions:** Reference [DESIGN.md](DESIGN.md) for architecture. Inspect manifests (`pyproject.toml`, `package.json`) before assuming dependencies.

---

## Tech Stack

### Backend

- **Language / Runtime:** Python `>=3.12`
- **Package & Environment Manager:** `uv`
- **Framework:** FastAPI (`uvicorn`)
- **Database / ORM:** SQLite (`aiosqlite`, WAL mode enabled) + SQLModel
- **AI / LLM:** OpenAI SDK (`AsyncOpenAI` via OpenRouter with Structured Outputs via `beta.chat.completions.parse`)
- **Validation:** Pydantic v2 & `pydantic-settings`
- **Streaming:** `sse-starlette` (Server-Sent Events)
- **Testing:** `pytest`, `pytest-asyncio`, `httpx`

### Frontend

- **Framework / Runtime:** React 19 + TypeScript
- **Build Tool:** Vite (`@vitejs/plugin-react`)
- **Styling:** Tailwind CSS v4 (`@tailwindcss/vite`)
- **Linter:** `oxlint`
- **Package Manager:** `npm`

---

## Directory Structure

```text
sovren-dev/
├── AGENTS.md                  # Project rules, tech stack, and conventions
├── DESIGN.md                  # System architecture, schemas, and pipeline design
├── backend/
│   ├── app/
│   │   ├── api/               # FastAPI endpoints & SSE streams (router.py)
│   │   ├── approval/          # Human-in-the-loop approval manager (manager.py)
│   │   ├── core/              # Shared domain models, enums & LLMClient (models.py, llm.py)
│   │   ├── db/                # SQLModel database session & schema (database.py, models.py)
│   │   ├── events/            # In-memory pub/sub event bus (bus.py)
│   │   ├── features/          # Domain feature workflows (email_triage.py)
│   │   ├── policy/            # Deterministic tool risk policy engine (engine.py)
│   │   ├── quarantine/        # Untrusted email sanitization & extraction (extractor.py)
│   │   ├── runtime/           # Core AgentRuntime control loop (agent.py)
│   │   ├── tools/             # Tool gateway & mock tool providers (builtin.py, registry.py)
│   │   ├── config.py          # App settings & environment variables (.env)
│   │   └── main.py            # FastAPI entry point & lifespan
│   ├── tests/                 # Pytest test suite (conftest.py, test_vertical_slice.py)
│   ├── pyproject.toml         # Backend dependencies & uv config
│   └── uv.lock
└── frontend/
    ├── src/
    │   ├── components/        # React components (ApprovalCard, AuditTimeline, etc.)
    │   ├── api.ts             # Backend API client & SSE consumer
    │   ├── types.ts           # Frontend TypeScript type definitions
    │   ├── App.tsx            # Main application UI container
    │   └── main.tsx           # React DOM root entry point
    ├── package.json           # Frontend dependencies & npm scripts
    ├── tsconfig.json
    └── vite.config.ts
```

---

## Common Commands

### Backend

```bash
# Navigate to backend directory
cd backend

# Run the development server
uv run uvicorn app.main:app --reload --port 8000

# Run tests
uv run pytest

# Add / install dependencies
uv add <package-name>
uv add --dev <package-name>
```

### Frontend

```bash
# Navigate to frontend directory
cd frontend

# Run local development server
npm run dev

# Run type check and production build
npm run build

# Run linter
npm run lint
```
