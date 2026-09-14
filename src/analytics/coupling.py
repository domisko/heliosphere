"""IMF clock angle and Newell geomagnetic coupling function."""

import math


def calculate_clock_angle(by: float, bz: float) -> float:
    """IMF clock angle in the Y-Z GSM plane, in degrees on [0, 360).

    0 deg = purely northward Bz (closed magnetosphere), 180 deg = purely
    southward Bz (dayside reconnection favorable).
    """
    theta = math.atan2(by, bz)
    if theta < 0:
        theta += 2 * math.pi
    return math.degrees(theta)


def calculate_coupling(v: float, by: float, bz: float) -> float:
    """Newell geomagnetic coupling function dPhi_MP/dt (empirical units)."""
    bt = math.sqrt(by**2 + bz**2)
    theta = math.atan2(by, bz)
    if theta < 0:
        theta += 2 * math.pi
    return (v ** (4 / 3)) * (bt ** (2 / 3)) * (math.sin(theta / 2) ** (8 / 3))
