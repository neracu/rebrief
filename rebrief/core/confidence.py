from __future__ import annotations

from enum import Enum


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


_CONFIDENCE_ORDER: dict[Confidence, int] = {
    Confidence.HIGH: 3,
    Confidence.MEDIUM: 2,
    Confidence.LOW: 1,
}


def parse_confidence(value: str) -> Confidence:
    normalized = value.strip().upper()
    try:
        return Confidence(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid confidence level: {value!r}") from exc


def parse_min_confidence(value: str) -> Confidence:
    mapping = {
        "high": Confidence.HIGH,
        "medium": Confidence.MEDIUM,
        "low": Confidence.LOW,
    }
    normalized = value.strip().lower()
    if normalized not in mapping:
        raise ValueError(f"Invalid min-confidence level: {value!r}")
    return mapping[normalized]


def meets_threshold(item: Confidence, minimum: Confidence) -> bool:
    return _CONFIDENCE_ORDER[item] >= _CONFIDENCE_ORDER[minimum]
