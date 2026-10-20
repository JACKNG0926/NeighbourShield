# NeighbourShield Web Backend — Complete Setup & Run Guide

A step-by-step, comprehensive manual for installing prerequisites, configuring the environment, initializing the database, and running the **NeighbourShield** township safety backend (Django REST API, Web Dashboard, and SOS Escalation Engine).

---

## 📋 Table of Contents

1. [System Architecture & Components](#1-system-architecture--components)
2. [Prerequisites & Software to Install](#2-prerequisites--software-to-install)
3. [Step 1: Clone / Open the Project](#step-1-clone--open-the-project)
4. [Step 2: Set Up Python Virtual Environment](#step-2-set-up-python-virtual-environment)
5. [Step 3: Install Required Python Packages](#step-3-install-required-python-packages)
6. [Step 4: Database Configuration (MySQL vs SQLite)](#step-4-database-configuration)
   - [Option A: MySQL (Default / Production-like)](#option-a-mysql-default--production-like)
   - [Option B: SQLite (Fast / Zero External Setup)](#option-b-sqlite-fast--zero-external-setup)
7. [Step 5: Network & Allowed Hosts Configuration](#step-5-network--allowed-hosts-configuration)
8. [Step 6: Initialize Database & Create Admin User](#step-6-initialize-database--create-admin-user)
9. [Step 7: Run the Application (Dual Terminal Execution)](#step-7-run-the-application-dual-terminal-execution)
10. [Step 8: Verify Setup & Explore Web Pages](#step-8-verify-setup--explore-web-pages)
11. [Step 9: Connecting Flutter Mobile App](#step-9-connecting-flutter-mobile-app)
12. [Troubleshooting & Common Errors](#troubleshooting--common-errors)

---

## 1. System Architecture & Components

NeighbourShield consists of two concurrently running processes:

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Web Server & REST API** | Django 6 / Django REST Framework | Serves the Township Web Dashboard, Admin interface, and JSON API for Flutter mobile app |
| **Escalation Engine** | Django Management Command (`run_escalation`) | Continuous background daemon that monitors pending SOS incidents, triggers escalation levels, and purges stale responder GPS coordinates |

Both processes share the same database and must run at the same time.

---

## 2. Prerequisites & Software to Install

Before setting up the repository, make sure the following software is installed on your Windows machine:

### 1. Python 3.12 (or 3.11+)
- Download from [python.org](https://www.python.org/downloads/).
- ⚠️ **Important during installation**: Check the box **"Add python.exe to PATH"**.
- *Windows Tip*: If running `python` opens the Microsoft Store, disable App Execution Aliases:
  > **Windows Settings** → **Apps** → **Advanced app settings** → **App execution aliases** → Turn off `App Installer` for `python.exe` and `python3.exe`.

### 2. Git
- Download from [git-scm.com](https://git-scm.com/downloads) if not already installed.

### 3. MySQL Server (Only if choosing MySQL)
- You can use any of the following:
  - **MySQL Community Server**: [dev.mysql.com/downloads/installer/](https://dev.mysql.com/downloads/installer/) (installs MySQL as a Windows background service, typically named `MySQL80` for MySQL 8.0 or MySQL 8.4 LTS).
  - **XAMPP** (Easiest GUI bundle — starts Apache & MySQL with 1 click): [apachefriends.org](https://www.apachefriends.org/)
  - **Docker MySQL container**: `docker run --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=12345 -d mysql:8.0`
- *(Note: If you do not want to install MySQL, you can use the built-in SQLite database — see [Step 4: Option B](#option-b-sqlite-fast--zero-external-setup)).*

---

## Step 1: Clone / Open the Project

Open **PowerShell** or **Command Prompt** and navigate to your workspace directory:

```powershell
cd c:\Users\User\Downloads\Github\NeighbourShield_Web
```

Verify you are in the directory containing `manage.py`, `neighbour_shield_backend/`, and `core/`.

---

## Step 2: Set Up Python Virtual Environment

A virtual environment prevents conflicts between project packages and system-wide packages.

### 2.1 Enable PowerShell Script Execution (Windows Only)
Run this once in PowerShell so virtual environment activation scripts can execute:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

### 2.2 Create Virtual Environment
Create a fresh virtual environment named `venv`:

```powershell
python -m venv venv
```

*(Note: If you have multiple Python versions or use Anaconda, specify the Python 3.12 path, e.g., `py -3.12 -m venv venv`)*.

### 2.3 Activate the Virtual Environment

**In PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

**In Command Prompt (CMD):**
```cmd
.\venv\Scripts\activate.bat
```

**In Git Bash:**
```bash
source venv/Scripts/activate
```

*When activated, your terminal prompt will show `(venv)` at the beginning.*

---

## Step 3: Install Required Python Packages

With your virtual environment activated, upgrade `pip` and install all dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pymysql
```

### Why `pymysql` & MySQL 8.0 Compatibility?
The project configuration in `neighbour_shield_backend/__init__.py` sets up `pymysql` and ensures seamless compatibility:
```python
import pymysql

pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()

# Django 6.x requires MySQL 8.4+ by default; bypass check to allow MySQL 8.0.x
from django.db.backends.mysql.base import DatabaseWrapper
DatabaseWrapper.check_database_version_supported = lambda self: None
```
This accomplishes two things:
1. Provides full MySQL connectivity without needing Microsoft Visual C++ Build Tools.
2. Allows Django 6 to connect directly to MySQL 8.0.x (like MySQL 8.0.46) without throwing `NotSupportedError: MySQL 8.4 or later is required`.

---

## Step 4: Database Configuration

Choose **Option A (MySQL)** or **Option B (SQLite)**:

### Option A: MySQL (Default / Production-like)

The project `neighbour_shield_backend/settings.py` is configured for MySQL:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'sime',
        'USER': 'root',
        'PASSWORD': 'your_mysql_password', # Change to match your MySQL root password
        'HOST': 'localhost',
        'PORT': '3306',
    }
}
```

#### A.1 Start your MySQL service

##### 🔹 If using MySQL Community Server (Windows Service):
MySQL Community Server installs on Windows as a background service, typically named **`MySQL80`** (for MySQL 8.x) or **`MySQL`**.

**Check if MySQL service is installed & running:**
Run this in PowerShell:
```powershell
Get-Service *mysql*
```
You will see output like:
```text
Status   Name       DisplayName
------   ----       -----------
Running  MySQL80    MySQL80
```

If it is stopped, you can start it using any of the following methods:

- **Method 1: PowerShell (Run as Administrator)**
  ```powershell
  Start-Service MySQL80
  ```
  *(To verify status: `Get-Service MySQL80`)*

- **Method 2: Command Prompt / CMD (Run as Administrator)**
  ```cmd
  net start MySQL80
  ```
  *(Note: If your service is named `MySQL` instead of `MySQL80`, use `net start MySQL`)*.

- **Method 3: Windows Services Management Console (GUI)**
  1. Press `Win + R`, type `services.msc`, and press **Enter**.
  2. Scroll down to find **MySQL80** (or **MySQL**).
  3. Right-click on it and click **Start** (or **Restart**).
  4. *(Recommended)* Right-click → **Properties** → set **Startup type** to **Automatic** so MySQL always starts automatically when Windows boots.

##### 🔹 If using XAMPP:
- Open **XAMPP Control Panel**.
- Click the **Start** button next to **MySQL** (port 3306 will turn green).

##### 🔹 If using Docker:
```powershell
docker start mysql
```

---

#### A.2 Create the database in MySQL

Before Django can migrate tables, the database `sime` must exist.

**1. Access the MySQL command prompt:**
- Open **MySQL 8.0 Command Line Client** from the Windows Start Menu, OR
- In PowerShell / CMD, run:
  ```powershell
  mysql -u root -p
  ```
  *(Enter your MySQL root password when prompted).*

**2. Create the `sime` database:**
```sql
CREATE DATABASE IF NOT EXISTS sime CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**3. Verify creation and exit:**
```sql
SHOW DATABASES;
EXIT;
```

#### A.3 Update Credentials in `neighbour_shield_backend/settings.py`
Open `neighbour_shield_backend/settings.py` and ensure the password matches your actual MySQL root password (around line 95):

```python
'PASSWORD': 'your_actual_password',
```

---

### Option B: SQLite (Fast / Zero External Setup)

If you do not have MySQL installed and want to run immediately:

1. Open `neighbour_shield_backend/settings.py`.
2. Locate the `DATABASES` section (around lines 90–99).
3. Replace it with SQLite:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

*(The repository already includes a pre-migrated `db.sqlite3` with existing schema!)*

---

## Step 5: Network & Allowed Hosts Configuration

By default, Django restricts HTTP Host headers for security.

Open `neighbour_shield_backend/settings.py` and inspect `ALLOWED_HOSTS` (around line 28).

Update `ALLOWED_HOSTS` to allow local browser access and local network testing:

```python
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '192.168.0.5',
    '*',  # Allows connection from any IP/Flutter emulator during development
]
```

---

## Step 6: Initialize Database & Create Admin User

Run the following commands in your activated virtual environment:

### 6.1 Apply Migrations
Creates all database tables (for areas, properties, incidents, users, authentication tokens, safety posts):

```powershell
python manage.py migrate
```

### 6.2 Create Township Administrator / Superuser
To log into the Django Admin and Township Management dashboard, create a superuser account:

```powershell
python manage.py createsuperuser
```
Follow the interactive prompts:
- **Username**: `admin` (or your preferred username)
- **Email**: `admin@example.com`
- **Password**: `your_secure_password`

*(Note: In NeighbourShield, any user with `is_superuser = True` or role `admin` is automatically granted full Township Administrator access).*

### 6.3 (Optional) Load Sample Fixture Data
To populate the database with pre-configured areas, user accounts, and sample safety posts:

```powershell
python manage.py loaddata data.json
```

---

## Step 7: Run the Application (Dual Terminal Execution)

To run the entire system, **two separate terminals** are required:

### 🖥️ Terminal 1 — Django Web Server & REST API

Open your first terminal:

```powershell
cd c:\Users\User\Downloads\Github\NeighbourShield_Web
.\venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

> **Tip for Flutter / LAN Testing**: If you want other devices on your Wi-Fi or Flutter mobile devices to access the backend, bind to `0.0.0.0`:
> ```powershell
> python manage.py runserver 0.0.0.0:8000
> ```

---

### ⚙️ Terminal 2 — SOS Escalation Engine & Location Cleaner

Open a second terminal window:

```powershell
cd c:\Users\User\Downloads\Github\NeighbourShield_Web
.\venv\Scripts\Activate.ps1
python manage.py run_escalation
```

#### What does `run_escalation` do?
- Loops every 15 seconds.
- Automatically checks for unacknowledged SOS incidents and escalates them to the next tier (e.g. from local volunteers to security dispatch).
- Purges stale GPS coordinates older than 10 minutes for user privacy.

*(Alternative for production cron/Task Scheduler: `python manage.py process_sos` runs a single check and exits).*

---

## Step 8: Verify Setup & Explore Web Pages

Once both terminals are running, open your browser:

### 1. Township Safety Dashboard
- **URL**: `http://127.0.0.1:8000/`
- **Access**: Requires Township Admin login (redirects to `/admin/login/`).
- **Features**: Visual overview of SOS alerts, active incidents, resolved cases, and quick metrics.

### 2. Township Area & Property Registration
- **URL**: `http://127.0.0.1:8000/township/`
- **Features**: Register new township sectors/areas (with GPS boundary radius) and assign properties/houses.

### 3. Emergency Broadcast Center
- **URL**: `http://127.0.0.1:8000/broadcast/`
- **Features**: Broadcast high-priority safety alerts to selected township zones.

### 4. Django Admin Portal
- **URL**: `http://127.0.0.1:8000/admin/`
- **Features**: Full database management for Users, Tokens, Incidents, Escalation Policies, and Devices.

---

## Step 9: Connecting Flutter Mobile App

The NeighbourShield Flutter mobile app interacts with the backend via the `/api/` endpoints:

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/auth/register/` | POST | Register resident account |
| `/api/auth/login/` | POST | Login and receive authentication token |
| `/api/me/` | GET, PATCH | View and update resident profile |
| `/api/me/location/` | PUT | Push resident/responder live GPS location |
| `/api/incidents/` | GET, POST | Trigger or view SOS incidents |
| `/api/incidents/<id>/acknowledge/` | POST | Security / Volunteer accepts an SOS dispatch |
| `/api/posts/` | GET, POST | Community safety bulletin & hazard reports |
| `/api/devices/` | POST | Register FCM push device token |

### Mobile Network Configuration:
When testing the Flutter app on a physical phone or external emulator:
1. Find your computer's local IP address using `ipconfig` (e.g., `192.168.0.15`).
2. Run Django on `0.0.0.0:8000`:
   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```
3. In Flutter, configure your `baseUrl` to:
   ```dart
   const String baseUrl = 'http://192.168.0.15:8000/api/';
   ```
4. Authenticate subsequent requests by passing the HTTP header:
   ```http
   Authorization: Token <your_token_here>
   ```

---

## Troubleshooting & Common Errors

### 1. `OperationalError: (2003, "Can't connect to MySQL server on 'localhost'")`
- **Cause**: MySQL server is not running or port 3306 is blocked.
- **Fix**:
  - **MySQL Community Server**:
    - Open PowerShell as Administrator and run:
      ```powershell
      Start-Service MySQL80
      ```
    - Or open `services.msc`, locate `MySQL80` (or `MySQL`), and click **Start**.
  - **XAMPP**: Open XAMPP Control Panel and click **Start** next to MySQL.
  - **Fallback to SQLite**: Switch `DATABASES` to **SQLite** in `neighbour_shield_backend/settings.py` (see [Step 4: Option B](#option-b-sqlite-fast--zero-external-setup)).

### 2. `django.db.utils.NotSupportedError: MySQL 8.4 or later is required (found 8.0.46)`
- **Cause**: Django 6.x officially raised its minimum required MySQL version to MySQL 8.4 (LTS), rejecting MySQL 8.0.x by default.
- **Solution 1 (Recommended — Zero Upgrade Required)**:
  MySQL 8.0.46 is completely compatible with NeighbourShield. The repository already includes a bypass in [`neighbour_shield_backend/__init__.py`](file:///C:/Users/User/Downloads/Github/NeighbourShield_Web/neighbour_shield_backend/__init__.py):
  ```python
  from django.db.backends.mysql.base import DatabaseWrapper
  DatabaseWrapper.check_database_version_supported = lambda self: None
  ```
  With this snippet in place, you can run `python manage.py migrate` directly against your existing MySQL 8.0.46 installation!
- **Solution 2 (If you want to upgrade MySQL Community Server to 8.4 LTS)**:
  - **Why MySQL Installer didn't show an update**: In **MySQL Installer - Community**, MySQL 8.4 is an **LTS Major Release Track**, not an in-place minor patch of 8.0. It therefore does not appear under the simple "Upgrade" tab.
  - **How to install 8.4 via MySQL Installer**:
    1. Open **MySQL Installer - Community**.
    2. Click the **Catalog** button in the lower-right corner to fetch Oracle's latest manifest.
    3. Click the **Add...** button on the right side.
    4. Expand **MySQL Servers** → **MySQL Server** → **MySQL Server 8.4** → select the version and click the green arrow **→** to add it to the install list.
    5. Click **Next** and complete the wizard.
  - **Direct Download (Alternative)**:
    - Download the standalone **MySQL Community Server 8.4 LTS MSI** directly from [dev.mysql.com/downloads/mysql/8.4.html](https://dev.mysql.com/downloads/mysql/8.4.html).

### 3. `django.core.exceptions.DisallowedHost: Invalid HTTP_HOST header: 'localhost:8000'`
- **Cause**: `ALLOWED_HOSTS` in `neighbour_shield_backend/settings.py` does not include `localhost` or `127.0.0.1`.
- **Fix**: Update `ALLOWED_HOSTS = ['*']` or add `'localhost'`, `'127.0.0.1'` to the list.

### 4. `File Activate.ps1 cannot be loaded because running scripts is disabled`
- **Cause**: Windows PowerShell security policy blocks script execution by default.
- **Fix**: Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` in PowerShell, then re-run `.\venv\Scripts\Activate.ps1`.

### 5. `Python was not found; run without arguments to install...`
- **Cause**: Windows App Execution Aliases are redirecting `python` to the Microsoft Store.
- **Fix**:
  1. Open Windows **Settings** → Search for **"Manage app execution aliases"**.
  2. Toggle **OFF** `python.exe` and `python3.exe`.
  3. Ensure your Python installation path is in your Windows `PATH` environment variable.

### 6. `django.db.utils.ProgrammingError: (1146, "Table 'sime.core_user' doesn't exist")`
- **Cause**: Database tables have not been created yet.
- **Fix**: Run `python manage.py migrate`.

---

## Quick Command Reference Cheatsheet

```powershell
# 0. Check & Start MySQL Community Server (if needed)
Get-Service *mysql*
Start-Service MySQL80

# 1. Activate venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
pip install pymysql

# 3. Apply migrations
python manage.py migrate

# 4. Create admin user
python manage.py createsuperuser

# 5. Start Web Server (Terminal 1)
python manage.py runserver 127.0.0.1:8000

# 6. Start Escalation Engine (Terminal 2)
python manage.py run_escalation
```
