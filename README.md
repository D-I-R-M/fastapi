# Sugar Journal AI API

> A FastAPI backend that exposes the **Sugar Learning Platform Journal**
> (`jarabe/journal` + `sugar-datastore`) over HTTP — with AI-powered reflection,
> live WebSocket updates, and a pluggable D-Bus / file / mock datastore.

**Live demo:** https://fastapi-tv77.onrender.com  
**Interactive docs:** https://fastapi-tv77.onrender.com/docs  
**GitHub:** https://github.com/D-I-R-M/fastapi

Modelled after [`musicblocks_reflection_fastapi`](https://github.com/sugarlabs/musicblocks_reflection_fastapi)
but targeting the Sugar Journal datastore instead of Music Blocks project data.

---

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/entries` | Paginated list of journal entries |
| `GET` | `/entries/{uid}` | Full detail for one entry (includes preview thumbnail) |
| `POST` | `/entries` | Save a new entry — triggers WebSocket broadcast |
| `POST` | `/entries/search` | Filter by full-text, activity, MIME type, tags |
| `DELETE` | `/entries/{uid}` | Remove an entry from the datastore |
| `POST` | `/reflect` | AI reflection on one or more specific entries |
| `POST` | `/insights` | Aggregate stats + LLM narrative across the whole journal |
| `WS` | `/ws/journal` | WebSocket — receive live `entry_added` events |
| `GET` | `/ws/journal/status` | Number of currently connected WebSocket clients |
| `POST` | `/ws/journal/publish` | Dev tool — manually push a test WebSocket event |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |

---

## Architecture

```
HTTP / WebSocket clients
         │
         ▼
  FastAPI app  (app/main.py)
         │
         ├── /entries  ──────────►  JournalService  ──►  DatastoreAdapter
         │                                                  ├── dbus  (real Sugar)
         │                                                  ├── file  (JSON files)
         │                                                  └── mock  (tests)
         │
         ├── /reflect, /insights  ►  ReflectionService  ──►  LLMAdapter
         │                                                      ├── anthropic (Claude)
         │                                                      ├── openai (GPT)
         │                                                      └── mock
         │
         └── /ws/journal  ────────►  Broadcaster  ──► all connected WS clients
                                     (pub/sub, in-process)
```

---

## Quick start (no Sugar required)

```bash
git clone https://github.com/D-I-R-M/fastapi
cd fastapi

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

| Variable | Default | Description |
|---|---|---|
| `DATASTORE_BACKEND` | `mock` | `dbus` / `file` / `mock` |
| `LLM_PROVIDER` | `mock` | `anthropic` / `openai` / `mock` |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `LLM_MODEL` | `claude-3-5-sonnet-20241022` | Any Claude or GPT model string |
| `DATASTORE_FILE_PATH` | `./sample_journal` | Directory of JSON files for `file` backend |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `PORT` | `8000` | Port to bind (set to `10000` on Render) |

---

## Datastore backends

### `mock`
Four in-memory entries. Perfect for tests and local demos. No setup required.

### `file`
Reads/writes flat JSON files from `./sample_journal/` (one file per entry).
Five sample entries are included. Useful for development on any platform.

### `dbus`
Talks to the real Sugar Datastore over D-Bus. Requires a running Sugar desktop
session on Linux, plus `dbus-python`.

```bash
# Option A — use the mock D-Bus service (no Sugar needed)
./tools/run_dbus_mock.sh        # Terminal 1
DATASTORE_BACKEND=dbus uvicorn app.main:app --reload  # Terminal 2

# Option B — on a real Sugar device
DATASTORE_BACKEND=dbus uvicorn app.main:app --reload
```

See `tools/README.md` for full D-Bus setup instructions.

---

## WebSocket live updates

Connect to `ws://localhost:8000/ws/journal` to receive live events whenever
a new journal entry is saved.

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/journal");
ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  // { event: "entry_added", uid, title, activity, mime_type, timestamp, tags }
  console.log(event);
};
```

A browser-based test client is included at `tools/ws_test_client.html`.
Open it locally, click Connect, then save an entry via `POST /entries` to
see the live event arrive instantly.

---

## Running with real AI reflection

```bash
# .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
DATASTORE_BACKEND=file      # or dbus on-device

uvicorn app.main:app --reload
```

Example:

```bash
curl -s -X POST http://localhost:8000/reflect \
  -H "Content-Type: application/json" \
  -d '{"uids": ["sample-001", "sample-003"]}' | python3 -m json.tool
```

---

## Docker

```bash
# Build and run with mock backends
docker build -t sugar-journal-api .
docker run -p 8000:8000 sugar-journal-api

# Run with real Anthropic key
docker run -p 8000:8000 \
  -e LLM_PROVIDER=anthropic \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  sugar-journal-api

# Or with docker-compose
docker-compose up
```

---

## Tests

```bash
pip install pytest pytest-asyncio httpx
python -m pytest tests/test_api.py -v
```

25 tests covering all endpoints, WebSocket handshake, live broadcast,
pagination, filtering, and error paths. All use mock backends — no network
or Sugar session required.

```bash
# D-Bus integration tests (Linux only, requires dbus-python)
eval $(dbus-launch --sh-syntax)
python tools/mock_datastore_service.py &
pytest tests/test_dbus_adapter.py -v
```

---

## Project layout

```
fastapi/
├── app/
│   ├── main.py                  # FastAPI app factory, CORS, router registration
│   ├── config.py                # Pydantic-settings (env vars / .env)
│   ├── dependencies.py          # Dependency injection wiring
│   ├── models/
│   │   └── journal.py           # JournalEntry + all request/response shapes
│   ├── adapters/
│   │   ├── base.py              # BaseDatastoreAdapter (abstract)
│   │   ├── datastore.py         # D-Bus / file / mock backends
│   │   └── llm.py               # Anthropic / OpenAI / mock backends
│   ├── services/
│   │   ├── journal.py           # JournalService + ReflectionService
│   │   └── broadcaster.py       # WebSocket pub/sub broadcaster
│   └── routers/
│       ├── entries.py           # /entries CRUD + search
│       ├── reflection.py        # /reflect + /insights
│       └── ws.py                # WebSocket /ws/journal
├── tests/
│   ├── test_api.py              # 25 API tests (mock backends)
│   └── test_dbus_adapter.py     # 13 D-Bus integration tests (Linux)
├── tools/
│   ├── mock_datastore_service.py  # Real D-Bus service mimicking Sugar
│   ├── run_dbus_mock.sh           # Launcher (auto-starts session bus)
│   ├── ws_test_client.html        # Browser WebSocket test client
│   └── README.md                  # D-Bus setup guide
├── sample_journal/              # 5 sample JSON journal entries
├── conftest.py                  # pytest path setup
├── .env.example                 # All env vars documented
├── .gitignore
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Deployment

Deployed on **Render** at https://fastapi-tv77.onrender.com.

Required environment variables on Render:

| Variable | Value |
|---|---|
| `DATASTORE_BACKEND` | `mock` |
| `LLM_PROVIDER` | `mock` |
| `PORT` | `10000` |

To enable real AI reflections, add `ANTHROPIC_API_KEY` and set
`LLM_PROVIDER=anthropic`.

---

## Extending

- **New datastore backend** — subclass `BaseDatastoreAdapter` in `app/adapters/datastore.py`
  and add a branch in `get_datastore_adapter()`
- **New LLM provider** — subclass `BaseLLMAdapter` in `app/adapters/llm.py`
  and add a branch in `get_llm_adapter()`
- **New endpoint** — create a router in `app/routers/` and register it in `app/main.py`

---

## Related projects

- [sugarlabs/musicblocks_reflection_fastapi](https://github.com/sugarlabs/musicblocks_reflection_fastapi) — inspiration
- [sugarlabs/sugar](https://github.com/sugarlabs/sugar) — Sugar shell + Journal (`jarabe/journal`)
- [sugarlabs/sugar-datastore](https://github.com/sugarlabs/sugar-datastore) — D-Bus datastore service
