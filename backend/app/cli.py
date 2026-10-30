"""Flask CLI commands: worker, jobs, demo seeding, provider health checks."""
from __future__ import annotations

import json

import click
from flask import Flask


def register_cli(app: Flask) -> None:
    @app.cli.command("worker")
    @click.option("--once", is_flag=True, help="Process at most one job and exit")
    def worker(once: bool):
        """Run the background job worker (PostgreSQL-backed queue)."""
        from app.tasks.queue import worker_loop

        worker_loop(app, once=once)

    @app.cli.command("run-jobs")
    def run_jobs():
        """Process all due jobs once, then exit."""
        from app.tasks.queue import run_pending

        click.echo(f"processed {run_pending()} job(s)")

    @app.cli.command("periodic")
    def periodic():
        """Run periodic checks once (upcoming events, deadlines, Gmail sync scheduling, demo cleanup)."""
        from app.tasks.periodic import run_periodic

        run_periodic()
        click.echo("done")

    @app.cli.command("seed-demo")
    @click.option("--password", default=None, help="Password for demo@tandem.travel (default: env or generated)")
    def seed_demo(password: str | None):
        """Create or reset the shared demo account with the Rome trip."""
        from app.services.demo.seed import seed_demo_account

        user, generated = seed_demo_account(password)
        click.echo(f"Demo account ready: {user.email}")
        if generated:
            click.echo(f"Generated password (shown once): {generated}")

    @app.cli.command("check-providers")
    def check_providers():
        """Run live health checks against configured AI providers (makes small API calls)."""
        from app.extensions import db
        from app.models import ProviderStatus
        from app.services.ai.router import build_providers
        from app.utils.timeutil import utcnow

        for name, provider in build_providers(app.config).items():
            result = provider.health_check()
            click.echo(f"{name}: {json.dumps(result)}")
            if result.get("state") != "not_configured":
                row = db.session.get(ProviderStatus, f"ai:{name}") or ProviderStatus(provider=f"ai:{name}", kind="ai")
                row.state = result.get("state", "unknown")
                row.detail = result
                row.cooldown_until = None if row.state == "ok" else row.cooldown_until
                row.checked_at = utcnow()
                db.session.add(row)
        db.session.commit()

    @app.cli.command("smoke-ai")
    def smoke_ai():
        """Live end-to-end check of configured AI providers using fictional demo documents (real API calls)."""
        from app.extensions import db
        from app.models import DemoTenant, Trip, User
        from app.services.agent.orchestrator import respond
        from app.services.ai.base import (
            TASK_DOCUMENT_EXTRACTION, TASK_SUMMARY, TASK_TEXT_EXTRACTION, AIRequest, ChatMessage, FilePart, ImagePart,
            TextPart,
        )
        from app.services.ai.router import build_providers
        from app.services.ai.schema_utils import parse_json_text, validate_against
        from app.services.demo import documents as demo_docs
        from app.services.demo.seed import create_demo_workspace, demo_start_date
        from app.services.ingestion.extractors import extract
        from app.services.ingestion.schema import EXTRACTION_SYSTEM_PROMPT, ExtractionResult

        providers = build_providers(app.config)
        start = demo_start_date()
        results: list[tuple[str, str, str]] = []

        def check(name: str, needs: str, fn) -> None:
            if not providers[needs].configured():
                results.append((name, "SKIP", f"{needs} not configured"))
                return
            try:
                results.append((name, "OK", fn()))
            except Exception as exc:  # noqa: BLE001 - report every failure
                results.append((name, "FAIL", f"{type(exc).__name__}: {str(exc)[:240]}"))

        def extraction(provider, part, role):
            req = AIRequest(task=TASK_DOCUMENT_EXTRACTION, system=EXTRACTION_SYSTEM_PROMPT, schema=ExtractionResult,
                            messages=[ChatMessage(role="user", parts=[part, TextPart("Extract the travel records.")])],
                            role=role, max_output_tokens=8192)
            resp = provider.generate(req, provider.model_for(role))
            data = validate_against(ExtractionResult, parse_json_text(resp.text))
            refs = sorted({r.get("booking_reference") or "?" for r in data["records"]})
            return f"{resp.model}: {len(data['records'])} record(s), refs {refs}, {resp.input_tokens}+{resp.output_tokens} tokens"

        pdf = FilePart(demo_docs.flight_confirmation(start), "application/pdf", "flight.pdf")
        png_bytes, png_mime = extract(demo_docs.walking_tour_screenshot(start), "image/png").images[0]
        png = ImagePart(png_bytes, png_mime)
        check("Gemini · PDF → structured extraction", "gemini", lambda: extraction(providers["gemini"], pdf, "document"))
        check("Gemini · screenshot → structured extraction", "gemini", lambda: extraction(providers["gemini"], png, "vision"))
        check("Z.ai · screenshot (free vision model)", "zai", lambda: extraction(providers["zai"], png, "vision"))

        def text_task(name, task):
            p = providers[name]
            req = AIRequest(task=task, system=EXTRACTION_SYSTEM_PROMPT, schema=ExtractionResult, role="extraction",
                            messages=[ChatMessage.user("Booking reference: AB12CD. Train 9512 Paris Gare de Lyon to "
                                                       "Milano Centrale, 12 December 2026 06:24 to 13:30. Booking confirmed.")])
            resp = p.generate(req, p.model_for("extraction"))
            data = validate_against(ExtractionResult, parse_json_text(resp.text))
            return f"{resp.model}: {len(data['records'])} record(s)"

        check("Z.ai · text → structured extraction", "zai", lambda: text_task("zai", TASK_TEXT_EXTRACTION))
        check("Groq · text-only structured task", "groq", lambda: text_task("groq", TASK_SUMMARY))

        def agent_turn():
            app.config["DEMO_ALLOW_EXTERNAL_AI"] = True
            user = create_demo_workspace()
            db.session.commit()
            try:
                from app.models import Conversation

                trip = db.session.execute(db.select(Trip).where(Trip.user_id == user.id)).scalar_one()
                conv = Conversation(user_id=user.id, trip_id=trip.id)
                db.session.add(conv)
                db.session.commit()
                msg = respond(user, conv, "What do I have on Saturday, and are there any conflicts I should fix?")
                tools = [t["name"] for t in msg.tool_calls]
                if msg.provider == "local":
                    raise RuntimeError(f"fell back to offline assistant (tools {tools})")
                return f"{msg.provider}/{msg.model}: tools {tools}; reply: {msg.content[:120]!r}"
            finally:
                tenant = db.session.get(DemoTenant, user.demo_tenant_id)
                db.session.delete(db.session.get(User, user.id))
                db.session.delete(tenant)
                db.session.commit()

        check("Agent · multi-tool turn on demo trip", "gemini" if providers["gemini"].configured() else "zai", agent_turn)
        for name, status, detail in results:
            click.echo(f"[{status:4}] {name}\n        {detail}")
        if any(s == "FAIL" for _, s, _ in results):
            raise SystemExit(1)

    @app.cli.command("openapi")
    @click.argument("path", default="-")
    def openapi(path: str):
        """Write the OpenAPI document to PATH (or stdout)."""
        from app.api.openapi import build_spec

        text = json.dumps(build_spec(), indent=2)
        if path == "-":
            click.echo(text)
        else:
            with open(path, "w") as fh:
                fh.write(text)
            click.echo(f"wrote {path}")
