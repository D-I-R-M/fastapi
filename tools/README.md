# tools/

Development utilities for the Sugar Journal FastAPI backend.

## mock_datastore_service.py

A real D-Bus service that registers as `org.laptop.sugar.DataStore` on the
session bus and serves the `sample_journal/` JSON files.

Implements the **exact same D-Bus interface** as the real Sugar Datastore:
- `find(query: a{sv}, properties: as) -> (aa{sv}, u)`
- `delete(uid: s) -> void`
- `get_filename(uid: s) -> s`
- `save(props: a{sv}, ...) -> s`
- Signal: `Updated(uid: s, event: s)`

### Requirements (Linux only)

```bash
sudo apt install python3-dbus python3-gi dbus
```

### Usage

**Terminal 1 — start the mock service:**
```bash
./tools/run_dbus_mock.sh
```

**Terminal 2 — run FastAPI against the mock D-Bus service:**
```bash
DATASTORE_BACKEND=dbus uvicorn app.main:app --reload
```

### Running D-Bus tests

```bash
eval $(dbus-launch --sh-syntax)
python tools/mock_datastore_service.py &
pytest tests/test_dbus_adapter.py -v
```

### Switching to the real Sugar Datastore

On a device with Sugar running:
```bash
DATASTORE_BACKEND=dbus uvicorn app.main:app --reload
```

No code changes needed.