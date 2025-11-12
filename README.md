# Household Tasks – MVP

**Stack**: FastAPI + SQLAlchemy (SQLite), Jinja2 + HTMX, session cookie, Argon2 hashing.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## Default admin user
On first run, DB is created with an admin user:
- email: admin@example.com
- password: admin

> Change it immediately in the web UI (top-right menu) or via DB.

## Notes
- SQLite for MVP. Switch to Postgres by changing `DATABASE_URL` and using Alembic in a later phase.
- Session cookie is HttpOnly/SameSite=Lax. For HTTPS set `SESSION_SECURE=true`.
