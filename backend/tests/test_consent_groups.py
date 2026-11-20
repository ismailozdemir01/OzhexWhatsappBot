from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main

def test_consent_gated_group_activity_and_revocation(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    main.Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", test_sessions)
    monkeypatch.setattr(main.cfg, "bootstrap_token", "one-time-test-token")
    monkeypatch.setattr(main.cfg, "jwt_secret", "test-secret-with-enough-entropy")
    client = TestClient(main.app)

    first = client.post("/api/v1/auth/bootstrap", headers={"X-Bootstrap-Token": "one-time-test-token"},
                        json={"email": "owner@example.com", "password": "Owner-password-123"})
    assert first.status_code == 200
    owner_token = first.json()["access_token"]
    owner = {"Authorization": f"Bearer {owner_token}"}

    assert client.put("/api/v1/consent", headers=owner,
                      json={"activity_sharing": True, "version": "1.0"}).status_code == 200
    device = {"device_key": "windows-device-001", "platform": "windows", "label": "Desktop"}
    assert client.post("/api/v1/devices", headers=owner, json=device).status_code == 200
    event = {"device_key": device["device_key"], "event_type": "foreground",
             "occurred_at": datetime.now(timezone.utc).isoformat()}
    assert client.post("/api/v1/activity", headers=owner, json=event).status_code == 200
    assert client.put("/api/v1/consent", headers=owner,
                      json={"activity_sharing": False, "version": "1.0"}).status_code == 200

    group = client.post("/api/v1/groups?name=Family", headers=owner)
    assert group.status_code == 200
    invite_code = group.json()["invite_code"]

    with test_sessions() as db:
        second_user = main.User(email="member@example.com", password_hash=main.pwd.hash("Member-password-123"))
        db.add(second_user)
        db.flush()
        db.add(main.Consent(user_id=second_user.id, activity_sharing=False))
        db.commit()
    login = client.post("/api/v1/auth/login", json={"email": "member@example.com", "password": "Member-password-123"})
    assert login.status_code == 200
    member = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/v1/groups/join", headers=member, params={"invite_code": invite_code}).status_code == 200

    # A group member must also opt in before viewing reciprocal activity.
    assert client.get(f"/api/v1/groups/{group.json()['id']}/activity", headers=member).status_code == 403
    assert client.put("/api/v1/consent", headers=member,
                      json={"activity_sharing": True, "version": "1.0"}).status_code == 200
    assert client.get(f"/api/v1/groups/{group.json()['id']}/activity", headers=member).json() == []
    assert client.put("/api/v1/consent", headers=owner,
                      json={"activity_sharing": True, "version": "1.0"}).status_code == 200
    # Re-enable the existing registered device after explicit consent is restored.
    assert client.post("/api/v1/devices", headers=owner, json=device).status_code == 200
    assert client.get(f"/api/v1/groups/{group.json()['id']}/activity", headers=member).json()
    assert client.put("/api/v1/consent", headers=owner,
                      json={"activity_sharing": False, "version": "1.0"}).status_code == 200
    assert client.get(f"/api/v1/groups/{group.json()['id']}/activity", headers=member).json() == []
