import uuid

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MenuExtractionUsage(Base):
    """One row per calendar month, tracking total AI menu-photo-extraction calls across every
    restaurant. Enforces settings.menu_extraction_monthly_call_cap as a real spend backstop
    (see config.py) — a company-wide budget cap, not a per-restaurant allowance."""

    __tablename__ = "menu_extraction_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    year_month: Mapped[str] = mapped_column(String(7), unique=True, index=True)  # "2026-09"
    call_count: Mapped[int] = mapped_column(Integer, default=0)
