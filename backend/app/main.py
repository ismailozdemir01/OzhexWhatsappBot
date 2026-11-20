import hashlib, hmac, json, secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
import jwt
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings
from passlib.context import CryptContext
from sqlalchemy import create_engine, String, Integer, Boolean, DateTime, ForeignKey, JSON, select, desc, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./ozhex.db"
    jwt_secret: str = "development-secret-change-before-deploy"
    jwt_expire_minutes: int = 720
    bootstrap_token: str = ""
    meta_verify_token: str = ""
    meta_app_secret: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_graph_version: str = "v27.0"
    cors_origins: str = "http://127.0.0.1:8000"
    class Config: env_file = ".env"
cfg = Settings()
if cfg.app_env.lower() == "production" and cfg.jwt_secret == "development-secret-change-before-deploy":
    raise RuntimeError("Set a unique JWT_SECRET before production startup.")
engine = create_engine(cfg.database_url, connect_args={"check_same_thread":False} if cfg.database_url.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, autoflush=False, expire_on_commit=False)
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    email: Mapped[str]=mapped_column(String(320),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    is_admin: Mapped[bool]=mapped_column(Boolean,default=False)
class Consent(Base):
    __tablename__="consents"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),unique=True,index=True)
    activity_sharing: Mapped[bool]=mapped_column(Boolean,default=False)
    version: Mapped[str]=mapped_column(String(32),default="1.0")
    granted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class Device(Base):
    __tablename__="devices"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    device_key: Mapped[str]=mapped_column(String(128))
    platform: Mapped[str]=mapped_column(String(16))
    label: Mapped[str]=mapped_column(String(120),default="")
    enabled: Mapped[bool]=mapped_column(Boolean,default=True)
class Activity(Base):
    __tablename__="activity"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    device_id: Mapped[int]=mapped_column(ForeignKey("devices.id"),index=True)
    event_type: Mapped[str]=mapped_column(String(24))
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    source: Mapped[str]=mapped_column(String(16))
class BusinessEvent(Base):
    __tablename__="business_events"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    wamid: Mapped[str|None]=mapped_column(String(255),index=True,nullable=True)
    event_type: Mapped[str]=mapped_column(String(32),index=True)
    contact_wa_id: Mapped[str|None]=mapped_column(String(64),nullable=True)
    payload: Mapped[dict]=mapped_column(JSON)
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class ShareGroup(Base):
    __tablename__="share_groups"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    name: Mapped[str]=mapped_column(String(80))
    owner_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    invite_code: Mapped[str]=mapped_column(String(32),unique=True,index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class GroupMember(Base):
    __tablename__="group_members"
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    group_id: Mapped[int]=mapped_column(ForeignKey("share_groups.id"),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    joined_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint("group_id","user_id"),)
Base.metadata.create_all(engine)
pwd=CryptContext(schemes=["pbkdf2_sha256"],deprecated="auto")
bearer=HTTPBearer(auto_error=False)
app=FastAPI(title="Ozhex WhatsApp Platform",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in cfg.cors_origins.split(",") if x.strip()],allow_methods=["GET","POST","PUT"],allow_headers=["Authorization","Content-Type","X-Bootstrap-Token","X-Hub-Signature-256"])
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def auth_user(creds: HTTPAuthorizationCredentials|None=Depends(bearer),db:Session=Depends(get_db)):
    if not creds: raise HTTPException(401,"Bearer token required")
    try: uid=int(jwt.decode(creds.credentials,cfg.jwt_secret,algorithms=["HS256"])["sub"])
    except Exception: raise HTTPException(401,"Invalid or expired token")
    user=db.get(User,uid)
    if not user: raise HTTPException(401,"Account not found")
    return user
def token_for(uid:int):
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":str(uid),"iat":now,"exp":now+timedelta(minutes=cfg.jwt_expire_minutes)},cfg.jwt_secret,algorithm="HS256")
class Credentials(BaseModel):
    email: EmailStr
    password: str=Field(min_length=12,max_length=128)
class ConsentInput(BaseModel):
    activity_sharing: bool
    version: str=Field(default="1.0",max_length=32)
class DeviceInput(BaseModel):
    device_key:str=Field(min_length=8,max_length=128)
    platform:str=Field(pattern="^(android|windows|web)$")
    label:str=Field(default="",max_length=120)
class ActivityInput(BaseModel):
    device_key:str=Field(min_length=8,max_length=128)
    event_type:str=Field(pattern="^(foreground|background)$")
    occurred_at:datetime
class SendTextInput(BaseModel):
    to: str=Field(pattern="^\\+?[1-9][0-9]{7,14}$")
    text: str=Field(min_length=1,max_length=4096)
@app.get("/health")
def health(): return {"status":"ok","service":"ozhex-whatsapp-platform"}
@app.post("/api/v1/auth/bootstrap")
def bootstrap(data:Credentials,x_bootstrap_token:str=Header(default=""),db:Session=Depends(get_db)):
    if not cfg.bootstrap_token or not hmac.compare_digest(x_bootstrap_token,cfg.bootstrap_token): raise HTTPException(403,"Bootstrap disabled or invalid")
    if db.scalar(select(User.id).limit(1)) is not None: raise HTTPException(409,"Initial account already exists")
    user=User(email=data.email.lower(),password_hash=pwd.hash(data.password),is_admin=True)
    db.add(user);db.flush();db.add(Consent(user_id=user.id,activity_sharing=False));db.commit()
    return {"access_token":token_for(user.id),"token_type":"bearer"}
@app.post("/api/v1/auth/login")
def login(data:Credentials,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==data.email.lower()))
    if not user or not pwd.verify(data.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    return {"access_token":token_for(user.id),"token_type":"bearer"}
@app.get("/api/v1/me")
def me(user:User=Depends(auth_user)): return {"id":user.id,"email":user.email,"is_admin":user.is_admin}
@app.get("/api/v1/consent")
def get_consent(user:User=Depends(auth_user),db:Session=Depends(get_db)):
    c=db.scalar(select(Consent).where(Consent.user_id==user.id))
    if not c: c=Consent(user_id=user.id,activity_sharing=False);db.add(c);db.commit();db.refresh(c)
    return {"activity_sharing":c.activity_sharing,"version":c.version,"granted_at":c.granted_at,"revoked_at":c.revoked_at}
@app.put("/api/v1/consent")
def set_consent(data:ConsentInput,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    c=db.scalar(select(Consent).where(Consent.user_id==user.id))
    if not c: c=Consent(user_id=user.id,activity_sharing=False);db.add(c)
    now=datetime.now(timezone.utc);c.activity_sharing=data.activity_sharing;c.version=data.version
    if data.activity_sharing: c.granted_at=now;c.revoked_at=None
    else:
        c.revoked_at=now
        for d in db.scalars(select(Device).where(Device.user_id==user.id)).all(): d.enabled=False
    db.commit()
    return {"activity_sharing":c.activity_sharing,"version":c.version,"granted_at":c.granted_at,"revoked_at":c.revoked_at}
@app.post("/api/v1/devices")
def register_device(data:DeviceInput,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    c=db.scalar(select(Consent).where(Consent.user_id==user.id))
    if not c or not c.activity_sharing: raise HTTPException(403,"Explicit consent required")
    d=db.scalar(select(Device).where(Device.user_id==user.id,Device.device_key==data.device_key))
    if not d: d=Device(user_id=user.id,device_key=data.device_key,platform=data.platform);db.add(d)
    d.platform=data.platform;d.label=data.label;d.enabled=True;db.commit()
    return {"device_key":d.device_key,"enabled":d.enabled}
@app.post("/api/v1/activity")
def ingest(data:ActivityInput,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    c=db.scalar(select(Consent).where(Consent.user_id==user.id))
    if not c or not c.activity_sharing: raise HTTPException(403,"Activity sharing is disabled")
    d=db.scalar(select(Device).where(Device.user_id==user.id,Device.device_key==data.device_key,Device.enabled.is_(True)))
    if not d: raise HTTPException(404,"Enabled device not found")
    now=datetime.now(timezone.utc);when=data.occurred_at
    if when.tzinfo is None: when=when.replace(tzinfo=timezone.utc)
    if abs((now-when).total_seconds())>86400: raise HTTPException(422,"Timestamp outside allowed 24-hour window")
    db.add(Activity(user_id=user.id,device_id=d.id,event_type=data.event_type,occurred_at=when,source=d.platform));db.commit()
    return {"accepted":True}
@app.get("/api/v1/activity")
def activity(limit:int=100,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Activity).where(Activity.user_id==user.id).order_by(desc(Activity.occurred_at)).limit(min(max(limit,1),500))).all()
    return [{"event_type":x.event_type,"occurred_at":x.occurred_at.isoformat(),"source":x.source} for x in rows]
@app.post("/api/v1/groups")
def create_group(name:str,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    if not 1 <= len(name.strip()) <= 80: raise HTTPException(422,"Group name must be 1-80 characters")
    code=secrets.token_urlsafe(12)
    group=ShareGroup(name=name.strip(),owner_id=user.id,invite_code=code)
    db.add(group);db.flush();db.add(GroupMember(group_id=group.id,user_id=user.id));db.commit()
    return {"id":group.id,"name":group.name,"invite_code":group.invite_code}
@app.post("/api/v1/groups/join")
def join_group(invite_code:str,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    group=db.scalar(select(ShareGroup).where(ShareGroup.invite_code==invite_code))
    if not group: raise HTTPException(404,"Invalid group invitation")
    member=db.scalar(select(GroupMember).where(GroupMember.group_id==group.id,GroupMember.user_id==user.id))
    if not member: db.add(GroupMember(group_id=group.id,user_id=user.id));db.commit()
    return {"id":group.id,"name":group.name,"membership":"active"}
@app.get("/api/v1/groups")
def list_groups(user:User=Depends(auth_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(ShareGroup).join(GroupMember,GroupMember.group_id==ShareGroup.id).where(GroupMember.user_id==user.id)).all()
    return [{"id":g.id,"name":g.name,"is_owner":g.owner_id==user.id} for g in rows]
@app.get("/api/v1/groups/{group_id}/activity")
def group_activity(group_id:int,limit:int=100,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    member=db.scalar(select(GroupMember.id).where(GroupMember.group_id==group_id,GroupMember.user_id==user.id))
    if member is None: raise HTTPException(403,"Group membership required")
    rows=db.execute(select(Activity,User,Device).join(User,User.id==Activity.user_id).join(Device,Device.id==Activity.device_id).join(GroupMember,GroupMember.user_id==Activity.user_id).join(Consent,Consent.user_id==Activity.user_id).where(GroupMember.group_id==group_id,Consent.activity_sharing.is_(True),Device.enabled.is_(True)).order_by(desc(Activity.occurred_at)).limit(min(max(limit,1),500))).all()
    return [{"member":u.email,"event_type":a.event_type,"occurred_at":a.occurred_at.isoformat(),"platform":d.platform} for a,u,d in rows]
@app.post("/api/v1/business/messages")
async def send_business_text(data:SendTextInput,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    if not user.is_admin: raise HTTPException(403,"Administrator access required")
    if not cfg.meta_access_token or not cfg.meta_phone_number_id: raise HTTPException(503,"Meta Cloud API credentials are not configured")
    recipient=data.to.lstrip("+")
    payload={"messaging_product":"whatsapp","recipient_type":"individual","to":recipient,"type":"text","text":{"preview_url":False,"body":data.text}}
    url=f"https://graph.facebook.com/{cfg.meta_graph_version}/{cfg.meta_phone_number_id}/messages"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.post(url,headers={"Authorization":f"Bearer {cfg.meta_access_token}"},json=payload)
    except httpx.RequestError:
        raise HTTPException(502,"Meta Cloud API connection failed")
    if response.is_error:
        raise HTTPException(502,"Meta Cloud API rejected the message; check phone number, permissions, recipient and messaging window")
    try: result=response.json()
    except ValueError: raise HTTPException(502,"Meta Cloud API returned an invalid response")
    messages=result.get("messages") or []
    if not messages or not messages[0].get("id"): raise HTTPException(502,"Meta Cloud API response did not contain a message ID")
    wamid=messages[0]["id"]
    db.add(BusinessEvent(wamid=wamid,event_type="outbound_message",contact_wa_id=recipient,payload={"type":"text","text":data.text}))
    db.commit()
    return {"accepted":True,"wamid":wamid}
@app.get("/api/v1/business/analytics")
def business_analytics(user:User=Depends(auth_user),db:Session=Depends(get_db)):
    if not user.is_admin: raise HTTPException(403,"Administrator access required")
    rows=db.scalars(select(BusinessEvent)).all()
    counts={}
    for row in rows: counts[row.event_type]=counts.get(row.event_type,0)+1
    return {"total_events":len(rows),"by_event_type":counts,"inbound_messages":counts.get("inbound_message",0),"outbound_messages":counts.get("outbound_message",0),"delivered":counts.get("status_delivered",0),"read":counts.get("status_read",0),"failed":counts.get("status_failed",0)}
@app.get("/api/v1/business/events")
def business_events(limit:int=100,user:User=Depends(auth_user),db:Session=Depends(get_db)):
    if not user.is_admin: raise HTTPException(403,"Administrator access required")
    rows=db.scalars(select(BusinessEvent).order_by(desc(BusinessEvent.occurred_at)).limit(min(max(limit,1),500))).all()
    return [{"wamid":x.wamid,"event_type":x.event_type,"contact_wa_id":x.contact_wa_id,"occurred_at":x.occurred_at.isoformat()} for x in rows]
@app.get("/api/v1/webhooks/meta")
def verify_webhook(request:Request):
    q=request.query_params
    if q.get("hub.mode")=="subscribe" and cfg.meta_verify_token and hmac.compare_digest(q.get("hub.verify_token",""),cfg.meta_verify_token):
        return Response(q.get("hub.challenge",""),media_type="text/plain")
    raise HTTPException(403,"Webhook verification failed")
@app.post("/api/v1/webhooks/meta")
async def receive_webhook(request:Request,x_hub_signature_256:str=Header(default=""),db:Session=Depends(get_db)):
    raw=await request.body()
    if not cfg.meta_app_secret: raise HTTPException(503,"META_APP_SECRET is not configured")
    digest=hmac.new(cfg.meta_app_secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(x_hub_signature_256,"sha256="+digest): raise HTTPException(401,"Invalid webhook signature")
    try: body=json.loads(raw)
    except json.JSONDecodeError: raise HTTPException(400,"Invalid JSON")
    for entry in body.get("entry",[]):
        for change in entry.get("changes",[]):
            value=change.get("value",{})
            for msg in value.get("messages",[]): db.add(BusinessEvent(wamid=msg.get("id"),event_type="inbound_message",contact_wa_id=msg.get("from"),payload=msg))
            for st in value.get("statuses",[]): db.add(BusinessEvent(wamid=st.get("id"),event_type="status_"+str(st.get("status","unknown")),contact_wa_id=st.get("recipient_id"),payload=st))
    db.commit()
    return {"received":True}
@app.get("/",response_class=HTMLResponse)
def dashboard(): return (Path(__file__).resolve().parents[2]/"web"/"index.html").read_text(encoding="utf-8")
