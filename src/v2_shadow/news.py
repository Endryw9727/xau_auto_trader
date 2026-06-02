"""V2-inspired news warning shadow layer.

No calendar API or scraper is called. Warnings are informational only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShadowNewsWarning:
    """Read-only news warning summary."""

    risk_level: str
    warning: str
    events: tuple[dict[str, object], ...] = ()
    advisory_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "risk_level": self.risk_level,
            "warning": self.warning,
            "events": list(self.events),
            "advisory_only": self.advisory_only,
        }


def build_shadow_news_warning(events: list[dict[str, object]] | None = None) -> ShadowNewsWarning:
    """Build a warning-only news shadow report from optional pre-supplied events."""
    supplied = tuple(events or ())
    high_impact = [event for event in supplied if str(event.get("impact", "")).upper() == "HIGH"]
    if high_impact:
        return ShadowNewsWarning(
            "HIGH",
            "High-impact events supplied to shadow report; warning only, not a live blocker.",
            supplied,
        )
    if supplied:
        return ShadowNewsWarning("MEDIUM", "Events supplied to shadow report; warning only.", supplied)
    return ShadowNewsWarning("UNKNOWN", "No news calendar is fetched in V2 shadow mode; warning layer is inactive.")
