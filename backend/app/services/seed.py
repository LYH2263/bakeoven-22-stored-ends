from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Batch, ConflictLog, Oven, Product


def _batch(product: Product, oven: Oven, code: str, start_min: int) -> Batch:
    # 与创建接口同一口径：按创建时的产品时长写入发酵止/烘烤止
    ferment_end = start_min + product.ferment_min
    return Batch(
        product_id=product.id,
        oven_id=oven.id,
        code=code,
        start_min=start_min,
        ferment_end_min=ferment_end,
        bake_end_min=ferment_end + product.bake_min,
        status="scheduled",
    )


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Product.id).limit(1)):
        return
    products = [
        Product(name="乡村欧包", ferment_min=40, bake_min=35),
        Product(name="黄油可颂", ferment_min=25, bake_min=20),
        Product(name="布朗尼", ferment_min=0, bake_min=30),
    ]
    ovens = [
        Oven(label="一层 1 号炉", capacity_note="盘炉"),
        Oven(label="一层 2 号炉", capacity_note="盘炉"),
        Oven(label="二层石板炉", capacity_note="石板"),
    ]
    db.add_all(products + ovens)
    db.flush()
    db.add_all(
        [
            _batch(products[0], ovens[0], "BO-0900", 9 * 60),
            _batch(products[1], ovens[0], "BO-1030", 10 * 60 + 30),
            _batch(products[2], ovens[1], "BO-1000", 10 * 60),
        ]
    )
    db.add(
        ConflictLog(
            batch_code="BO-试排",
            oven_id=ovens[0].id,
            detail="试算与 BO-0900 烘烤段重叠（半开区间检测）",
        )
    )
    db.commit()
