# NeighbourShield

NeighbourShield is a Django REST backend for a township safety system. It records SOS incidents, responder acknowledgements, safety reports, and emergency broadcasts.

## Structure

- `neighbour_shield_backend/` — project configuration and top-level routes.
- `core/` — domain models, REST API, Django admin configuration, dashboard, and management commands.
- `core/models.py` — SOS escalation and audit rules; this is the system's business-rule layer.
- `core/views.py` — authenticated API endpoints under `/api/`.

## Registering a property

Township administrators create an `Area`, then add its houses, apartments, or townhouses in **Admin → Properties**. When a resident is assigned to a property, their area is set from that property. One property can have multiple residents.

## Local setup

Install the dependencies in a fresh Python 3.12 virtual environment, then run migrations:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

With no database environment variables, development uses the local `db.sqlite3`. Copy `.env.example` into your deployment's secret store and set `DJANGO_DB_ENGINE` plus the MySQL settings to use MySQL.

## API safety rules

- Obtain a token with `POST /api/login/`; send it as `Authorization: Token <token>`.
- SOS creation and acknowledgement use the transaction-safe workflow in `Incident`.
- Residents see only their own incidents and can only edit their own hazard reports.
- Township administrators manage users; official announcements and broadcasts require administrator permissions.
- Register app installations at `/api/devices/`; device tokens are write-only and are never returned.

## Scheduled processing

Run the following command every minute using Task Scheduler, cron, or a worker platform:

```powershell
python manage.py process_sos
```

It escalates unacknowledged SOS incidents and removes stale user locations. Push delivery itself still needs an FCM provider integration.
