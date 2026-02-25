"""
Shared types for aerpawlib v2 safety module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GeofenceRegion:
    """Include or exclude geofence region."""

    points: List[dict]  # [{'lat': ..., 'lon': ...}, ...]
    include: bool  # True = allowed, False = no-go
