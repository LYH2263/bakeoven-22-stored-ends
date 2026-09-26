"""老库迁移：为 batches 表补发酵止/烘烤止两列，并按产品时长回填存量行。

新库由 create_all 直接建出两列、种子在创建时写入，此迁移是空操作。
回填只写 NULL 行，已有值一律不动。
"""

from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.models import Batch, Product


def migrate_batch_ends(engine: Engine) -> None:
    insp = inspect(engine)
    if "batches" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("batches")}
    with engine.begin() as conn:
        if "ferment_end_min" not in cols:
            conn.execute(text("ALTER TABLE batches ADD COLUMN ferment_end_min INTEGER"))
        if "bake_end_min" not in cols:
            conn.execute(text("ALTER TABLE batches ADD COLUMN bake_end_min INTEGER"))
    with Session(engine) as db:
        dirty = False
        for b in db.scalars(select(Batch)).all():
            if b.ferment_end_min is not None and b.bake_end_min is not None:
                continue
            p = db.get(Product, b.product_id)
            if not p:
                continue
            b.ferment_end_min = b.start_min + p.ferment_min
            b.bake_end_min = b.ferment_end_min + p.bake_min
            dirty = True
        if dirty:
            db.commit()
