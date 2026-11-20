import os, platform, time, uuid
from datetime import datetime, timezone
import psutil, requests
API=os.environ.get("OZHEX_API_URL","http://127.0.0.1:8000").rstrip("/")
TOKEN=os.environ.get("OZHEX_ACCESS_TOKEN","")
KEY=os.environ.get("OZHEX_DEVICE_KEY",str(uuid.uuid4()))
LABEL=os.environ.get("OZHEX_DEVICE_LABEL",platform.node())
NAMES={x.strip().lower() for x in os.environ.get("WHATSAPP_PROCESS_NAMES","WhatsApp.exe").split(",") if x.strip()}
INTERVAL=max(3,int(os.environ.get("POLL_INTERVAL_SECONDS","5")))
def request(method,path,**kwargs):
 r=requests.request(method,API+path,headers={"Authorization":"Bearer "+TOKEN},timeout=15,**kwargs);r.raise_for_status();return r.json() if r.content else None
def running():
 for p in psutil.process_iter(["name"]):
  try:
   if (p.info.get("name") or "").lower() in NAMES:return True
  except (psutil.NoSuchProcess,psutil.AccessDenied):pass
 return False
def main():
 if not TOKEN:raise SystemExit("Set OZHEX_ACCESS_TOKEN before starting the agent.")
 request("POST","/api/v1/devices",json={"device_key":KEY,"platform":"windows","label":LABEL});previous=None
 print("Ozhex Windows agent started. Ctrl+C stops monitoring.")
 while True:
  state=running()
  if state!=previous:
   request("POST","/api/v1/activity",json={"device_key":KEY,"event_type":"foreground" if state else "background","occurred_at":datetime.now(timezone.utc).isoformat()});print(datetime.now().isoformat(timespec="seconds"),"WhatsApp", "running" if state else "not running");previous=state
  time.sleep(INTERVAL)
if __name__=="__main__":main()
