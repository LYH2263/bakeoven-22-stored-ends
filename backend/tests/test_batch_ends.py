"""批次发酵止/烘烤止落库后的读取行为：种子一致、改库以库为准并标记、迁移回填。"""

import os
import tempfile

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import Batch  # noqa: E402
from app.services.migrate import backfill_batch_ends, ensure_batch_end_columns  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _seed_batches(client):
    return {b["code"]: b for b in client.get("/api/batches").json()}


def test_seed_batches_ends_match_recipe_and_unflagged():
    with TestClient(app) as client:
        batches = _seed_batches(client)
        # 乡村欧包 9:00 起，发酵 40 分、烘烤 35 分
        assert batches["BO-0900"]["start_min"] == 9 * 60
        assert batches["BO-0900"]["ferment_end"] == 9 * 60 + 40
        assert batches["BO-0900"]["bake_end"] == 9 * 60 + 40 + 35
        # 黄油可颂 10:30 起，发酵 25 分、烘烤 20 分
        assert batches["BO-1030"]["start_min"] == 10 * 60 + 30
        assert batches["BO-1030"]["ferment_end"] == 10 * 60 + 55
        assert batches["BO-1030"]["bake_end"] == 11 * 60 + 15
        # 布朗尼 10:00 起，发酵 0 分（发酵止=开工）、烘烤 30 分
        assert batches["BO-1000"]["start_min"] == 10 * 60
        assert batches["BO-1000"]["ferment_end"] == 10 * 60
        assert batches["BO-1000"]["bake_end"] == 10 * 60 + 30
        assert all(not b["ends_mismatch"] for b in batches.values())

        blocks = client.get("/api/gantt").json()
        spans = {(g["code"], g["phase"]): (g["start_min"], g["end_min"]) for g in blocks}
        assert spans[("BO-0900", "ferment")] == (9 * 60, 9 * 60 + 40)
        assert spans[("BO-0900", "bake")] == (9 * 60 + 40, 9 * 60 + 75)
        assert spans[("BO-1030", "ferment")] == (10 * 60 + 30, 10 * 60 + 55)
        assert spans[("BO-1030", "bake")] == (10 * 60 + 55, 11 * 60 + 15)
        assert spans[("BO-1000", "ferment")] == (10 * 60, 10 * 60)
        assert spans[("BO-1000", "bake")] == (10 * 60, 10 * 60 + 30)
        assert all(not g["ends_mismatch"] for g in blocks)


def test_shortened_bake_end_served_from_db_and_flagged():
    with TestClient(app) as client:
        # 绕过创建接口，直接改库：BO-0900 烘烤止改短一分钟
        db = SessionLocal()
        try:
            batch = db.scalar(select(Batch).where(Batch.code == "BO-0900"))
            batch.bake_end_min -= 1
            db.commit()
            shortened = batch.bake_end_min
        finally:
            db.close()
        assert shortened == 9 * 60 + 75 - 1

        batches = _seed_batches(client)
        assert batches["BO-0900"]["bake_end"] == shortened
        assert batches["BO-0900"]["ferment_end"] == 9 * 60 + 40
        assert batches["BO-0900"]["ends_mismatch"] is True
        assert batches["BO-1030"]["ends_mismatch"] is False
        assert batches["BO-1000"]["ends_mismatch"] is False

        blocks = client.get("/api/gantt").json()
        bake = next(g for g in blocks if g["code"] == "BO-0900" and g["phase"] == "bake")
        assert bake["end_min"] == shortened
        assert bake["ends_mismatch"] is True
        ferment = next(g for g in blocks if g["code"] == "BO-0900" and g["phase"] == "ferment")
        assert ferment["end_min"] == 9 * 60 + 40

        # 读取不得悄悄改写库里的值
        db = SessionLocal()
        try:
            assert db.scalar(select(Batch).where(Batch.code == "BO-0900")).bake_end_min == shortened
        finally:
            db.close()


def test_migration_backfills_ends_consistent_with_recipe():
    # 模拟迁移前的旧表：batches 没有两列
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(80), ferment_min INTEGER, bake_min INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE ovens (id INTEGER PRIMARY KEY, label VARCHAR(40), capacity_note VARCHAR(80))"
        ))
        conn.execute(text(
            "CREATE TABLE batches (id INTEGER PRIMARY KEY, product_id INTEGER, oven_id INTEGER,"
            " code VARCHAR(40), start_min INTEGER, status VARCHAR(20), created_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO products VALUES (1, '乡村欧包', 40, 35)"))
        conn.execute(text("INSERT INTO ovens VALUES (1, '一层 1 号炉', '盘炉')"))
        conn.execute(text(
            "INSERT INTO batches (id, product_id, oven_id, code, start_min, status)"
            " VALUES (1, 1, 1, 'BO-0900', 540, 'scheduled')"
        ))

    ensure_batch_end_columns(engine)
    db = SessionLocal()
    try:
        backfill_batch_ends(db)
        row = db.scalar(select(Batch).where(Batch.code == "BO-0900"))
        assert row.ferment_end_min == 9 * 60 + 40
        assert row.bake_end_min == 9 * 60 + 75
    finally:
        db.close()

    # 迁移后读出来与现算一致，不标不一致
    with TestClient(app) as client:
        batches = _seed_batches(client)
        assert batches["BO-0900"]["ferment_end"] == 9 * 60 + 40
        assert batches["BO-0900"]["bake_end"] == 9 * 60 + 75
        assert batches["BO-0900"]["ends_mismatch"] is False
