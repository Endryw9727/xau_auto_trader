"""Telegram-friendly report model for future notification output."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


ReportSeverity = Literal["INFO", "WARNING", "STOP", "ERROR"]


@dataclass(frozen=True)
class TelegramReport:
    """Notification payload model. It is reporting-only."""

    title: str
    status: str
    message: str
    severity: ReportSeverity = "INFO"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
