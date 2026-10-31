"""Test fixtures. Tests run against PostgreSQL (TEST_DATABASE_URL, default: local dev cluster db tandem_test).
External providers are never called: AI providers are faked or mocked with respx, geocoding is offline."""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import text

from app import create_app
from app.extensions import db

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://tandem@127.0.0.1:5433/tandem_test")


@pytest.fixture(scope="session")
def app():
    storage_dir = tempfile.mkdtemp(prefix="tandem-test-storage-")
    for key in ("GEMINI_API_KEY", "ZAI_API_KEY", "GROQ_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
                "BOOKING_COM_API_TOKEN", "VIATOR_API_KEY"):
        os.environ.pop(key, None)
    app = create_app({
        "TESTING": True, "SQLALCHEMY_DATABASE_URI": TEST_DB, "JOB_RUNNER": "inline", "RATELIMIT_ENABLED": False,
        "LOCATION_PROVIDER": "offline", "STORAGE_LOCAL_PATH": storage_dir, "OSM_PLACES_ENABLED": False,
        "WEATHER_ENABLED": False, "NEWS_ENABLED": False,  # no network in tests; test_trip_context mocks it
        "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests", "GEMINI_API_KEY": "", "ZAI_API_KEY": "",
        "GROQ_API_KEY": "", "GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": "", "DEMO_ALLOW_EXTERNAL_AI": False,
        "BROWSER_WORKER_ENABLED": False, "BROWSER_ASSIST_SITES": "",
    })
    from app.extensions import limiter

    limiter.enabled = False
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        yield
        db.session.remove()
        tables = ", ".join(f'"{t.name}"' for t in reversed(db.metadata.sorted_tables))
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()


class ApiClient:
    def __init__(self, client):
        self.client = client
        self.csrf = None

    def _headers(self, extra=None):
        h = {"X-Tandem-Locale": "en", **({"X-CSRF-Token": self.csrf} if self.csrf else {})}
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.client.get(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json, headers=self._headers(kw.pop("headers", None)), **kw)

    def patch(self, url, json=None, **kw):
        return self.client.patch(url, json=json, headers=self._headers(kw.pop("headers", None)), **kw)

    def put(self, url, json=None, **kw):
        return self.client.put(url, json=json, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def register(self, email="traveller@example.com", password="correct horse battery", name="Test Traveller"):
        # The English suite: accounts are created in English (Romanian is covered in test_i18n.py).
        r = self.client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": name, "locale": "en"})
        assert r.status_code == 201, r.get_json()
        self.csrf = r.get_json()["data"]["csrf_token"]
        return r.get_json()["data"]["user"]

    def demo(self):
        r = self.client.post("/api/v1/auth/demo", json={"locale": "en"})
        assert r.status_code == 201, r.get_json()
        self.csrf = r.get_json()["data"]["csrf_token"]
        return r.get_json()["data"]["user"]


@pytest.fixture
def api(app):
    return ApiClient(app.test_client())


@pytest.fixture
def other_api(app):
    return ApiClient(app.test_client())


@pytest.fixture
def user_api(api):
    api.register()
    return api


def upload(api, filename, data, mime):
    import io

    return api.client.post("/api/v1/inbox/upload", data={"files": [(io.BytesIO(data), filename, mime)]},
                           headers=api._headers(), content_type="multipart/form-data")
