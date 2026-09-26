from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    ferment_min: Mapped[int] = mapped_column(Integer)
    bake_min: Mapped[int] = mapped_column(Integer)


class Oven(Base):
    __tablename__ = "ovens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(40), unique=True)
    capacity_note: Mapped[str] = mapped_column(String(80), default="")


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    oven_id: Mapped[int] = mapped_column(ForeignKey("ovens.id"))
    code: Mapped[str] = mapped_column(String(40), unique=True)
    start_min: Mapped[int] = mapped_column(Integer)  # minutes from 00:00
    # 创建时按当时产品时长写入，之后所有读路径只读这两列，不再现算
    ferment_end_min: Mapped[int] = mapped_column(Integer)
    bake_end_min: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConflictLog(Base):
    __tablename__ = "conflict_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_code: Mapped[str] = mapped_column(String(40))
    oven_id: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
