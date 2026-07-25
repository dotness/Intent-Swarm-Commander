"""Guardian Critic agent — safety verification for swarm commands.

Implements the initial minimal rule set from spec.md:
1. Altitude Limits: 10m ≤ altitude ≤ 400m
2. Geofencing: Target not in restricted airspace polygons
3. Mission Feasibility: Duration ≤ 30 minutes (1800s)
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Safety constraint constants ───────────────────────────────────────────

MIN_ALTITUDE_M = 10.0
MAX_ALTITUDE_M = 400.0
MAX_DURATION_S = 1800  # 30 minutes


@dataclass
class Violation:
    """A single constraint violation."""

    rule_id: str
    rule_description: str
    severity: str
    actual_value: str
    allowed_range: str
    remediation: str | None = None


def check_altitude(altitude_m: float | None) -> Violation | None:
    """Check altitude is within safe operational bounds."""
    if altitude_m is None:
        return None  # No altitude specified — acceptable for some missions

    if altitude_m < MIN_ALTITUDE_M:
        return Violation(
            rule_id="SAFETY-ALT-MIN",
            rule_description="Altitude must not be below minimum safe altitude",
            severity="critical",
            actual_value=f"{altitude_m}m",
            allowed_range=f">= {MIN_ALTITUDE_M}m",
            remediation=f"Increase altitude to at least {MIN_ALTITUDE_M}m",
        )

    if altitude_m > MAX_ALTITUDE_M:
        return Violation(
            rule_id="SAFETY-ALT-MAX",
            rule_description="Altitude must not exceed maximum allowed altitude",
            severity="critical",
            actual_value=f"{altitude_m}m",
            allowed_range=f"<= {MAX_ALTITUDE_M}m",
            remediation=f"Reduce altitude to at most {MAX_ALTITUDE_M}m",
        )

    return None


def check_duration(duration_s: int | None) -> Violation | None:
    """Check mission duration does not exceed battery limits."""
    if duration_s is None:
        return None

    if duration_s > MAX_DURATION_S:
        return Violation(
            rule_id="SAFETY-DUR-MAX",
            rule_description="Mission duration must not exceed standard battery limits",
            severity="high",
            actual_value=f"{duration_s}s ({duration_s / 60:.0f} min)",
            allowed_range=f"<= {MAX_DURATION_S}s ({MAX_DURATION_S / 60:.0f} min)",
            remediation="Reduce mission duration or plan refueling waypoints",
        )

    return None


def check_geofencing(target_area: dict | str) -> Violation | None:
    """Check target coordinates are not in restricted airspace.

    NOTE: For MVP, this performs a placeholder check. Full polygon
    intersection against restricted zones is a post-MVP enhancement.
    """
    # MVP: No restricted zones defined yet — always passes
    return None


def verify_command(
    altitude_m: float | None,
    duration_s: int | None,
    target_area: dict | str,
    drone_count: int | None = None,
) -> list[Violation]:
    """Run all safety constraint checks against a proposed command.

    Returns an empty list if all checks pass, otherwise returns the
    list of violations. The system MUST block commands with any violations.
    """
    violations: list[Violation] = []

    v = check_altitude(altitude_m)
    if v:
        violations.append(v)

    v = check_duration(duration_s)
    if v:
        violations.append(v)

    v = check_geofencing(target_area)
    if v:
        violations.append(v)

    if violations:
        logger.warning(
            "Guardian Critic found %d violation(s): %s",
            len(violations),
            [v.rule_id for v in violations],
        )
    else:
        logger.info("Guardian Critic: all safety checks passed")

    return violations
