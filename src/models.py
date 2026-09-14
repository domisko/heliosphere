"""Shared data contracts used across ingestion, analytics, storage, and API layers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RawWindRecord(BaseModel):
    """One minute of plasma data. NOAA's rtsw_wind_1m feed reports proton_*
    fields and carries redundant rows from multiple L1 spacecraft (ACE, IMAP,
    DSCOVR/SOLAR1) per minute; `active` marks the one NOAA currently trusts."""

    model_config = ConfigDict(populate_by_name=True)

    time_tag: datetime
    active: bool = True
    speed: float | None = Field(None, validation_alias="proton_speed", description="Solar wind bulk speed in km/s")
    density: float | None = Field(None, validation_alias="proton_density", description="Proton density in p/cm^3")
    temperature: float | None = Field(None, validation_alias="proton_temperature", description="Ion temperature in Kelvin")


class RawMagRecord(BaseModel):
    time_tag: datetime
    active: bool = True
    bx_gsm: float | None = Field(None, description="IMF Bx in GSM coordinates (nT)")
    by_gsm: float | None = Field(None, description="IMF By in GSM coordinates (nT)")
    bz_gsm: float | None = Field(None, description="IMF Bz in GSM coordinates (nT)")
    bt: float | None = Field(None, description="Total magnetic field strength (nT)")


class EnrichedTelemetry(BaseModel):
    timestamp: datetime
    speed: float
    density: float
    temperature: float
    bx: float
    by: float
    bz: float
    bt: float
    clock_angle: float
    coupling_index: float
    storm_tier: str
    bz_derivative_15m: float
