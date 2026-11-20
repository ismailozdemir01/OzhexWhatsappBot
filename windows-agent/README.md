# Windows agent

Install Python 3.11+, then run in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OZHEX_API_URL="http://127.0.0.1:8000"
$env:OZHEX_ACCESS_TOKEN="<your-access-token>"
python agent.py
```

The agent monitors the local WhatsApp Desktop process name only. If your package uses another executable name, set WHATSAPP_PROCESS_NAMES to a comma-separated list. It does not read messages, contacts, or browser sessions. Enable sharing in the Web dashboard before starting.
