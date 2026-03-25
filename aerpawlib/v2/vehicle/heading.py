"""Heading angle helpers for v2 Drone."""


def _normalize_heading(h: float) -> float:
    """Normalize a heading angle to the range [0, 360)."""
    return h % 360


def _heading_diff(a: float, b: float) -> float:
    """Return the shortest absolute angular distance between headings."""
    d = abs((a % 360) - (b % 360))
    return min(d, 360 - d)
