"""Vercel serverless entry point: exposes the Flask WSGI app from backend/app.

Vercel rewrites /api/* here (see vercel.json). Static frontend files are served by Vercel directly.
Background jobs run inline (JOB_RUNNER defaults to inline when VERCEL is set) and periodic checks run
via Vercel Cron calling /api/v1/internal/cron.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import create_app  # noqa: E402

app = create_app()
