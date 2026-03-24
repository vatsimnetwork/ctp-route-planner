# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CTP Route Planner is a Django + PostgreSQL web app for managing VATSIM CTP (Cross the Pond) flight routes, waypoints, FIR boundaries, and airways.

## Commands

**Docker (recommended):**
```bash
docker compose up --build
```

**Local development:**
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Other management commands:**
```bash
python manage.py migrate
python manage.py backup_routes   # Manual CSV backup to backups/
python manage.py test            # Run tests
```

**Environment:** Copy the variables from README.md into a `.env` file in the project root before running locally.

## Architecture

### App Structure

Single Django app (`routeplanner/`) with views split by concern:
- `views/routes.py` — Route CRUD (batch save with optimistic locking, delete)
- `views/routeplotter.py` — Route visualization: resolves route strings to coordinates, serves FIR GeoJSON and waypoint data
- `views/setting.py` — Settings pages: waypoint CSV import, FIR boundary upload, airway CSV import
- `views/home.py` — Home page
- `discord.py` — Discord webhook integration (fire-and-forget in background thread)

### Models

- **Location** — Navigation waypoints (identifier, lon, lat, waypoint_id)
- **Route** — Flight routes (identifier as PK, group, routestring, facilities, tags)
- **Airway** / **AirwayWaypoint** — Jet airways with ordered waypoints via through model
- **RouteRevisionSet** / **RouteRevisionEntry** — Full audit trail: every batch save snapshots all routes

### Authentication

`SessionCheckMiddleware` (`routeplanner/middleware/session_check.py`) validates a `session_id` cookie against the external SSO service configured by `AUTH_SERVICE_URL`. It calls `GET /internal/session/validate` with `X-Internal-Key`, forwarded `Cookie`, `User-Agent`, and `X-Forwarded-For` headers. It sets `request.is_session_valid`, `request.user_cid`, and `request.user_roles` on every request. Unauthenticated requests are redirected to `{AUTH_SERVICE_URL}/auth/login/` unless the view is decorated with `login_not_required` or the path is `/admin/`.

### Route Save Rules

- Commas and semicolons are not allowed in route strings
- AMAS/EMEA identifiers are auto-generated from first/last waypoint; NAT identifiers are user-defined
- `_validate_route_payload()` in `views/routes.py` enforces all validation
- Concurrent edit detection uses optimistic locking: original row values are compared before writes, returning HTTP 409 on conflict; writes use `select_for_update()` inside `@transaction.atomic`

### Route Plotting

The plotter (`views/routeplotter.py`) resolves route strings containing ICAO waypoint identifiers, oceanic coordinates, and airway segment references into ordered lat/lon coordinates. When a waypoint identifier is ambiguous, the nearest match to the previous point is chosen. Airway segments are resolved by finding entry/exit points and extracting the ordered sub-sequence of waypoints.

### FIR Boundaries

Served from a local GeoJSON file if present; falls back to fetching from the vatspy-data-project on GitHub.

### Frontend

Templates use Bootstrap 5.3 with a client-side dark/light theme toggle (persisted in `localStorage`). Route visualization uses Leaflet.js with GeoJSON overlays.
