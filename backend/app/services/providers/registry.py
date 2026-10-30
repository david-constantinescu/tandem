"""Provider registry with demo isolation.

Demo workspaces can only reach the simulator. Real accounts can never reach the simulator. This is
enforced here, the single place adapters are created for a user.
"""
from __future__ import annotations

from flask import current_app

from app.models import User
from app.services.providers.base import TravelProviderAdapter
from app.services.providers.osm import OSMPlacesAdapter
from app.services.providers.partners import BookingComAdapter, ExpediaAdapter, GetYourGuideAdapter, ViatorAdapter
from app.services.providers.simulator import SimulatorAdapter
from app.utils.errors import NotFound

REAL_ADAPTERS = (OSMPlacesAdapter, BookingComAdapter, ExpediaAdapter, ViatorAdapter, GetYourGuideAdapter)


def adapters_for(user: User) -> list[TravelProviderAdapter]:
    cfg = current_app.config
    if user.is_demo:
        return [SimulatorAdapter(cfg)]
    return [cls(cfg) for cls in REAL_ADAPTERS]


def get_adapter(user: User, key: str) -> TravelProviderAdapter:
    for adapter in adapters_for(user):
        if adapter.key == key:
            return adapter
    raise NotFound("Provider not available for this account", code="provider_not_available")
