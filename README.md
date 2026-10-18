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
pip install -r requirements.txt
pip install pymysql
python manage.py migrate
python manage.py run_escalation
```

With no database environment variables, development uses the local `db.sqlite3`. Copy `.env.example` into your deployment's secret store and set `DJANGO_DB_ENGINE` plus the MySQL settings to use MySQL.

## Running the System (Two Terminals Required):

To run the system locally, you need to run the web server and the background escalation engine simultaneously.

```
Terminal 1 (Web API & Dashboard):
PowerShell
.\venv\Scripts\Activate.ps1
python manage.py runserver 192.168.0.5:8000
```
```
Terminal 2 (Escalation & Notification Worker):
PowerShell
.\venv\Scripts\Activate.ps1
python manage.py run_escalation
```

## API safety rules

- Register a resident with `POST /api/auth/register/`, or log in with `POST /api/auth/login/`; send the returned token as `Authorization: Token <token>`.
- SOS creation and acknowledgement use the transaction-safe workflow in `Incident`.
- Residents see only their own incidents and can only edit their own hazard reports.
- Township administrators manage users; official announcements and broadcasts require administrator permissions.
- Register app installations at `/api/devices/`; device tokens are write-only and are never returned.

## Flutter API

All JSON endpoints are under `/api/`. Use the trailing slash shown below and send `Content-Type: application/json`.

| Endpoint | Methods | Purpose |
| --- | --- | --- |
| `/api/auth/register/` | POST | Create a resident account and return a token/profile. |
| `/api/auth/login/` | POST | Log in with `username` and `password`; returns token/profile. |
| `/api/me/` | GET, PATCH | Read or update the authenticated resident's profile. |
| `/api/me/location/` | PUT | Update only the logged-in user's location with `latitude` and `longitude`. |
| `/api/areas/` | GET | List township areas and their map boundaries. |
| `/api/properties/` | GET | Admins see all properties; residents see only their assigned residence. |
| `/api/incidents/` | GET, POST | List permitted SOS incidents or trigger a new SOS. |
| `/api/incidents/{id}/acknowledge/` | POST | Security or eligible volunteers acknowledge an SOS. |
| `/api/posts/` | GET, POST, PATCH | Safety feed and hazard reports. |
| `/api/devices/` | GET, POST, PATCH, DELETE | Register/manage the current user's mobile devices. |
| `/api/users/` | CRUD | Township-admin user management only. |

Example Flutter login request body:

```json
{"username": "resident01", "password": "your-password"}
```

Example authenticated request header:

```text
Authorization: Token <token returned at login>
```

## Scheduled processing

Run the following command every minute using Task Scheduler, cron, or a worker platform:

```powershell
python manage.py process_sos
```

It escalates unacknowledged SOS incidents and removes stale user locations. Push delivery itself still needs an FCM provider integration.
