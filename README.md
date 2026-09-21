# Al Dente Company Brain

Hackathon project (Coding Agent Hackathon, June 2026): the **company brain** of Al Dente S.r.l., a fictional pasta maker selling to supermarkets, distributors and restaurants. You ask a question in plain English. An LLM agent decides which company data it needs (CRM, ERP, call transcripts, knowledge base), calls those sources, and returns a grounded answer. It can also return a generated artifact: an HTML deck, or a docx/pptx/pdf/xlsx file.

**Result:** the scored dry-run reached **135/160** with **0 wrong answers** (calls 40, erp 35, crm 30, kb 30).

## Architecture

```
            ┌─────────────────────── frontend/ (React + Vite) ───────────────────────┐
            │  Command bar · Orchestration hub · Knowledge graph · Executive memo    │
            └───────────────┬───────────────────────────────┬────────────────────────┘
                     POST /ask                        GET /api/graph
            ┌───────────────▼───────────────────────────────▼────────────────────────┐
            │  backend/main.py (FastAPI)                                              │
            │    agent/loop.py      tool-calling loop, wall-clock budget, verticale  │
            │    agent/tools.py     13 tools (OpenAI function-calling schemas)       │
            │    agent/clients.py   Al Dente API clients, full pagination            │
            │    agent/kb.py        BM25 over whole documents in data/kb/            │
            │    agent/artifacts.py docx / pptx / pdf / xlsx + HTML decks            │
            └───────┬──────────────────────────────┬─────────────────────────────────┘
                    │                              │
        Al Dente mock APIs (crm / erp / calls)   data/kb/*.md (35 docs)
```

- **Agent loop:** an OpenAI-compatible tool-calling loop (Regolo.ai `qwen3-coder-next`). Every LLM call has a hard wall-clock deadline, so each answer comes back within the 30 s limit. Aggregates (totals, counts, group-bys) are computed in Python, not by the model.
- **Tools:** `search_customers`, `get_customer`, `get_opportunities`, `get_orders`, `get_production_orders`, `get_inventory`, `get_bom`, `get_suppliers`, `get_shipments`, `get_calls`, `get_call_transcript`, `count_transcript_matches`, `search_kb`.
- **Honesty on traps:** before answering, the agent checks that the customer, lot or figure asked about exists. If it doesn't, the answer says so explicitly (for example, "there is no customer named X in the CRM") instead of inventing a value.
- **Knowledge base:** BM25 retrieval that returns whole documents rather than chunks, so shelf life and allergens stay together.
- **Artifacts:** HTML decks are returned inline in `answer`. Binary files are written to `backend/static/files/` and returned as an absolute `artifact_url`. If the LLM is slow, a template deck is built from the data already gathered.
- **UI:** a 3-panel dashboard with a React Flow knowledge graph (customers → products → raw materials → suppliers, plus KB documents) and an answer panel that keeps a chat history. Clicking a tool tile filters the graph, and clicking a node puts its name and ID into the question box.

## `/ask` contract (frozen)

```jsonc
// POST /ask
{ "question": "How many open opportunities does CUST-0132 have?" }

// 200 OK
{
  "answer": "...",
  "sources": ["crm/opportunities"],
  "verticale": "crm",          // crm | erp | calls | kb
  "artifact_url": null         // absolute URL only for docx/pptx/pdf/xlsx
}
```

## Repository layout

```
.
├── AGENTS.md                # Project spec + hard constraints (read by AI coding agents)
├── backend/                 # Everything that gets deployed (Railway)
│   ├── main.py              # FastAPI app: /ask, /api/graph, /health, static UI
│   ├── agent/               # Agent loop, tools, API clients, KB retrieval, artifacts
│   ├── data/kb/             # 35 company documents (RAG corpus)
│   ├── static/              # Built UI (output of frontend build) + /files/ artifacts
│   ├── pyproject.toml       # Python deps (uv)
│   ├── railway.json         # Railway config (Railpack)
│   └── .env.example         # Env var template
├── frontend/                # React + TypeScript + Tailwind + React Flow UI
│   └── src/                 # components/, hooks/, lib/, types/
├── docs/
│   ├── PROGRESS.md          # Build log, decisions, scoring history
│   ├── FRONTEND_SPEC.md     # UI specification
│   └── challenge/           # Original hackathon brief, API reference, sample questions,
│                            # deploy + Docker guides, starter README
├── docker-compose.dev.yml   # Optional dev container
├── Dockerfile.dev
└── package.json             # Root convenience scripts (dev:ui, build:ui, deploy)
```

## Run locally

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# Backend (serves the built UI at http://localhost:8000)
cd backend
cp .env.example .env         # fill in LLM_API_KEY, MODEL, MOCK_API_TOKEN, ...
uv sync
uv run uvicorn main:app --reload --port 8000

# Frontend with hot reload (optional, proxies API calls to :8000)
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

The frontend build writes into `backend/static/`:

```bash
npm run build:ui             # from repo root
```

### Environment variables (`backend/.env`)

| Var | Purpose |
| --- | --- |
| `LLM_BASE_URL` | OpenAI-compatible endpoint (Regolo.ai / Mistral) |
| `LLM_API_KEY` | LLM provider key |
| `MODEL` | Model id (must support tool calling) |
| `MOCK_API_BASE_URL` | Al Dente mock API base URL |
| `MOCK_API_TOKEN` | Personal mock-API token |
| `PUBLIC_BASE_URL` | Public backend URL, used to build `artifact_url` |

## Deploy

```bash
npm run deploy               # builds the UI into backend/static/, then `railway up` from backend/
```

See [docs/challenge/DEPLOY.md](docs/challenge/DEPLOY.md) for the full Railway guide.

## Tech stack

FastAPI · OpenAI SDK (Regolo.ai) · rank-bm25 · httpx · python-docx / python-pptx / fpdf2 / openpyxl · React 19 · Vite · Tailwind v4 · React Flow · Framer Motion · Railway
