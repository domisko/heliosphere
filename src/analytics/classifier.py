"""NOAA G-scale storm severity heuristic driven by southward Bz and speed,
plus the official Kp-index-based mapping NOAA actually uses."""


def classify_storm_level(bz: float, speed: float, coupling: float) -> str:
    # Sustained southward Bz is the primary driver of geomagnetic storms
    if bz <= -20 and speed >= 700:
        return "G4-G5 (Extreme)"
    if bz <= -15 and speed >= 600:
        return "G3 (Strong)"
    if bz <= -10 and speed >= 500:
        return "G2 (Moderate)"
    if bz <= -5 or coupling > 5000:
        return "G1 (Minor)"
    return "G0 (Nominal)"


def classify_g_scale_from_kp(kp: float) -> str:
    """NOAA's official G-scale: G1=Kp5 ... G5=Kp9. See
    https://www.swpc.noaa.gov/noaa-scales-explanation"""
    if kp >= 9:
        return "G5 (Extreme)"
    if kp >= 8:
        return "G4 (Severe)"
    if kp >= 7:
        return "G3 (Strong)"
    if kp >= 6:
        return "G2 (Moderate)"
    if kp >= 5:
        return "G1 (Minor)"
    return "G0 (Nominal)"
