# Jenga

Jenga is a savings and small-business finance MVP built with Django. This repository contains **both the backend and frontend**: a JSON API, Django HTML templates, CSS and browser JavaScript. The current frontend runs from Django; no separate Node frontend server is required.

## What is implemented

- Phone-number registration and password login, member profiles and language preferences.
- A member dashboard, income/expense tracking, savings goals, planning and retirement calculations.
- Recorded bank/SACCO accounts with interest rates and minimum deposits.
- An AI assistant page and personal savings insights, including illustrative return projections.
- A public partnerships page for collaboration with banks and SACCOs.
- A dedicated SACCO login and reports restricted to that SACCO's participating members.
- A simple admin workspace for adding SACCOs/banks, creating users/admins, deleting users and assigning SACCO access.

**SMS/OTP recovery is not part of the MVP.** Administrators handle password help after verifying identity. There are no shared or seeded demo login credentials.

## Project structure

```text
Jenga/
|-- manage.py                 # Django commands
|-- requirements.txt          # Python dependencies
|-- .env.example              # Environment variable template
|-- config/                   # Settings, page views and root URL routes
|-- api/v1/                   # API route includes
|-- apps/
|   |-- accounts/             # Users, authentication and recorded partner accounts
|   |-- transactions/         # Income and expenses
|   |-- goals/                # Savings goals
|   |-- planning/             # Financial planning calculations
|   |-- retirement/           # Retirement calculations
|   |-- commitments/          # Retained backend functionality; no navigation page
|   |-- assistant/            # Chat and language integrations
|   `-- insights/             # Personal insights, SACCO access and aggregate reports
|-- templates/                # Pages and shared navigation/styles/scripts
`-- docs/                     # Feature setup and reporting details
```

Within an app, `models.py` defines stored data, `serializers.py` validates API data, `views.py` handles requests, `urls.py` maps addresses to handlers, and `migrations/` tracks database changes. Some apps also use `services.py` for calculations.

## Local setup: Windows, VS Code and PowerShell

Use **Python 3.12** for the documented setup (tested locally with 3.12.10) and PostgreSQL (tested locally with 17.5). The repository does not pin an exact Python version. Dependencies are listed in `requirements.txt`, including Django, Django REST Framework, SimpleJWT, psycopg, python-dotenv, django-cors-headers, google-genai and requests.

Run all commands below from the repository root, the folder containing `manage.py`. Open that folder in VS Code and use its PowerShell terminal.

### 1. Select the project and activate a virtual environment

Replace the path if your checkout is elsewhere:

```powershell
Set-Location "C:\Users\mable\Desktop\Jenga"
python --version
psql --version
```

For a new checkout, create the environment once:

```powershell
python -m venv venv
```

Activate it in each new terminal:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

In VS Code, use **Python: Select Interpreter** and select `venv\Scripts\python.exe`. If activation is blocked, you can use `.\venv\Scripts\python.exe` in place of `python` for the remaining commands.

### 2. Configure the local environment

Copy the template **only if `.env` does not already exist**:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env` privately. Replace the example secret and database credentials with your own values. Do not commit this file or share secret values.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required private Django signing key; replace the example placeholder. |
| `DEBUG` | Set `True` for local development. |
| `ALLOWED_HOSTS` | For local use: `localhost,127.0.0.1`. |
| `DB_NAME` | Name of your local PostgreSQL database. |
| `DB_USER`, `DB_PASSWORD` | Credentials for that database. |
| `DB_HOST` | Use `localhost` or `127.0.0.1` for local development. |
| `DB_PORT` | PostgreSQL port, normally `5432`. |
| `CORS_ALLOWED_ORIGINS` | Allowed origins for a separate API client; the bundled UI uses the same origin. |
| `CORS_ALLOW_ALL_ORIGINS` | Prefer `False` and explicit origins. |
| `GEMINI_API_KEY` | Needed for Gemini-generated assistant responses/AI explanations. |
| `GEMINI_MODEL` | Gemini model name used by the integration; verify availability for your account. |
| `SUNBIRD_API_TOKEN` | Needed for the Sunbird translation integration. |
| `SUNBIRD_TRANSLATE_URL` | Optional translation endpoint override; a default is defined in settings. |

Core authentication and SACCO access do not require AI-provider credentials. External AI/translation features depend on provider availability and credentials. No SMS-provider configuration is needed.

### 3. Create the development database

Ensure PostgreSQL is running. If the database does not exist, connect using your local PostgreSQL administrator (replace `postgres` if needed):

```powershell
psql -U postgres -h localhost
```

Inside the PostgreSQL prompt, create the database matching `DB_NAME`, for example:

```sql
CREATE DATABASE jenga;
\q
```

Use an existing database instead if it is already configured. **Before migrating, confirm that `.env` points to your local development database, not a shared or production database.**

### 4. Apply migrations and create your admin account

Back in PowerShell, from the repository root:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

Follow the prompts for the administrator's phone number, name and password. Skip `createsuperuser` if you already have an admin account. Credentials are chosen by you; there is no default admin password.

### 5. Start Django

```powershell
python manage.py check
python manage.py runserver
```

Open **http://127.0.0.1:8000/**. Stop the server with `Ctrl+C`.

## Pages and login credentials

| Page | Local URL | Access |
| --- | --- | --- |
| Landing page / member login | http://127.0.0.1:8000/ | Public; members use their registered phone and password. |
| Sign up | http://127.0.0.1:8000/signup/ | Public member registration. |
| Partnerships | http://127.0.0.1:8000/partnerships/ | Public collaboration information. |
| SACCO login | http://127.0.0.1:8000/sacco/login/ | Phone/password of an administrator-approved representative. |
| SACCO insights | http://127.0.0.1:8000/sacco/ | Active SACCO access required for report data. |
| Admin | http://127.0.0.1:8000/admin/ | Administrator credentials created with `createsuperuser`. |
| Savings goals | http://127.0.0.1:8000/goals/ | Member account. |
| Recorded partner accounts | http://127.0.0.1:8000/partners/ | Member account. |
| AI assistant | http://127.0.0.1:8000/assistant/ | Member account. |
| Personal insights | http://127.0.0.1:8000/insights/ | Member account. |
| Profile | http://127.0.0.1:8000/profile/ | Member account. |

The ordinary member login also sends approved SACCO representatives to their SACCO workspace. SACCO access does not grant Django admin access.

## Set up a SACCO for the MVP

Sign into `/admin/` as a superuser:

1. Open **Add institution** under **SACCOs and banks**, choose SACCO or Bank, and save its name.
2. Open **Add user**, enter the person's name, phone and password, and choose their role.
3. For a **SACCO representative**, select their SACCO. Choose **Administrator** to add another admin.
4. Use **Manage an existing user's SACCO** in the Users section to assign representative access or member affiliation. Leave SACCO empty to remove that assignment.
5. Each member enables sharing in their own Profile page; admins cannot consent for them.
6. The representative uses the account's phone and password at `/sacco/login/`.

The admin landing page shows only institutions and users. User deletion has a separate confirmation and removes associated records; deleting your own admin account is blocked.

Remove the SACCO login assignment to revoke SACCO reporting access, including for an existing login token. To help a user recover their account, verify their identity and use the user's **change password** action in Django admin. Password changes invalidate existing sessions.

SACCO reports contain group trends, not individual balances, names or personal transactions. They use only the assigned SACCO's active, consenting members. Reporting requires at least five members in a cohort or sector group; savings growth compares two completed month ends. A new database can therefore show **Not enough data** until sufficient history exists.

See [SACCO MVP setup](docs/sacco-mvp.md) and [insight calculations and privacy rules](docs/insights-and-sacco-access.md).

## API and verification

API routes use `/api/v1/`. This prefix is not an API index page. There is currently no Swagger/OpenAPI documentation page configured. The browser UI and API are served by the same Django process.

Selected endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/register/` | Register a member. |
| POST | `/api/v1/auth/login/` | Obtain member login tokens. |
| POST | `/api/v1/auth/sacco/login/` | Obtain tokens for an approved SACCO representative. |
| POST | `/api/v1/auth/refresh/` | Refresh a valid session. |
| GET / PATCH | `/api/v1/profile/` | Read/update your profile. |
| GET / POST | `/api/v1/partners/accounts/` | Read/add your recorded partner accounts. |
| POST | `/api/v1/insights/personal/` | Calculate personal savings insights. |
| GET | `/api/v1/insights/sacco/` | Read your SACCO's aggregate report. |
| POST | `/api/v1/assistant/ask/` | Ask the assistant. |

Protected API requests use `Authorization: Bearer <access-token>`. Django admin uses its own session login. SMS request and password-reset endpoints have been removed.

To verify the application, open the landing page, log into admin, and test a representative account through `/sacco/login/`. Unapproved users should be denied SACCO login; revoking approval should block report access.

Run automated checks from the repository root:

```powershell
python manage.py check
python manage.py test apps config
```

Django tests create a separate test database. The configured PostgreSQL user needs permission to create it; run tests against your local development configuration. Node.js is optional for running the application but is used by the JavaScript interaction checks, which skip when Node is unavailable.

## MVP limitations

Partner accounts and savings figures are recorded in Jenga; there is no live bank/SACCO connection, money movement, subscription billing or loan-disbursement tracking. Return projections use recorded terms and assumptions, not guaranteed returns. Aggregate savings trends cannot prove how loan funds were spent. SMS/OTP verification is deferred.


### Bank representatives and the institution directory

After adding a bank or SACCO, create an **Add user** account for its representative.
Choose **Bank representative** or **SACCO representative**, select the matching
institution, and set their phone and password. Both use the **Institution login**
page at `/sacco/login/`. An institution entry itself has no password.

Use **Manage an existing user's institution** to assign client memberships or
representative login access. Bank reports use only that bank's assigned, consenting
clients and the same aggregate privacy thresholds as SACCO reports.

New institutions appear in the member's **Add Partner** dropdown when opened.
Choosing a partner does not automatically enable data sharing. Admin logout returns
to the landing page. See [institution setup](docs/sacco-mvp.md) for details.


Institution insights also shows **Members on Jenga**: the current number of enabled
user accounts assigned to that bank or SACCO by an administrator. This includes
members who have not opted into financial reporting and is not a measure of recent
login activity. The count appears even when there is insufficient savings history.
Financial trends still require consent and the existing minimum group size; no
individual member details or balances are exposed.
