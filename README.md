# Reseva

**An autonomous AI restaurant-reservation assistant.** Tell Reseva what you want in plain English ("Book Bella Italia Mayfair for 2 tomorrow at 8pm") and it finds the restaurant, checks availability, asks for your approval, makes the booking, and emails you a confirmation. You can also change or cancel a reservation by its ID.

Reseva is built on [LangGraph](https://langchain-ai.github.io/langgraph/) with Claude as the language model. Every action that changes something (booking, changing, cancelling) pauses for explicit human approval first.

**Live demo:** https://reseva-ac385db28e395ffbba1179920844be59.us.langgraph.app/app/

> **Status:** working demo. The restaurant catalogue is four mock restaurants in Mayfair, so bookings are stored in Reseva's own database and are not sent to any real restaurant.

## Features

- **Natural-language booking.** Search by cuisine and area, then book in a conversation.
- **Deterministic availability checks.** Availability is always checked by code for the exact restaurant, date, time and party size, and the model never guesses it.
- **Alternative times.** If a slot is full, Reseva offers nearby times at the same restaurant.
- **Human approval for every change.** Booking, modifying and cancelling each pause on an approval card before anything is written.
- **Email confirmations** for bookings, changes and cancellations (via [Resend](https://resend.com)).
- **Tool use through MCP.** Restaurant tools are exposed by an [MCP](https://modelcontextprotocol.io) server.
- **Persistent data.** Reservations are stored in PostgreSQL, and conversation state is persisted by the deployment, so a chat can be paused and resumed.
- **Tracing.** Runs are traced in LangSmith.

## How it works

Here is the path a request takes:

1. You type a request in the web app (React).
2. The web app sends it to the API (FastAPI) at `/api/v1/chat`.
3. The API passes it to the LangGraph agent, which runs inside the same LangSmith deployment.
4. The agent uses Claude to understand the request and decide what to do. When it needs restaurant information, it calls tools provided by the MCP restaurant server, which also runs inside the agent. That server reads and writes the PostgreSQL database (Neon).
5. When the agent reaches a step that changes something (a booking, a change or a cancellation), it pauses and sends an approval question back to the web app. Your answer goes to `/api/v1/chat/{id}/resume`, and the agent carries on.
6. After a booking, change or cancellation, the agent sends you a confirmation email through Resend.

The agent and the web app are served from a single LangSmith deployment: FastAPI routes are attached to the agent server (`http.app` in `langgraph.json`), and the built React app is served from the same address, so there is no CORS to configure in production.

### The agent

An outer graph (`agent/advanced_graph.py`) wraps the core reservation graph (`agent/graph.py`):

1. **Load memory and plan.** Load saved preferences (optional) and draft a short plan for the request.
2. **Run the core reservation graph.** Extract the request into structured state (restaurant, date, time, party size, intent), route deterministically, and let Claude call the search and availability tools.
3. **Evaluate and adapt.** Check whether the goal was met and retry or adjust if not.

Inside the core graph, a booking goes through three gates, in order:

1. **Availability** is confirmed for the exact slot.
2. **Approval card.** The graph pauses with `interrupt()` and resumes only on an explicit yes.
3. **Customer email** is collected, then the reservation is created and a confirmation email is sent.

Claude is deliberately **not** given the `create_reservation` tool. Only the graph can create reservations, and only after approval.

### MCP tools

`mcp_servers/restaurant_server.py` exposes `search_restaurants`, `check_availability`, `get_alternative_times`, `create_reservation`, `get_reservation`, `modify_reservation` and `cancel_reservation`. The agent calls them in-process (`agent/mcp_client.py`), so there is no subprocess to manage.

## Tech stack

| Layer | Technology |
| --- | --- |
| Agent | LangGraph, LangChain, Claude (`claude-sonnet-4-5`) |
| Tools | MCP (Python SDK) |
| API | FastAPI |
| Database | PostgreSQL (Neon), SQLAlchemy, psycopg 3 |
| Email | Resend |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Hosting and tracing | LangSmith Deployment |

## Project structure

```
agent/          LangGraph agent: core graph, advanced wrapper, state, Claude setup,
                request extraction, in-process MCP client, deployment entrypoint
mcp_servers/    MCP restaurant server (search, availability, booking tools)
api/            FastAPI routes (/api/v1/chat, /api/v1/chat/{id}/resume, health)
database/       SQLAlchemy models, repositories, init and seed scripts
integrations/   Restaurant provider interface and mock provider
frontend/       React + Vite web app
static_app/     Built frontend, served by the deployment at /app/
tests/          Test suite
langgraph.json  Deployment config (graph + FastAPI app)
```

## Getting started

### Prerequisites

- Python 3.11
- A current Node.js LTS release
- A PostgreSQL database (a free [Neon](https://neon.tech) project works well)
- API keys for [Anthropic](https://console.anthropic.com), [LangSmith](https://smith.langchain.com) and [Resend](https://resend.com)

### 1. Install

```bash
git clone <your-repo-url>
cd reseva

python -m venv .venv
source .venv/bin/activate        # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### 2. Configure

Copy `.env.example` to `.env` and fill in the values.

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude |
| `DATABASE_URL` | PostgreSQL connection string (`?sslmode=require` for Neon) |
| `LANGSMITH_API_KEY` | LangSmith tracing and API access |
| `LANGSMITH_TRACING` | Set to `true` to trace runs |
| `LANGSMITH_PROJECT` | LangSmith project name |
| `RESEND_API_KEY` | Sending confirmation emails |
| `RESEND_FROM_EMAIL` | Verified sender address in Resend |
| `RESEND_FROM_NAME` | Sender display name |
| `LANGGRAPH_API_URL` | URL of a deployed agent (used by the API when running locally) |
| `ALLOWED_ORIGINS` | Optional. Comma-separated origins allowed by CORS when running locally |
| `RATE_LIMIT_PER_MINUTE` | Optional. Requests per visitor per minute (default 20) |
| `RESEVA_IN_PROCESS` | Set to `1` only in the deployment's environment (see Deployment) |

The frontend reads `VITE_API_BASE_URL` from `frontend/.env.local` (for example `http://127.0.0.1:8000`) in development. The production build leaves it empty so it calls its own address.

### 3. Set up the database

```bash
python -m database.init_db    # create tables
python -m database.seed       # add the four mock restaurants
```

### 4. Run locally

The API talks to a deployed agent, so set `LANGGRAPH_API_URL` and `LANGSMITH_API_KEY` in `.env` first.

```bash
uvicorn api.main:app --port 8000
```

Then either open `http://127.0.0.1:8000/app/` (serves the built frontend from `static_app/`), or run the frontend dev server:

```bash
cd frontend
npm run dev
```

### 5. Run the tests

```bash
python -m pytest tests/<file>.py
```

Many tests use PostgreSQL and read `DATABASE_URL`, so point it at a test database, not production.

## Deployment

Reseva deploys as a single LangSmith Deployment that serves the agent, the API routes and the web app.

1. Put the production values in `.env.production` (this file is git-ignored) and add `RESEVA_IN_PROCESS=1`.
2. Set up the production database once: `python -m database.init_db` then `python -m database.seed`, with `DATABASE_URL` pointing at it.
3. Rebuild the frontend and copy it into `static_app/`:
   ```bash
   cd frontend && npm run build && cd ..
   rm -rf static_app && cp -r frontend/dist static_app
   ```
4. Deploy:
   ```bash
   langgraph deploy
   ```
5. The app is served at `<deployment-url>/app/`.

`langgraph.json` points `graphs.reseva` at `agent/deployment.py` and `http.app` at `api/main.py:app`.

## Design notes

- **Approval before action.** Writes happen only after an explicit approval resumes the paused graph. The web app sends `true` or `false`, and LangSmith Studio accepts the text `yes`.
- **In-process MCP.** The MCP server runs inside the agent process. An earlier version launched it as a subprocess, which failed to start on the hosted platform.
- **Public API, limited blast radius.** The deployment exposes only `/app/` and `/api/v1/*` for the web app. A simple per-visitor rate limit protects model spend.

## Known limitations

- Restaurants and availability are mock data (four restaurants, fixed slots).
- Long-term, per-user memory is implemented in the code but switched off in production, because the web app does not yet identify individual users.
- There is no user login. Anyone with a reservation ID can look up, change or cancel that reservation.
- The in-memory rate limit is best-effort and resets when the server restarts.

## Roadmap

- Connect a real reservation provider through `integrations/`
- User accounts, and per-user memory
- Custom domain
- Automated tests that run without a database