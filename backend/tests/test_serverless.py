"""Serverless (Vercel) support: database-backed storage, cron endpoint, database URL normalisation."""
from __future__ import annotations

from app.config import normalise_database_url
from app.extensions import db
from app.models import StoredObject
from app.services.demo import documents as D
from app.services.demo.seed import demo_start_date
from tests.conftest import upload


def test_database_url_normalisation():
    assert normalise_database_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalise_database_url("postgresql://u@h/db") == "postgresql+psycopg://u@h/db"
    assert normalise_database_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"


def test_database_storage_round_trip(app, user_api, monkeypatch):
    import app.services.storage as storage_mod

    monkeypatch.setitem(app.config, "STORAGE_TYPE", "database")
    monkeypatch.setattr(storage_mod, "_backend", None)
    data = D.museum_ticket(demo_start_date())
    doc = upload(user_api, "ticket.pdf", data, "application/pdf").get_json()["data"]["documents"][0]
    row = db.session.execute(db.select(StoredObject)).scalar_one()
    assert b"%PDF" not in bytes(row.data)  # encrypted at rest
    assert user_api.get(f"/api/v1/documents/{doc['id']}/download").data == data
    assert user_api.get(f"/api/v1/inbox/{doc['id']}").get_json()["data"]["status"] == "awaiting_review"
    user_api.delete(f"/api/v1/inbox/{doc['id']}")
    assert db.session.execute(db.select(StoredObject)).first() is None
    monkeypatch.setattr(storage_mod, "_backend", None)


def test_cron_requires_secret(app, api, monkeypatch):
    monkeypatch.setitem(app.config, "CRON_SECRET", "s3cret-value")
    assert api.get("/api/v1/internal/cron").status_code == 403
    assert api.get("/api/v1/internal/cron", headers={"Authorization": "Bearer wrong"}).status_code == 403
    r = api.get("/api/v1/internal/cron", headers={"Authorization": "Bearer s3cret-value"})
    assert r.status_code == 200 and "jobs_processed" in r.get_json()["data"]
    monkeypatch.setitem(app.config, "CRON_SECRET", "")
    assert api.get("/api/v1/internal/cron", headers={"Authorization": "Bearer "}).status_code == 403
