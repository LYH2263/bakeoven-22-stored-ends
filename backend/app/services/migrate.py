"""幂等迁移：batches 表补发酵止/烘烤止两列，并按当前产品时长回填旧行。"""

from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.models import Batch, Product
from app.services.oven_engine import RecipeDurations, recipe_ends


def ensure_batch_end_columns(engine: Engine) -> None:
    """旧库缺列时补列（新库由 create_all 直接带出两列，此处跳过）。"""
    insp = inspect(engine)
    if "batches" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("batches")}
    with engine.begin() as conn:
        if "ferment_end_min" not in cols:
            conn.execute(text("ALTER TABLE batches ADD COLUMN ferment_end_min INTEGER"))
        if "bake_end_min" not in cols:
            conn.execute(text("ALTER TABLE batches ADD COLUMN bake_end_min INTEGER"))


def backfill_batch_ends(db: Session) -> None:
    """把仍为空的两列按当前产品时长回填；已有值的行一律不动。"""
    rows = db.scalars(
        select(Batch).where(Batch.ferment_end_min.is_(None) | Batch.bake_end_min.is_(None))
    ).all()
    for b in rows:
        p = db.get(Product, b.product_id)
        if not p:
            continue
        b.ferment_end_min, b.bake_end_min = recipe_ends(
            b.start_min, RecipeDurations(p.ferment_min, p.bake_min)
        )
    if rows:
        db.commit()
