# Jenga API

Django backend foundation for team development. This repository is a starting point only: project configuration, PostgreSQL, Django REST Framework, CORS, and `/api/v1/` routing. Application apps, models, and endpoints are added later.

## Project structure

| Path | Purpose |
| --- | --- |
| `config/` | Django project package: settings, root URLs, WSGI, and ASGI. |
| `apps/` | Home for future Django apps. Add each feature as its own app here. |
| `api/v1/` | Versioned API URL routing. Include app routers from `api/v1/urls.py`. |
| `manage.py` | Django management entry point. |
| `.env.example` | Documented environment variables. Copy to `.env` for local use. |

## Requirements

- Python 3.10+
- PostgreSQL

## Setup

1. Create and activate a virtual environment.

   **Windows (PowerShell)**

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   **macOS / Linux**

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies.

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file and edit values as needed.

   ```bash
   copy .env.example .env
   ```

   On macOS / Linux:

   ```bash
   cp .env.example .env
   ```

4. Create the PostgreSQL database named in `DB_NAME` (default: `jenga`).

5. Apply migrations.

   ```bash
   python manage.py migrate
   ```

6. Start the development server.

   ```bash
   python manage.py runserver
   ```

The API version prefix is available at `http://127.0.0.1:8000/api/v1/`. No application endpoints are registered yet.

## Environment variables

| Variable | Description |
| --- | --- |
| `SECRET_KEY` | Django secret key. Use a unique value in every environment. |
| `DEBUG` | `True` for local development. |
| `ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. |
| `DB_NAME` | PostgreSQL database name. |
| `DB_USER` | PostgreSQL user. |
| `DB_PASSWORD` | PostgreSQL password. |
| `DB_HOST` | PostgreSQL host. |
| `DB_PORT` | PostgreSQL port (default `5432`). |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins allowed by CORS. |
| `CORS_ALLOW_ALL_ORIGINS` | Set `True` only for local experiments. Prefer an explicit origin list. |

## Adding a Django app later

```bash
python manage.py startapp example apps/example
```

Then add `"apps.example"` to `INSTALLED_APPS` in `config/settings.py` and include that app’s URLs from `api/v1/urls.py`.
