# Self-Eat Backend

FastAPI backend for **Self-Eat** — the self-ordering and seating platform,
Self-It's first product. Self-It builds software that lets people do things
themselves; see the [project umbrella](https://github.com/sgoelman/SelfEat)
for the full vision and the other component repos.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# No local Postgres needed for dev — uses SQLite:
DATABASE_URL="sqlite+aiosqlite:///./dev.db" python -m app.seed
DATABASE_URL="sqlite+aiosqlite:///./dev.db" python -m uvicorn app.main:app --port 8123
```

Seeded demo login: `owner@demo.selfeat` / `demopass123` (restaurant slug `demo-lakeside`).

Production uses Cloud SQL (PostgreSQL) — see `.env.example` and Secret Manager
(`selfeat-database-url` in the `self-eat-app` GCP project).
