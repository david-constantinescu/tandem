"""Tandem backend application factory."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from app.config import Config, load_dotenv, validate_config
from app.extensions import db, limiter, migrate
from app.i18n import tr
from app.utils.errors import APIError

BLUEPRINTS = (
    "app.api.health", "app.api.auth", "app.api.settings", "app.api.trips", "app.api.reservations",
    "app.api.itinerary", "app.api.inbox", "app.api.documents", "app.api.activities", "app.api.assistant",
    "app.api.approvals", "app.api.integrations", "app.api.notifications", "app.api.demo", "app.api.internal", "app.api.browser", "app.api.demo_sites",
    "app.api.calendar", "app.api.context", "app.api.openapi",
)


def create_app(overrides: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__, static_folder=None)
    app.config.update(Config().as_flask_dict())
    app.config.update(
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        MAX_CONTENT_LENGTH=None,  # uploads are size-checked per file in the ingestion pipeline
        JSON_SORT_KEYS=False,
    )
    if overrides:
        app.config.update(overrides)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        # Keep database sessions in UTC regardless of the server's local timezone.
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {**app.config["SQLALCHEMY_ENGINE_OPTIONS"],
                                                   "connect_args": {"options": "-c timezone=UTC"}}
    app.config["MAX_CONTENT_LENGTH"] = (
        app.config["MAX_UPLOAD_BYTES"] * app.config["MAX_FILES_PER_UPLOAD"] + 1024 * 1024
    )

    if app.config.get("TRUSTED_PROXIES"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        n = int(app.config["TRUSTED_PROXIES"])
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)  # type: ignore[method-assign]

    _configure_logging(app)
    for warning in validate_config(app.config):
        app.logger.warning("config: %s", warning)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent / "migrations"))
    app.config["RATELIMIT_ENABLED"] = app.config.get("RATELIMIT_ENABLED", True)
    limiter.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": [app.config["FRONTEND_URL"]]}}, supports_credentials=True)

    from importlib import import_module

    from app import models as _models  # noqa: F401 - register models with SQLAlchemy metadata
    from app.tasks import handlers as _handlers  # noqa: F401 - register job handlers

    for module_name in BLUEPRINTS:
        app.register_blueprint(import_module(module_name).bp)

    from app.api._core import load_session

    app.before_request(load_session)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_frontend(app)

    from app.cli import register_cli

    register_cli(app)
    return app


def _configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.config["APP_ENV"] == "development" and os.environ.get("TANDEM_DEBUG") else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Never log request bodies: they can contain travel documents and personal data.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)


def _register_error_handlers(app: Flask) -> None:
    from app.api._core import error_response

    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        db.session.rollback()
        return error_response(err)

    @app.errorhandler(HTTPException)
    def handle_http(err: HTTPException):
        if not request.path.startswith("/api/"):
            return err
        code = {413: "payload_too_large", 429: "rate_limited", 404: "not_found", 405: "method_not_allowed"}.get(
            err.code or 500, "http_error")
        return jsonify({"error": {"code": code, "message": tr(err.description or err.name)}}), err.code

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        db.session.rollback()
        app.logger.exception("unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": {"code": "internal_error", "message": tr("Something went wrong on our side.")}}), 500


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
            resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        else:
            resp.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: https://*.tile.openstreetmap.org; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
        if app.config["SESSION_COOKIE_SECURE"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp


def _register_frontend(app: Flask) -> None:
    """Serve the built SPA when present (single-origin deployments)."""
    dist = Path(app.config["FRONTEND_DIST"])

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path: str):
        if path.startswith("api/"):
            return jsonify({"error": {"code": "not_found", "message": "Unknown API route"}}), 404
        if not (dist / "index.html").exists():
            return jsonify({"service": "tandem-api", "frontend": "not built; run the Vite dev server"}), 200
        target = dist / path
        if path and target.is_file():
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")
