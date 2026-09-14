import math

import pytest

from src.analytics.classifier import classify_g_scale_from_kp, classify_storm_level
from src.analytics.coupling import calculate_clock_angle, calculate_coupling


def test_clock_angle_purely_southward_is_180():
    assert calculate_clock_angle(by=0.0, bz=-10.0) == pytest.approx(180.0)


def test_clock_angle_purely_northward_is_0():
    assert calculate_clock_angle(by=0.0, bz=10.0) == pytest.approx(0.0)


def test_clock_angle_purely_dawnward_is_90():
    assert calculate_clock_angle(by=10.0, bz=0.0) == pytest.approx(90.0)


def test_clock_angle_purely_duskward_wraps_into_positive_range():
    # atan2(-10, 0) is negative internally; the wrap-around must still land at 270 deg.
    assert calculate_clock_angle(by=-10.0, bz=0.0) == pytest.approx(270.0)


def test_coupling_is_maximal_for_purely_southward_field():
    v, bz = 500.0, -10.0
    coupling = calculate_coupling(v, by=0.0, bz=bz)
    expected = v ** (4 / 3) * abs(bz) ** (2 / 3)  # sin(theta/2) = sin(90deg) = 1
    assert coupling == pytest.approx(expected)


def test_coupling_is_near_zero_for_purely_northward_field():
    coupling = calculate_coupling(500.0, by=0.0, bz=10.0)
    assert coupling == pytest.approx(0.0, abs=1e-9)


def test_coupling_matches_hand_derivation_for_duskward_field():
    # Exercises the theta-wrap branch: atan2(-8, 0) is negative before wrapping.
    v, by, bz = 400.0, -8.0, 0.0
    bt = math.sqrt(by**2 + bz**2)
    theta = 3 * math.pi / 2  # atan2(-8, 0) wrapped into [0, 2pi)
    expected = v ** (4 / 3) * bt ** (2 / 3) * math.sin(theta / 2) ** (8 / 3)
    assert calculate_coupling(v, by, bz) == pytest.approx(expected)


def test_coupling_matches_hand_derivation_for_dawnward_field():
    v, by, bz = 400.0, 8.0, 0.0
    bt = math.sqrt(by**2 + bz**2)
    theta = math.pi / 2  # atan2(8, 0)
    expected = v ** (4 / 3) * bt ** (2 / 3) * math.sin(theta / 2) ** (8 / 3)
    assert calculate_coupling(v, by, bz) == pytest.approx(expected)


@pytest.mark.parametrize(
    "bz,speed,coupling,expected",
    [
        (-25.0, 750.0, 100.0, "G4-G5 (Extreme)"),
        (-20.0, 700.0, 100.0, "G4-G5 (Extreme)"),  # inclusive boundary
        (-19.9, 700.0, 100.0, "G3 (Strong)"),  # just misses the extreme threshold
        (-16.0, 650.0, 100.0, "G3 (Strong)"),
        (-12.0, 550.0, 100.0, "G2 (Moderate)"),
        (-6.0, 300.0, 100.0, "G1 (Minor)"),
        (-2.0, 300.0, 6000.0, "G1 (Minor)"),  # coupling-driven override
        (2.0, 300.0, 100.0, "G0 (Nominal)"),
    ],
)
def test_classify_storm_level_tiers(bz, speed, coupling, expected):
    assert classify_storm_level(bz, speed, coupling) == expected


@pytest.mark.parametrize(
    "kp,expected",
    [
        (9.0, "G5 (Extreme)"),
        (8.0, "G4 (Severe)"),
        (8.67, "G4 (Severe)"),  # NOAA groups 9- into G4 too
        (7.0, "G3 (Strong)"),
        (6.0, "G2 (Moderate)"),
        (5.0, "G1 (Minor)"),
        (4.99, "G0 (Nominal)"),
        (1.33, "G0 (Nominal)"),
    ],
)
def test_classify_g_scale_from_kp_matches_noaas_official_thresholds(kp, expected):
    assert classify_g_scale_from_kp(kp) == expected
