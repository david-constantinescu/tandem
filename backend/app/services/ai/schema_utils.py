"""JSON-schema helpers for provider structured-output modes and robust JSON parsing."""
from __future__ import annotations

import copy
import json
import re

from pydantic import BaseModel, ValidationError

from app.services.ai.base import InvalidOutput

_DROP_KEYS = {"title", "default", "examples"}


def inline_schema(model: type[BaseModel] | dict) -> dict:
    """Return a JSON schema with $refs inlined and cosmetic keys removed."""
    schema = model.model_json_schema() if not isinstance(model, dict) else copy.deepcopy(model)
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                merged = {**resolve(copy.deepcopy(defs[name])), **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            return {k: resolve(v) for k, v in node.items() if k not in _DROP_KEYS}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def strict_schema(model: type[BaseModel] | dict) -> dict:
    """Schema for strict json_schema modes: every property required, no additional properties."""
    schema = inline_schema(model)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                node["required"] = list(props.keys())
                node["additionalProperties"] = False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_text(text: str) -> dict:
    """Parse a JSON object from model text, tolerating code fences and leading prose."""
    if not text or not text.strip():
        raise InvalidOutput("Model returned an empty response")
    cleaned = _FENCE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise InvalidOutput("Model response did not contain a JSON object") from None
        try:
            value = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise InvalidOutput(f"Model returned malformed JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise InvalidOutput("Model response JSON was not an object")
    return value


def validate_against(schema: type[BaseModel], data: dict) -> dict:
    try:
        return schema.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors(include_url=False)[:8]
        )
        raise InvalidOutput(f"Model output failed schema validation: {problems}") from exc


def schema_prompt(schema: type[BaseModel]) -> str:
    return (
        "Respond with a single JSON object only (no prose, no code fences) that conforms to this JSON schema:\n"
        + json.dumps(inline_schema(schema), separators=(",", ":"))
    )
