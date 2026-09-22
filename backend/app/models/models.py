from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeliveryRoute(Base):
    __tablename__ = "delivery_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    max_weight_kg: Mapped[float] = mapped_column(Float, default=8.0)
    max_volume_l: Mapped[float] = mapped_column(Float, default=20.0)
    stops: Mapped[list["SubscriberStop"]] = relationship(back_populates="route")


class SubscriberStop(Base):
    __tablename__ = "subscriber_stops"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("delivery_routes.id"))
    seq: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80))
    weight_kg: Mapped[float] = mapped_column(Float)
    volume_l: Mapped[float] = mapped_column(Float)
    route: Mapped[DeliveryRoute] = relationship(back_populates="stops")


class PackRun(Base):
    """一次带幂等令牌的装袋结果快照；同路线同令牌重放时直接复用。"""

    __tablename__ = "pack_runs"
    __table_args__ = (
        UniqueConstraint("route_id", "idempotency_key", name="uq_pack_run_route_key"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("delivery_routes.id"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    bags: Mapped[list["PackBag"]] = relationship(back_populates="run")
    rejects: Mapped[list["RejectRecord"]] = relationship(back_populates="run")


class PackBag(Base):
    __tablename__ = "pack_bags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("delivery_routes.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("pack_runs.id"), nullable=True)
    bag_index: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float)
    volume_l: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["BagItem"]] = relationship(back_populates="bag")
    run: Mapped[PackRun | None] = relationship(back_populates="bags")


class BagItem(Base):
    __tablename__ = "bag_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bag_id: Mapped[int] = mapped_column(ForeignKey("pack_bags.id"))
    stop_id: Mapped[int] = mapped_column(ForeignKey("subscriber_stops.id"))
    stop_name: Mapped[str] = mapped_column(String(80))
    weight_kg: Mapped[float] = mapped_column(Float)
    volume_l: Mapped[float] = mapped_column(Float)
    bag: Mapped[PackBag] = relationship(back_populates="items")


class RejectRecord(Base):
    __tablename__ = "reject_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("delivery_routes.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("pack_runs.id"), nullable=True)
    stop_id: Mapped[int] = mapped_column(Integer)
    stop_name: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    run: Mapped[PackRun | None] = relationship(back_populates="rejects")
