from sqlalchemy import ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RelationshipState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "relationship_states"
    __table_args__ = (
        UniqueConstraint("simulation_run_id", "protagonist_guest_id", "target_guest_id"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    simulation_run_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE")
    )
    protagonist_guest_id: Mapped[str] = mapped_column(
        ForeignKey("guest_profiles.id", ondelete="CASCADE")
    )
    target_guest_id: Mapped[str] = mapped_column(ForeignKey("guest_profiles.id", ondelete="CASCADE"))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(default="observing", nullable=False)
    recent_trend: Mapped[str] = mapped_column(default="observing", nullable=False)
    notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    simulation = relationship("SimulationRun", back_populates="relationships")

