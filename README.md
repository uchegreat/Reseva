<div align="center">

# Reseva

**An AI restaurant-reservation assistant that books, changes and cancels tables through natural conversation.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-agent-1C3C3C)
![Claude](https://img.shields.io/badge/Claude-Sonnet_4.5-D97757)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)

**[Live demo](https://reseva-ac385db28e395ffbba1179920844be59.us.langgraph.app/app/)**

</div>

---

## Contents

1. [Overview](#overview)
2. [Features](#features)
3. [How a request flows through the system](#how-a-request-flows-through-the-system)
4. [The agent in detail](#the-agent-in-detail)
5. [MCP restaurant tools](#mcp-restaurant-tools)
6. [Data model](#data-model)
7. [API reference](#api-reference)
8. [Frontend](#frontend)
9. [Project structure](#project-structure)
10. [Configuration](#configuration)
11. [Local development](#local-development)
12. [Testing](#testing)
13. [Deployment with the LangSmith CLI](#deployment-with-the-langsmith-cli)
14. [Security and privacy](#security-and-privacy)
15. [Troubleshooting](#troubleshooting)
16. [Design decisions](#design-decisions)
17. [Known limitations](#known-limitations)
18. [Roadmap](#roadmap)

## Overview

Reseva lets a person say what they want in plain English, for example *"Book Bella Italia Mayfair for 2 people tomorrow at 8pm"*. The agent finds the restaurant, checks that the exact slot is available, shows a summary for approval, collects an email address, creates the reservation and sends a confirmation email. A reservation can later be changed or cancelled by its ID, with the same approval step each time.

The agent is built with [LangGraph](https://langchain-ai.github.io/langgraph/) and uses Claude as its language model. Everything that changes data (a booking, a change or a cancellation) pauses for explicit human approval before it happens.

> **Status:** working demo. The catalogue is four mock restaurants in Mayfair, London. Reservations are stored in Reseva's own database and are not sent to any real restaurant.

## Features

- **Natural-language booking.** Search by cuisine and area, pick a restaurant, give a date, time and party size, all in conversation.
- **Deterministic availability checks.** Availability is checked by code for the exact restaurant, date, time and party size. The language model never decides whether a table is free.
- **Alternative times.** If a slot is taken, the agent offers other times at the same restaurant and does not switch restaurants unless asked.
- **Human approval for every change.** Booking, modifying and cancelling each stop on an approval card first.
- **Email confirmations** for bookings, changes and cancellations, sent with [Resend](https://resend.com).
- **Tools over MCP.** Restaurant operations are exposed as [Model Context Protocol](https://modelcontextprotocol.io) tools.
- **Pausable conversations.** Conversation state is persisted by the deployment, so a chat can pause for approval and resume.
- **Tracing.** Every run is traced in LangSmith.
- **One deployment.** The agent, the API routes and the web app are served together from a single LangSmith Deployment.

## How a request flows through the system

1. The person types a request in the web app (React).
2. The web app sends it to the API (FastAPI) at `POST /api/v1/chat`.
3. The API passes it to the LangGraph agent, which runs inside the same LangSmith deployment.
4. The agent uses Claude to understand the request and decide what to do. When it needs restaurant information it calls tools provided by the MCP restaurant server, which also runs inside the agent process. That server reads and writes the PostgreSQL database (Neon).
5. When the agent reaches a step that changes something, it pauses and sends an approval question back to the web app. The person's answer is sent to `POST /api/v1/chat/{thread_id}/resume`, and the agent carries on.
6. After a booking, change or cancellation, the agent sends a confirmation email through Resend.

The FastAPI routes are attached to the agent server through the `http.app` setting in `langgraph.json`, and the built React app is served from the same address under `/app/`. Because the page and the API share one origin, no CORS configuration is needed in production.

## The agent in detail

### Outer graph (`agent/advanced_graph.py`)

An outer graph wraps the core reservation graph and adds planning, memory and self-checking:

| Step | What it does |
| --- | --- |
| Load memory | Loads saved preferences for the user, if any (currently switched off in production, see [Known limitations](#known-limitations)). |
| Create plan | Drafts a short plan for the request. |
| Detect requested restaurant | If the person names a restaurant, locks it in so it is never silently replaced. |
| Inject memory and plan | Adds the plan and constraints to the model's context. |
| Core agent | Runs the core reservation graph (below). |
| Evaluate execution | Checks whether the goal was met. |
| Adapt | Retries or adjusts when the goal was not met. |
| Save memory | Stores newly learned preferences. |

The plan text is internal. The web app filters it out, so people only see the assistant's replies.

### Core reservation graph (`agent/graph.py`)

1. **Extract state.** A structured extraction step turns each message into state: restaurant, date, time, party size, cuisine, location and intent (search, book, modify, cancel).
2. **Route deterministically.** Plain code decides the next step from that state. Examples: a named restaurant with a full set of details goes straight to an availability check, and a modify or cancel request goes to a reservation lookup.
3. **Agent step.** Claude answers questions and calls the search, availability, alternative-times and reservation-lookup tools. Claude is **not** given the tool that creates, changes or cancels reservations.
4. **Gates for each write.** Writes only happen through graph nodes that sit behind approval.

### The three gates for a new booking

1. **Availability.** The exact slot must be confirmed available by the availability tool.
2. **Approval.** The graph calls `interrupt()` and shows a card with the restaurant, guests, date and time. It resumes only on an explicit approval.
3. **Email, then create.** The customer's email is collected, the reservation is created in the database, and the confirmation email is sent.

Modifying and cancelling follow the same pattern: look the reservation up by ID, ask for approval (and an email address if one is not known), apply the change, then confirm by message and email.

### Approval answers

The approval step accepts a yes from either source: the web app sends the boolean `true`, and LangSmith Studio can send the text `yes`. Anything else counts as a rejection and ends the flow.

## MCP restaurant tools

`mcp_servers/restaurant_server.py` defines the tools. `agent/mcp_client.py` calls them in-process through the MCP in-memory transport.

| Tool | Purpose |
| --- | --- |
| `search_restaurants(location, cuisine?)` | Find restaurants by area and optional cuisine. |
| `check_availability(restaurant_id, date, time, party_size)` | Check one exact slot. |
| `get_alternative_times(restaurant_id, date, requested_time, party_size)` | List other times at the same restaurant. |
| `create_reservation(restaurant_id, date, time, party_size)` | Create a reservation (called by the graph after approval only). |
| `get_reservation(reservation_id)` | Look up a reservation. |
| `modify_reservation(reservation_id, date?, time?, party_size?)` | Change a reservation (graph only). |
| `cancel_reservation(reservation_id)` | Cancel a reservation (graph only). |

Claude is bound to `search_restaurants`, `check_availability`, `get_alternative_times` and `get_reservation`.

### The mock catalogue

| ID | Restaurant | Cuisine | Bookable times |
| --- | --- | --- | --- |
| `rest-001` | Bella Italia Mayfair | Italian | 18:00, 18:30, 19:00, 19:30, 20:00 |
| `rest-002` | La Tavola | Italian | 18:00, 18:30, 20:00, 20:30 |
| `rest-003` | The Mayfair Grill | British | not bookable |
| `rest-004` | Sushi House Mayfair | Japanese | not bookable |

The `integrations/` package defines a booking-provider interface with a mock implementation. It is the intended place to plug in a real provider. The live MCP server currently serves its own built-in mock data.

## Data model

PostgreSQL, accessed with SQLAlchemy and psycopg 3. Tables are created by `database/init_db.py`.

| Table | Purpose | Main columns |
| --- | --- | --- |
| `users` | People who use Reseva | `external_id`, `email` |
| `restaurants` | Restaurant catalogue (seeded by `database/seed.py`) | `id`, `name`, `location`, `cuisine` |
| `reservations` | Bookings | `reservation_id` (for example `res-1a2b3c4d`), `restaurant_id`, `date`, `time`, `party_size`, `status`, `created_at` |
| `reservation_events` | Audit trail per reservation | `event_type`, `description`, `created_at` |
| `user_memories` | Learned preferences per user | `memory_type`, `memory_key`, `memory_value` |

`reservations.restaurant_id` is a foreign key to `restaurants.id`, so the restaurants must be seeded before any booking can be created.

## API reference

Base address: the deployment URL (production) or `http://127.0.0.1:8000` (local).

### `GET /api/v1/health`

Returns `{"status": "healthy", "service": "reseva-api", "version": "1.0.0"}`.

### `POST /api/v1/chat`

Send a message in a conversation thread.

```json
{
  "thread_id": "3f240cf1-aa4d-4c38-a054-de1386a99007",
  "user_id": "any-string",
  "message": "Book Bella Italia Mayfair for 2 people tomorrow at 8pm"
}
```

Response:

```json
{
  "thread_id": "3f240cf1-aa4d-4c38-a054-de1386a99007",
  "status": "approval_required",
  "message": "You're about to book Bella Italia Mayfair for 2 people on 2026-10-26 at 20:00. Do you want me to proceed?",
  "data": { "__interrupt__": [ ... ], "messages": [ ... ] }
}
```

`status` is `approval_required` when the agent is waiting for an answer. Otherwise it reports the agent's task status. The thread ID is chosen by the client, and the same ID continues the conversation.

### `POST /api/v1/chat/{thread_id}/resume`

Answer a paused question.

```json
{ "approval": true }
```

`approval` is a boolean for approval cards (`true` to approve, `false` to decline) or a string when the agent is asking for an email address. The response has the same shape as `/chat`.

### Example

```bash
curl -s -X POST "$BASE/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"demo-1","user_id":"me","message":"Find me Italian restaurants in Mayfair"}'
```

Requests are rate limited per visitor (default 20 per minute) and return `429` when the limit is exceeded.

## Frontend

A React and TypeScript single-page app built with Vite and styled with Tailwind CSS (`frontend/`). It provides:

- A chat view that shows the person's messages and the assistant's replies, with bold text and line breaks preserved.
- **Approval cards** for bookings, changes and cancellations, with buttons that match the action: **Confirm booking / Cancel**, **Confirm change / Keep original** and **Yes, cancel it / Keep reservation**.
- **An email box** when the agent asks for an address.
- **Thinking indicators** (animated dots and a "ResEva is thinking..." line) while the agent works.
- A filter that hides internal messages (plans, tool calls and tool results) from the chat.

In development the app calls `VITE_API_BASE_URL` (from `frontend/.env.local`). The production build uses an empty value, so it calls the address it was served from. `vite.config.ts` sets `base: '/app/'` so assets resolve under `/app/`.

## Project structure

```
reseva/
├── agent/
│   ├── advanced_graph.py     Outer graph: memory, planning, evaluation, adaptation
│   ├── graph.py              Core reservation graph, routing and approval gates
│   ├── state.py              Shared state definitions
│   ├── claude.py             Claude model and bound tools
│   ├── extractor.py          Structured extraction of intent and details
│   ├── memory_extractor.py   Extraction of user preferences
│   ├── mcp_client.py         In-process client for the MCP restaurant server
│   └── deployment.py         Graph entry point used by the deployment
├── mcp_servers/
│   └── restaurant_server.py  MCP tools and mock restaurant data
├── api/
│   ├── main.py               FastAPI routes, rate limit, static web app
│   └── schemas.py            Request and response models
├── database/                 Models, repositories, init and seed scripts
├── integrations/             Booking-provider interface and mock provider
├── frontend/                 React + Vite web app (source)
├── static_app/               Built web app served at /app/
├── tests/                    Test suite
├── langgraph.json            Deployment configuration
├── requirements.txt          Python dependencies
└── .env.example              Template for environment variables
```

## Configuration

### Environment variables

Copy `.env.example` to `.env` for local work. Production values go in `.env.production` (git-ignored).

| Variable | Required | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Yes | Claude |
| `DATABASE_URL` | Yes | PostgreSQL connection string. For Neon, end it with `?sslmode=require` |
| `LANGSMITH_API_KEY` | Yes | LangSmith API access and tracing |
| `LANGSMITH_TRACING` | No | `true` to trace runs |
| `LANGSMITH_PROJECT` | No | Tracing project name |
| `LANGSMITH_DEPLOYMENT_NAME` | No | Deployment name used by `langgraph deploy` |
| `LANGGRAPH_API_URL` | Local only | Address of a deployed agent, used by the API when run on a laptop |
| `RESEND_API_KEY` | Yes | Sending email |
| `RESEND_FROM_EMAIL` | Yes | Verified sender address in Resend |
| `RESEND_FROM_NAME` | No | Sender display name |
| `RESEVA_IN_PROCESS` | Production | Set to `1` in `.env.production` so the API calls the agent directly instead of over the network |
| `ALLOWED_ORIGINS` | No | Comma-separated origins allowed by CORS when running locally |
| `RATE_LIMIT_PER_MINUTE` | No | Requests per visitor per minute (default 20) |
| `VITE_API_BASE_URL` | Frontend | Set in `frontend/.env.local` for development |

### `langgraph.json`

```json
{
  "dependencies": ["."],
  "graphs": { "reseva": "./agent/deployment.py:graph" },
  "env": ".env.production",
  "http": { "app": "./api/main.py:app" }
}
```

| Key | Meaning |
| --- | --- |
| `dependencies` | Install the project itself; Python packages come from `requirements.txt` |
| `graphs` | Registers the agent under the ID `reseva` |
| `env` | File whose variables are sent to the deployment |
| `http.app` | Attaches the FastAPI app so its routes are served by the same server |

No Python version is set, so the CLI default (3.11) is used.

## Local development

### Prerequisites

- Python 3.11
- A current Node.js LTS release
- A PostgreSQL database (a free [Neon](https://neon.tech) project works well)
- API keys for [Anthropic](https://console.anthropic.com), [LangSmith](https://smith.langchain.com) and [Resend](https://resend.com)

### Setup

```bash
git clone https://github.com/uchegreat/Reseva.git
cd Reseva

python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..

cp .env.example .env               # then fill in your values
```

### Create the database tables and seed the restaurants

```bash
python -m database.init_db
python -m database.seed
```

Run these against whichever database `DATABASE_URL` points to. `init_db` creates the tables that are missing and does not delete data; `seed` adds the four mock restaurants.

### Run the API and the web app

The API forwards chat requests to a deployed agent, so set `LANGGRAPH_API_URL` and `LANGSMITH_API_KEY` in `.env` first.

```bash
uvicorn api.main:app --port 8000
```

Then either open `http://127.0.0.1:8000/app/` (serves the built app from `static_app/`), or run the Vite dev server in a second terminal:

```bash
cd frontend
npm run dev
```

## Testing

Tests live in `tests/` and cover the extractor, repositories, graph flows, approvals, recovery and the API.

```bash
python -m pytest tests/test_alternatives.py
```

Notes:

- Many tests use PostgreSQL and read `DATABASE_URL`. Point it at a test database, never at production.
- `tests/test_availability.py` and `tests/test_mcp_client.py` are small runnable scripts: `python -m tests.test_availability`.
- The workflow in `.github/workflows/ci.yml` runs on every push. Many tests need a database and keys, so it may not pass without them.

## Deployment with the LangSmith CLI

Reseva is deployed as a single [LangSmith Deployment](https://docs.langchain.com/langsmith/deployment) using the `langgraph deploy` command from the LangGraph CLI. The result is a Docker image of the agent server, built from this project and run by LangSmith.

### What `langgraph deploy` does

1. Reads `langgraph.json` to find the graph, the dependencies, the env file and the custom FastAPI app.
2. Builds a Docker image of the LangGraph API server that contains this project (the image is built on top of LangChain's `langgraph-api` base image).
3. Pushes the image to a registry managed by LangSmith.
4. Creates the deployment on first use, or a new **revision** of the existing deployment afterwards, and waits for it to become healthy.

There is no Dockerfile in the repository. The CLI derives the image from `langgraph.json`.

### Building the image: remote or local

| Mode | When it is used |
| --- | --- |
| **Remote build** | Used when Docker is not available. The CLI uploads a small source archive (about 0.3 MB for Reseva) and LangSmith builds the image. All Reseva releases so far were built this way, because Docker Desktop was not running. |
| **Local build** | Used when Docker is installed and running. The CLI builds the image on your machine and pushes it. |

You can force a mode with `--remote` or `--no-remote`.

### Prerequisites

- `pip install langgraph-cli` (inside the virtual environment)
- A LangSmith API key with access to Deployments (`LANGSMITH_API_KEY` in `.env`)
- Optional: Docker Desktop, for local builds

### One-time setup for a new deployment

1. Create the production database and set `DATABASE_URL` for it in `.env.production`.
2. Create the tables and seed the restaurants against that database:
   ```bash
   python -m database.init_db
   python -m database.seed
   ```
3. Fill in `.env.production` with the variables from the table above, including `RESEVA_IN_PROCESS=1`.
4. Set the deployment name, for example `LANGSMITH_DEPLOYMENT_NAME=reseva`.

### Releasing a new version

1. Run the checks you need, for example the tests that do not need a database.
2. Rebuild the frontend and copy it into `static_app/`:
   ```bash
   cd frontend
   npm run build
   cd ..
   rm -rf static_app
   cp -r frontend/dist static_app
   ```
3. Deploy:
   ```bash
   langgraph deploy
   ```
   The command prints its progress (queued, building, deploying) and ends with `Deployment successful!` and the deployment URL. A build takes about three to four minutes.
4. Verify:
   - Open `<deployment-url>/api/v1/health`. It should return `{"status":"healthy",...}`.
   - Open `<deployment-url>/app/` in a private window and run a search, then a booking.

Two details about the environment: `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` are reserved by the platform, so the CLI skips them when sending variables, and the deployment gets them from LangSmith itself.

### Useful commands

```bash
langgraph deploy list                          # list deployments
langgraph deploy revisions list <deployment-id>   # list revisions
langgraph deploy logs                          # runtime logs
langgraph deploy logs --type build             # build logs of the latest revision
langgraph deploy logs -f                       # follow logs
```

Logs are also available in the LangSmith UI (the document icon on each revision).

### Working with the Docker image yourself (optional)

The normal release path above needs none of this. These commands are available when you want to inspect or run the image on your own machine:

```bash
langgraph dockerfile Dockerfile           # write out the Dockerfile the CLI would use
langgraph build -t reseva:local           # build the image locally (needs Docker)
langgraph up                              # run the server locally in Docker
langgraph deploy --image reseva:local     # deploy an image you built (must be linux/amd64)
```

`langgraph deploy` can also push to a container registry you manage (`--push-to`) or deploy an image already in a registry (`--image-uri`), which is how self-hosted setups work. See the [LangGraph CLI reference](https://docs.langchain.com/langsmith/cli).

### Deployment settings

At the time of writing the deployment is a Serverless deployment on the Small size (1 replica, 0.4 CPU, 1 GB) and scales down after a week without traffic. Compute size and scale-down time are set under the deployment's settings in LangSmith.

### Custom domains

The deployment is served from the default `*.langgraph.app` address. LangSmith's settings for this deployment type do not offer a custom-domain option, so using your own domain means putting a reverse proxy (for example a Cloudflare Worker) in front of the deployment address.

## Security and privacy

- **Secrets stay out of git.** `.env`, `.env.production` and `frontend/.env.local` are git-ignored, and the history was checked for key patterns before publishing. Use `.env.example` as the template.
- **Public routes by design.** `/app/` and `/api/v1/*` are open so anyone can try the demo. The platform's own endpoints (threads, runs, assistants) require a LangSmith API key.
- **Spend protection.** A per-visitor rate limit (default 20 requests per minute) limits model usage. It is best effort: it identifies visitors by the forwarded address and resets on restart. Set a spending limit with your model provider as well.
- **No login.** Anyone who knows a reservation ID can look up, change or cancel that reservation. Do not use real personal data in the demo.
- **Writes are gated.** The agent cannot create, change or cancel a reservation without an explicit approval.
- **Email.** Confirmation emails go to the address typed into the email box.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `MCPError: Connection closed` during `session.initialize()` on the hosted deployment | The MCP server was started as a subprocess, and a child process does not inherit the import path set up by the platform, so it exits before the handshake | Use the in-process client in `agent/mcp_client.py` (already the default) |
| Clicking **Confirm booking** does nothing, or the run ends as `booking_rejected` | The approval step only accepted the text `yes`, while the web app sends `true` | Approval accepts both (`_is_approved` in `agent/graph.py`) |
| The page shows "The hosted reservation service could not resume the request" | The agent raised an error while resuming | Run `langgraph deploy logs` and look for `Hosted LangGraph resume error` |
| The chat shows only "Request processed successfully." | The reply was filtered out because it carried an empty `tool_calls` list | Treat only non-empty `tool_calls` as tool messages (`isToolMessage` in `frontend/src/App.tsx`) |
| Clicking **Confirm** or **Cancel** on an email question has no useful effect | A yes or no is not an email address | The web app shows an email box for these questions, and `ResumeRequest.approval` accepts text |
| The built page calls `127.0.0.1:8000` | `.env.local` was baked into the production build | Keep `frontend/.env.production` with an empty `VITE_API_BASE_URL` |
| `/app/` loads blank or assets return 404 | Wrong base path or missing build | Keep `base: '/app/'` in `vite.config.ts` and copy `frontend/dist` to `static_app/` |
| `foreign key` error when booking | The restaurants table is empty | Run `python -m database.seed` against the production database |
| SSL errors with Neon | Missing SSL option | End `DATABASE_URL` with `?sslmode=require` |
| Environment values end with a stray character on Windows | Windows line endings in an env file read by a shell script | Strip carriage returns (`tr -d '\r'`) when reading values in Git Bash |

## Design decisions

- **Approval before action.** The model proposes, a person approves, and only then does graph code write to the database. The model is never given the write tools.
- **Code decides availability.** Availability and routing are deterministic, so the model cannot invent a free table or swap the restaurant the person asked for.
- **In-process MCP.** The MCP server runs inside the agent process. An earlier version launched it as a subprocess, which failed on the hosted platform.
- **One deployment.** Serving the API and the web app from the agent deployment keeps the API key off the browser, removes CORS, and means one thing to deploy.
- **Plans stay internal.** The planning text guides the model but is hidden from the chat.

## Known limitations

- Restaurants and availability are mock data (four restaurants and fixed time slots).
- Long-term memory is implemented but switched off in production, because the web app does not yet identify individual users. The `users` table is empty and memory loading is skipped.
- There is no login, so reservations are protected only by their ID.
- The rate limit is in memory and best effort.
- Code review found one routing path where a stale invalid-email state could send a repeated booking request to the email step before the approval card. It has not been reproduced in testing, and starting a new chat avoids it.
- The public address is the default LangSmith address.

## Roadmap

- Connect a real reservation provider through `integrations/`
- User accounts and per-user memory
- Custom domain
- Tests that run without a database, and a CI workflow that passes without secrets
- Tighten the invalid-email retry route so approval can never be skipped