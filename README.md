# Emergency Response Platform

Community emergency response services with a FastAPI API, a Django/DRF compatibility API, and a Next.js frontend.

## Repository layout

- `backend/app/` - FastAPI application, SQLAlchemy models, authentication, and async API routes.
- `backend/apps/` and `backend/config/` - Django/DRF compatibility service and its management commands.
- `backend/migrations/` - Alembic migrations for the FastAPI data model.
- `backend/tests/` - FastAPI integration and security tests.
- `frontend/` - Next.js web client and health-check page.

## Local setup

### Backend

1. Create a Python virtual environment and install dependencies:

   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set `DATABASE_URL` and `JWT_SECRET_KEY`.
   The FastAPI service expects PostgreSQL through `postgresql+asyncpg`.

3. Apply the FastAPI schema and start the API:

   ```bash
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```

   FastAPI documentation is available at <http://localhost:8000/docs>.

The Django service uses the same `.env` file for its database connection settings.
Set `DJANGO_TESTING=true` (or run a Django `test` command) when an in-memory SQLite
database is required.

### Frontend

```bash
cd frontend
npm ci
copy .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. Set `NEXT_PUBLIC_API_BASE_URL` in `.env.local` when
the API is not running on port 8000.

## Validation

Run the backend tests from `backend` with `pytest -q`, the Django checks with
`python manage.py check`, and the frontend checks from `frontend` with
`npm run lint`.
