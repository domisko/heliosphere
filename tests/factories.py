"""Shared test data builders."""

from datetime import datetime

from src.models import EnrichedTelemetry


def make_record(**overrides) -> EnrichedTelemetry:
    base = dict(
        timestamp=datetime(2026, 1, 1, 0, 0),
        speed=400.0,
        density=5.0,
        temperature=1e5,
        bx=1.0,
        by=2.0,
        bz=-3.0,
        bt=3.5,
        clock_angle=120.0,
        coupling_index=1000.0,
        storm_tier="G0 (Nominal)",
        bz_derivative_15m=0.0,
    )
    base.update(overrides)
    return EnrichedTelemetry(**base)
