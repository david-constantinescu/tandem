"""Provider registry with demo isolation.

Demo workspaces get real, read-only places from OpenStreetMap plus the simulator (the only provider they can
"book" with, and nothing real is charged). Real accounts can never reach the simulator. This is enforced here,
the single place adapters are created for a user.
"""
from __future__ import annotations

from flask import current_app

from app.models import User
from app.services.providers.base import TravelProviderAdapter
from app.services.providers.osm import OSMPlacesAdapter
from app.services.providers.partners import (
    BookingComAdapter,
    ExpediaAdapter,
    GetYourGuideAdapter,
    HeadoutAdapter,
    KlookAdapter,
    TiqetsAdapter,
    ViatorAdapter,
)
from app.services.providers.simulator import SimulatorAdapter
from app.utils.errors import NotFound

REAL_ADAPTERS = (OSMPlacesAdapter, BookingComAdapter, ExpediaAdapter, ViatorAdapter, GetYourGuideAdapter, TiqetsAdapter,
                 KlookAdapter, HeadoutAdapter)


def adapters_for(user: User) -> list[TravelProviderAdapter]:
    cfg = current_app.config
    if user.is_demo:
        return [OSMPlacesAdapter(cfg), SimulatorAdapter(cfg)]
    return [cls(cfg) for cls in REAL_ADAPTERS]


def get_adapter(user: User, key: str) -> TravelProviderAdapter:
    for adapter in adapters_for(user):
        if adapter.key == key:
            return adapter
    raise NotFound("Provider not available for this account", code="provider_not_available")
