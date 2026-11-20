# OzhexWhatsappBot

Consent-based WhatsApp usage telemetry and official WhatsApp Business Cloud API event capture. Target clients: Android, Windows and Web, with a FastAPI backend.

## Boundaries
- A device reports only its own WhatsApp app foreground/background transitions after explicit opt-in.
- This is local app usage, **not** WhatsApp server online/last-seen status.
- Shared activity is not available until the account owner grants consent.
- Business events are received through signed Meta webhooks. No WhatsApp Web scraping or unofficial protocol.

## Backend quick start
Python 3.11+:
1. cd backend
2. py -3.11 -m venv .venv
3. .\.venv\Scripts\Activate.ps1
4. pip install -r requirements.txt
5. Copy .env.example to .env and set JWT_SECRET, BOOTSTRAP_TOKEN, META_VERIFY_TOKEN and META_APP_SECRET.
6. uvicorn app.main:app --reload

Dashboard: http://127.0.0.1:8000/ ; API docs: http://127.0.0.1:8000/docs.

Create the first administrator once:
```powershell
$body = @{ email = "admin@example.com"; password = "Use-A-Long-Unique-Password" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/bootstrap -Headers @{ "X-Bootstrap-Token" = "your-bootstrap-token" } -ContentType "application/json" -Body $body
```
After bootstrap, remove BOOTSTRAP_TOKEN from the production environment. PostgreSQL is recommended for deployment; SQLite works for local development.

## Meta webhook
Callback URL: https://YOUR_HOST/api/v1/webhooks/meta. Configure the same verify token in Meta, subscribe to messages, and set META_APP_SECRET. The webhook verifies X-Hub-Signature-256 and persists inbound messages and delivery/read status events.

## Clients
Android Usage Access client and Windows WhatsApp process agent are being added on the feature branch. Device clients authenticate with the same account token and must register only after consent is enabled.

## Validation
No CI workflow is configured or run. Run local tests after installing dependencies; do not expose the development server publicly. Production deployment requires HTTPS, backups, rate limiting, retention controls, and a privacy notice.
