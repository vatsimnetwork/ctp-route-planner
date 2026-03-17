# CTP Route Planner

Web app for managing waypoints and CTP routes with Django + PostgreSQL.

## Tech Stack

- Python 3.x
- Django 5.2
- PostgreSQL
- Docker Compose

## Environment Variables

Create/update `.env` in project root:

```env
DJANGO_SECRET_KEY=your_secret_key
DEBUG=True
DJANGO_LOGLEVEL=info
DJANGO_ALLOWED_HOSTS=127.0.0.1

DATABASE_ENGINE=postgresql_psycopg2
DATABASE_NAME=dockerdjango
DATABASE_USERNAME=dbuser
DATABASE_PASSWORD=dbpassword
DATABASE_HOST=localhost
DATABASE_PORT=5432

AUTH_INTERNAL_URL=http://auth-panel:8000
AUTH_PUBLIC_URL=https://auth.example.com
INTERNAL_API_KEY=your_internal_api_key
APP_URL=http://localhost:8000

# Optional: if set, each route change sends a CSV to this webhook
DISCORD_ROUTES_WEBHOOK_URL=
```

## Run with Docker

```bash
docker compose up --build
```

Then open: `http://localhost:8000`

## Run locally (venv)

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Main Routes

- `/` Home
- `/routeplotter/` Route plotter page
- `/routes/` Route management page
- `/settings/waypoints/` Waypoint settings/import
- `/auth/login/` Redirect to SSO login
- `/auth/logout/` Redirect to SSO logout

## Session and Roles

`SessionCheckMiddleware` validates the `session_id` cookie against the SSO internal endpoint.

On successful validation, these request attributes are available:

- `request.is_session_valid` (bool)
- `request.user_cid` (string or `None`)
- `request.user_roles` (list of role strings)

Example in a view:

```python
def my_view(request):
    if "administrator" in request.user_roles:
        # admin-only logic
        ...
```

## Route Save Rules

- Commas and semicolons are not allowed in route strings
- AMAS/EMEA identifiers are generated automatically from first and last waypoint
- NAT identifiers are user-defined and must be unique
- Saves are validated against original row values to detect concurrent edits

## Manual CSV Backup Command

Run on demand:

```bash
python manage.py backup_routes
```

Output folder:

- `backups/` (timestamped CSV files)

## Notes

- Make sure `AUTH_SERVICE_URL` and `INTERNAL_API_KEY` match your SSO service config.
