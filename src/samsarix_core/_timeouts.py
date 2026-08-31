# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Private numeric validation shared by execution and retention deadlines."""

from __future__ import annotations

from math import isfinite


def normalize_timeout(value: object, *, allow_zero: bool = False) -> float | None:
    """Return a finite duration, or None when it cannot be represented safely."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        duration = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    if not isfinite(duration) or duration < 0 or (duration == 0 and not allow_zero):
        return None
    return duration
