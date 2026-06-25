from __future__ import annotations

from typing import Any


def evaluate_known_signal(profile: dict[str, Any], measurement: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic profile matching; frequency alone never suppresses an alert."""
    reasons: list[str] = []
    mismatches: list[str] = []
    center = int(measurement["center_frequency_hz"])
    expected = int(profile["center_frequency_hz"])
    tolerance = int(profile["frequency_tolerance_hz"])
    frequency_delta = abs(center - expected)
    (reasons if frequency_delta <= tolerance else mismatches).append("frequency")

    checks = (
        (
            "bandwidth_hz",
            "bandwidth",
            lambda value, target: abs(value - target) <= max(target * 0.25, tolerance),
        ),
        ("expected_power_min_dbm", "power_min", lambda value, target: value >= target),
        ("expected_power_max_dbm", "power_max", lambda value, target: value <= target),
        (
            "modulation",
            "modulation",
            lambda value, target: str(value).casefold() == str(target).casefold(),
        ),
        (
            "protocol",
            "protocol",
            lambda value, target: str(value).casefold() == str(target).casefold(),
        ),
        (
            "source_type",
            "source_type",
            lambda value, target: str(value).casefold() == str(target).casefold(),
        ),
        ("location_id", "location", lambda value, target: str(value) == str(target)),
    )
    measurement_keys = {
        "expected_power_min_dbm": "power_dbm",
        "expected_power_max_dbm": "power_dbm",
    }
    for profile_key, reason, compare in checks:
        target = profile.get(profile_key)
        if target is None:
            continue
        value = measurement.get(measurement_keys.get(profile_key, profile_key))
        if value is None:
            mismatches.append(f"{reason}_missing")
        elif compare(value, target):
            reasons.append(reason)
        else:
            mismatches.append(reason)

    matched = not mismatches
    suppress = (
        matched and bool(profile.get("suppress_alerts")) and profile.get("status") == "active"
    )
    return {
        "known_signal_id": str(profile.get("id")) if profile.get("id") else None,
        "matched": matched,
        "suppress_alert": suppress,
        "suppression_reason": "known_signal_profile_match" if suppress else None,
        "frequency_delta_hz": frequency_delta,
        "matched_attributes": reasons,
        "mismatches": mismatches,
    }
