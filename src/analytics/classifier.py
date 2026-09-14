"""NOAA G-scale storm severity heuristic driven by southward Bz and speed."""


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
