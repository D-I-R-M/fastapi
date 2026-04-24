# Sugar Journal AI API

A FastAPI backend that exposes the **Sugar Learning Platform Journal**
(`jarabe/journal` + `sugar-datastore`) over HTTP, with AI-powered reflection
and learning-insights endpoints.

Modelled after
[`musicblocks_reflection_fastapi`](https://github.com/sugarlabs/musicblocks_reflection_fastapi)
but targeting the Sugar Journal datastore instead of Music Blocks project data.

---

## Features

| Endpoint | What it does |
|---|---|
| `GET /entries` | Paginated list of journal entries |
| `GET /entries/{uid}` | Full detail for one entry (includes preview thumbnail) |
| `POST /entries/search` | Filter by full-text, activity, MIME type, tags |
| `DELETE /entries/{uid}` | Remove an entry from the datastore |
| `POST /reflect` | AI reflection on one or more specific entries |
| `POST /insights` | Aggregate stats + LLM narrative across the whole journal |
| `GET /docs` | Swagger UI |
| `GET /redoc` | ReDoc |

---

## Architecture

```
HTTP clients
     │
     ▼
FastAPI app  (app/main.py)
     │
     ├── /entries  router  ──►  JournalService  ──►  DatastoreAdapter
     │                                                  ├── dbus  (real Sugar)
     │                                                  ├── file  (JSON files)
     │                                                  └── mock  (tests)
     │
     └── /reflect, /insights  ──►  ReflectionService  ──►  LLMAdapter
                                                              ├── anthropic
                                                              ├── openai
                                                              └── mock
```

---

## Quick start (no Sugar required)

```bash
git clone <this-repo>
cd sugar_journal_fastapi

pip install fastapi "uvicorn[standard]" pydantic pydantic-settings httpx anthropic

# Uses mock datastore + mock LLM by default
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** to explore the API interactively.

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `DATASTORE_BACKEND` | `mock` | `dbus` / `file` / `mock` |
| `LLM_PROVIDER` | `mock` | `anthropic` / `openai` / `mock` |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `LLM_MODEL` | `claude-3-5-sonnet-20241022` | Any model string |
| `DATASTORE_FILE_PATH` | `./sample_journal` | Directory of JSON files for `file` backend |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |

---

## Datastore backends

### `mock`
Four in-memory entries; perfect for tests and demos.

### `file`
Place one JSON file per journal entry in `./sample_journal/`.
Five sample entries are included. Each file must be a JSON object with
the same keys as `JournalEntry` (all optional except `uid` — the filename
stem is used if `uid` is absent).

### `dbus`
Talks to the real Sugar Datastore over D-Bus. Requires:
- A running Sugar desktop session (Linux)
- `dbus-python` installed (`pip install dbus-python`)
- The `org.laptop.sugar.DataStore` service to be active

```bash
DATASTORE_BACKEND=dbus uvicorn app.main:app --reload
```

---

## Running with real AI reflection

```bash
# .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
DATASTORE_BACKEND=file      # or dbus on-device

uvicorn app.main:app --reload
```

Example request:

```bash
curl -s -X POST http://localhost:8000/reflect \
  -H "Content-Type: application/json" \
  -d '{"uids": ["sample-001", "sample-003"]}' | python3 -m json.tool
```

---

## Docker

```bash
# Build
docker build -t sugar-journal-api .

# Run with mock backends
docker run -p 8000:8000 sugar-journal-api

# Run with real keys
docker run -p 8000:8000 \
  -e LLM_PROVIDER=anthropic \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  sugar-journal-api
```

Or with docker-compose:

```bash
docker-compose up
```

---

## Tests

```bash
pip install pytest pytest-asyncio httpx
pytest -v
```

All tests use mock backends — no network or Sugar session required.

---

## Project layout

```
sugar_journal_fastapi/
├── app/
│   ├── main.py              # FastAPI app factory
│   ├── config.py            # Pydantic-settings
│   ├── dependencies.py      # DI wiring
│   ├── models/
│   │   └── journal.py       # JournalEntry, request/response shapes
│   ├── adapters/
│   │   ├── datastore.py     # D-Bus / file / mock backends
│   │   └── llm.py           # Anthropic / OpenAI / mock backends
│   ├── services/
│   │   └── journal.py       # JournalService + ReflectionService
│   └── routers/
│       ├── entries.py       # /entries CRUD + search
│       └── reflection.py    # /reflect + /insights
├── tests/
│   └── test_api.py
├── sample_journal/          # Five sample JSON entries
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Extending

- **Add a new datastore backend** — subclass `BaseDatastoreAdapter` in
  `app/adapters/datastore.py` and add a branch in `get_datastore_adapter()`.
- **Add a new LLM provider** — subclass `BaseLLMAdapter` in
  `app/adapters/llm.py` and add a branch in `get_llm_adapter()`.
- **Add a new endpoint** — create a new router in `app/routers/` and
  register it in `app/main.py`.

---

## Related projects

- [sugarlabs/musicblocks_reflection_fastapi](https://github.com/sugarlabs/musicblocks_reflection_fastapi) — inspiration
- [sugarlabs/sugar](https://github.com/sugarlabs/sugar) — Sugar shell + Journal (`jarabe/journal`)
- [sugarlabs/sugar-datastore](https://github.com/sugarlabs/sugar-datastore) — D-Bus datastore service
