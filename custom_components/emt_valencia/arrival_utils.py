"""Small, dependency-free helpers for normalising EMT arrival rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def arrival_sort_key(item: Mapping[str, Any]) -> tuple[int, int, str]:
    """Order estimates, scheduled arrivals, then malformed/error rows safely."""
    if isinstance(item.get("minutes"), int):
        return (0, item["minutes"], "")
    if scheduled := item.get("scheduled_arrival"):
        return (1, 0, str(scheduled))
    return (2, 0, "")
