# sentinel-api

```bash
# from repo root
uv sync                                  # creates .venv for the whole workspace
uv run --package sentinel-api sentinel-api
# or, for hot reload during dev:
uv run --package sentinel-api uvicorn sentinel_api.main:app --reload --port 8000
```

Docs: http://localhost:8000/docs  (Authorize with admin / ADMIN_PASSWORD)

Bootstrap accounts (all share ADMIN_PASSWORD): admin, supervisor, operator, gsrtc_nodal, auditor.
