"""OpenAPI 3.1 document generated from the URL map, view metadata and Pydantic request models."""
from __future__ import annotations

import re

from flask import Blueprint, current_app

from app.api._core import OPENAPI_REGISTRY
from app.services.ai.schema_utils import inline_schema

bp = Blueprint("openapi", __name__, url_prefix="/api/v1")


def build_spec() -> dict:
    paths: dict = {}
    for rule in current_app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1") or rule.endpoint == "static":
            continue
        view = current_app.view_functions[rule.endpoint]
        meta = OPENAPI_REGISTRY.get(f"{view.__module__}.{view.__name__}")
        if meta is None:
            continue
        path = re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", r"{\1}", rule.rule)
        for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            op: dict = {"summary": meta["summary"], "tags": [meta["tag"] or "General"],
                        "responses": {"200": {"description": "Success: {\"data\": ...}"},
                                      "4XX": {"description": "Error: {\"error\": {\"code\", \"message\"}}"}}}
            params = [{"name": p, "in": "path", "required": True, "schema": {"type": "string"}}
                      for p in re.findall(r"{([a-z_]+)}", path)]
            if params:
                op["parameters"] = params
            if meta["body"] is not None and method in ("POST", "PUT", "PATCH"):
                op["requestBody"] = {"required": True, "content": {
                    "application/json": {"schema": inline_schema(meta["body"])}}}
            if meta["auth"]:
                op["security"] = [{"sessionCookie": [], "csrfHeader": []}]
            paths.setdefault(path, {})[method.lower()] = op
    return {
        "openapi": "3.1.0",
        "info": {"title": "Tandem API", "version": "1.0.0",
                 "description": "Tandem travel management API. Session cookie auth; state-changing requests "
                                "require the X-CSRF-Token header returned by /auth/me or /auth/login."},
        "components": {"securitySchemes": {
            "sessionCookie": {"type": "apiKey", "in": "cookie", "name": current_app.config["SESSION_COOKIE_NAME"]},
            "csrfHeader": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"}}},
        "paths": dict(sorted(paths.items())),
    }


@bp.get("/openapi.json")
def openapi():
    from flask import jsonify

    return jsonify(build_spec())

