# OzhexWhatsappBot

Android + Windows + Web clients with a FastAPI backend for consent-based local WhatsApp usage telemetry and official WhatsApp Business Cloud API webhook capture.

## Data boundaries
- Android reports Usage Access foreground/background transitions for WhatsApp on the enrolled Android device.
- Windows reports whether the local WhatsApp Desktop process is running. It does not yet distinguish foreground from background windows.
- These are device-local usage signals, **not** WhatsApp server online/last-seen status.
- Sharing is disabled by default and requires the account owner to opt in.
- Business messages/status events arrive through signed Meta webhooks. No WhatsApp Web scraping or unofficial protocol.

## Backend setup
Python 3.11+:
```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```
Set a random JWT_SECRET (32+ random bytes), a one-time BOOTSTRAP_TOKEN, and Meta webhook secrets in .env. Then run:
```powershell
uvicorn app.main:app --reload
```
Dashboard: http://127.0.0.1:8000/ ; API docs: http://127.0.0.1:8000/docs.

Create the first administrator once:
```powershell
$body = @{ email = "admin@example.com"; password = "Use-A-Long-Unique-Password" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/bootstrap -Headers @{ "X-Bootstrap-Token" = "your-bootstrap-token" } -ContentType "application/json" -Body $body
```
Bootstrap is one-time: it rejects creation when an account already exists. Remove BOOTSTRAP_TOKEN from the production environment after setup. SQLite is suitable for local development; use PostgreSQL for deployment.

## Windows client
```powershell
cd windows-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OZHEX_API_URL="http://127.0.0.1:8000"
$env:OZHEX_ACCESS_TOKEN="<access-token>"
python agent.py
```
Enable activity sharing in the Web panel first. Set WHATSAPP_PROCESS_NAMES if the installed executable name differs.

## Android client
Open the android/ folder in Android Studio with JDK 17 and Android SDK 35. Install the app, grant Usage Access in Android Settings, enter the backend URL and access token, then explicitly enable the consent checkbox and start monitoring. A persistent foreground notification is displayed. Stop monitoring and revoke consent from the app at any time. For a physical phone, the backend must be reachable over HTTPS or the same trusted LAN; the emulator default URL is http://10.0.2.2:8000.

## Meta WhatsApp Cloud API
Set META_VERIFY_TOKEN and META_APP_SECRET in the backend environment. Set the Meta callback to https://YOUR_HOST/api/v1/webhooks/meta, configure the same verify token, subscribe to messages, and configure the app secret. The webhook validates X-Hub-Signature-256 and persists inbound messages and delivery/read status events. Outbound Cloud API messaging and customer conversation workflows are not implemented yet.

## Current implementation boundary
The branch contains the backend, consent/device APIs, browser dashboard, Android Usage Access client and Windows process monitor. Group-level participant sharing, production deployment hardening, outbound Business messaging, analytics aggregation, and client packaging remain subsequent implementation work.

No CI workflow is configured or run. Local verification has not yet been performed from a Windows checkout. Do not expose the development server publicly; production requires HTTPS, rate limiting, backups, retention/deletion controls, and a privacy notice.
