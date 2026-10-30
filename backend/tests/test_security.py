"""Authentication, sessions, CSRF, ownership isolation, upload validation, SSRF and sanitisation."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import UserSession
from app.services.demo import documents as D
from app.services.demo.seed import demo_start_date
from app.utils.errors import ValidationFailed
from tests.conftest import upload


def test_register_login_logout_me(api):
    api.register("a@example.com")
    me = api.get("/api/v1/auth/me").get_json()["data"]
    assert me["user"]["email"] == "a@example.com" and me["csrf_token"]
    assert api.post("/api/v1/auth/logout").status_code == 200
    assert api.get("/api/v1/auth/me").get_json()["data"]["user"] is None
    bad = api.client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong password!"})
    assert bad.status_code == 401
    good = api.client.post("/api/v1/auth/login", json={"email": "A@Example.com", "password": "correct horse battery"})
    assert good.status_code == 200


def test_duplicate_and_weak_registration(api):
    api.register("dup@example.com")
    r = api.client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "another long pw"})
    assert r.status_code == 409
    r = api.client.post("/api/v1/auth/register", json={"email": "weak@example.com", "password": "short"})
    assert r.status_code == 422


def test_csrf_required_for_writes(user_api):
    r = user_api.client.post("/api/v1/trips", json={"name": "No token"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "csrf_failed"
    assert user_api.post("/api/v1/trips", json={"name": "With token"}).status_code == 201


def test_session_expiry(user_api):
    for s in db.session.execute(db.select(UserSession)).scalars():
        s.expires_at = s.expires_at - timedelta(days=365)
    db.session.commit()
    assert user_api.get("/api/v1/trips").status_code == 401


def test_unauthenticated_access_blocked(api):
    for url in ("/api/v1/trips", "/api/v1/inbox", "/api/v1/approvals", "/api/v1/settings"):
        assert api.get(url).status_code == 401


def test_cross_user_isolation(user_api, other_api):
    trip = user_api.post("/api/v1/trips", json={"name": "Private"}).get_json()["data"]
    doc = upload(user_api, "hotel.pdf", D.hotel_confirmation(demo_start_date()), "application/pdf")
    doc_id = doc.get_json()["data"]["documents"][0]["id"]
    other_api.register("intruder@example.com")
    assert other_api.get(f"/api/v1/trips/{trip['id']}").status_code == 404
    assert other_api.patch(f"/api/v1/trips/{trip['id']}", json={"name": "x"}).status_code == 404
    assert other_api.get(f"/api/v1/inbox/{doc_id}").status_code == 404
    assert other_api.get(f"/api/v1/documents/{doc_id}/download").status_code == 404
    assert other_api.delete(f"/api/v1/inbox/{doc_id}").status_code == 404
    assert other_api.get("/api/v1/trips").get_json()["data"] == []
    # Uploading into someone else's trip is refused.
    r = other_api.client.post("/api/v1/inbox/upload", data={"trip_id": trip["id"], "files": []},
                              headers=other_api._headers(), content_type="multipart/form-data")
    assert r.status_code in (404, 422)


def test_upload_validation(user_api):
    r = upload(user_api, "malware.exe", b"MZ\x90\x00", "application/octet-stream")
    assert r.status_code == 422 and r.get_json()["data"]["errors"][0]["code"] == "unsupported_type"
    r = upload(user_api, "fake.pdf", b"<html>not a pdf</html>", "application/pdf")
    assert r.get_json()["data"]["errors"][0]["code"] == "signature_mismatch"
    r = upload(user_api, "image.png", D.flight_confirmation(demo_start_date()), "image/png")
    assert r.get_json()["data"]["errors"][0]["code"] in ("mime_mismatch", "signature_mismatch")
    big = b"%PDF-1.4\n" + b"0" * (21 * 1024 * 1024)
    r = upload(user_api, "big.pdf", big, "application/pdf")
    assert r.get_json()["data"]["errors"][0]["code"] == "file_too_large"


def test_duplicate_upload_detected(user_api):
    data = D.museum_ticket(demo_start_date())
    first = upload(user_api, "ticket.pdf", data, "application/pdf").get_json()["data"]["documents"][0]
    second = upload(user_api, "ticket copy.pdf", data, "application/pdf").get_json()["data"]["documents"][0]
    assert first["status"] == "awaiting_review"
    assert second["status"] == "duplicate" and second["duplicate_of_id"] == first["id"]


def test_download_is_private_and_attachment(user_api):
    data = D.museum_ticket(demo_start_date())
    doc = upload(user_api, "ticket.pdf", data, "application/pdf").get_json()["data"]["documents"][0]
    r = user_api.get(f"/api/v1/documents/{doc['id']}/download")
    assert r.status_code == 200 and r.data == data
    assert "attachment" in r.headers["Content-Disposition"]
    assert "sandbox" in r.headers["Content-Security-Policy"]


def test_stored_files_are_encrypted_at_rest(app, user_api):
    import os

    data = D.museum_ticket(demo_start_date())
    upload(user_api, "ticket.pdf", data, "application/pdf")
    root = app.config["STORAGE_LOCAL_PATH"]
    blobs = [open(os.path.join(d, f), "rb").read() for d, _, fs in os.walk(root) for f in fs]
    assert blobs and all(b"%PDF" not in b for b in blobs)


@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://localhost:5050/", "http://169.254.169.254/latest",
                                 "http://10.0.0.1/", "file:///etc/passwd", "http://example.com:8080/x",
                                 "http://user:pw@example.com/"])
def test_ssrf_blocked(user_api, url):
    r = user_api.post("/api/v1/inbox/url", json={"url": url})
    assert r.status_code == 422, (url, r.get_json())


def test_ssrf_checks_every_redirect(monkeypatch):
    from app.services.ingestion import safe_fetch

    seen = []
    monkeypatch.setattr(safe_fetch, "_check_host", lambda u: seen.append(u) or (
        (_ for _ in ()).throw(ValidationFailed("blocked", code="blocked_address")) if "internal" in u else None))

    import httpx

    def handler(request):
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://internal.example/secret"})
        return httpx.Response(200, text="secret", headers={"content-type": "text/plain"})

    real_client = httpx.Client
    monkeypatch.setattr(safe_fetch.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(ValidationFailed):
        safe_fetch.fetch("http://public.example/start", user_agent="t")
    assert seen == ["http://public.example/start", "http://internal.example/secret"]


def test_html_sanitised_and_pasted_scripts_inert(user_api):
    html = ('<html><body><h1>Booking</h1><script>alert(1)</script><img src="https://tracker/x.gif" onerror="x()">'
            '<a href="javascript:alert(1)">click</a><p>Reservation number: AB12345</p></body></html>').encode()
    doc = upload(user_api, "booking.html", html, "text/html").get_json()["data"]["documents"][0]
    prev = user_api.get(f"/api/v1/documents/{doc['id']}/preview").get_json()["data"]
    assert "<script" not in prev["html"] and "onerror" not in prev["html"] and "javascript:" not in prev["html"]
    assert "<img" not in prev["html"]


def test_security_headers(user_api):
    r = user_api.get("/api/v1/trips")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"


def test_data_export_and_account_deletion(user_api):
    user_api.post("/api/v1/trips", json={"name": "Export me"})
    r = user_api.get("/api/v1/settings/export")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    r = user_api.post("/api/v1/settings/delete-account", json={"password": "correct horse battery", "confirm": "DELETE"})
    assert r.status_code == 200
    assert user_api.get("/api/v1/trips").status_code == 401
    login = user_api.client.post("/api/v1/auth/login", json={"email": "traveller@example.com",
                                                             "password": "correct horse battery"})
    assert login.status_code == 401


def test_openapi_document(api):
    spec = api.get("/api/v1/openapi.json").get_json()
    assert spec["openapi"].startswith("3.1")
    assert "/api/v1/approvals/{action_id}/approve" in spec["paths"]
    assert "requestBody" in spec["paths"]["/api/v1/inbox/paste"]["post"]
