"""批次端点落库：创建时写入发酵止/烘烤止，之后各读取面只认库里的两列。"""

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.api.router import _all_occupancies
from app.database import Base, get_db
from app.main import app
from app.models.models import Batch
from app.services.migrate import migrate_batch_ends
from app.services.seed import seed_if_empty


@pytest.fixture()
def env(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/bakeoven.db", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    migrate_batch_ends(engine)
    with TestingSession() as db:
        seed_if_empty(db)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield SimpleNamespace(client=TestClient(app), session=TestingSession)
    app.dependency_overrides.clear()


def _gantt_by_code(client):
    out = {}
    for blk in client.get("/api/gantt").json():
        out.setdefault(blk["code"], {})[blk["phase"]] = blk
    return out


def test_seed_batches_stored_ends_match_recipe(env):
    # 库里的两列与按产品时长现算一致
    with env.session() as db:
        rows = {b.code: b for b in db.scalars(select(Batch)).all()}
    # 乡村欧包 9:00 起，发酵 40 → 9:40，烘烤 35 → 10:15
    assert (rows["BO-0900"].start_min, rows["BO-0900"].ferment_end_min, rows["BO-0900"].bake_end_min) == (540, 580, 615)
    # 黄油可颂 10:30 起，发酵 25 → 10:55，烘烤 20 → 11:15
    assert (rows["BO-1030"].start_min, rows["BO-1030"].ferment_end_min, rows["BO-1030"].bake_end_min) == (630, 655, 675)
    # 布朗尼发酵 0：发酵止 = 开工，烘烤止 = 开工 + 30
    assert (rows["BO-1000"].start_min, rows["BO-1000"].ferment_end_min, rows["BO-1000"].bake_end_min) == (600, 600, 630)

    # 读接口：端点一致，不一致标记为否
    api_rows = {b["code"]: b for b in env.client.get("/api/batches").json()}
    assert (api_rows["BO-0900"]["ferment_end"], api_rows["BO-0900"]["bake_end"]) == (580, 615)
    assert (api_rows["BO-1030"]["ferment_end"], api_rows["BO-1030"]["bake_end"]) == (655, 675)
    assert (api_rows["BO-1000"]["ferment_end"], api_rows["BO-1000"]["bake_end"]) == (600, 630)
    assert all(not b["ends_mismatch"] for b in api_rows.values())

    # 甘特仍是原来的色块
    gantt = _gantt_by_code(env.client)
    assert (gantt["BO-0900"]["ferment"]["start_min"], gantt["BO-0900"]["ferment"]["end_min"]) == (540, 580)
    assert (gantt["BO-0900"]["bake"]["start_min"], gantt["BO-0900"]["bake"]["end_min"]) == (580, 615)
    assert (gantt["BO-1030"]["ferment"]["start_min"], gantt["BO-1030"]["ferment"]["end_min"]) == (630, 655)
    assert (gantt["BO-1030"]["bake"]["start_min"], gantt["BO-1030"]["bake"]["end_min"]) == (655, 675)
    assert (gantt["BO-1000"]["ferment"]["start_min"], gantt["BO-1000"]["ferment"]["end_min"]) == (600, 600)
    assert (gantt["BO-1000"]["bake"]["start_min"], gantt["BO-1000"]["bake"]["end_min"]) == (600, 630)
    assert all(not blk["ends_mismatch"] for blk in env.client.get("/api/gantt").json())


def test_migration_backfills_old_schema(tmp_path):
    # 旧库：batches 表没有两个端点列，迁移后回填并与现算一致
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(80), ferment_min INTEGER, bake_min INTEGER)"))
        conn.execute(text("CREATE TABLE batches (id INTEGER PRIMARY KEY, product_id INTEGER, oven_id INTEGER, code VARCHAR(40), start_min INTEGER, status VARCHAR(20), created_at DATETIME)"))
        conn.execute(text("INSERT INTO products VALUES (1, '乡村欧包', 40, 35)"))
        conn.execute(text("INSERT INTO batches (id, product_id, oven_id, code, start_min, status, created_at) VALUES (1, 1, 1, 'BO-0900', 540, 'scheduled', '2026-01-01 00:00:00')"))
    migrate_batch_ends(engine)
    OldSession = sessionmaker(bind=engine)
    with OldSession() as db:
        b = db.get(Batch, 1)
        assert (b.ferment_end_min, b.bake_end_min) == (580, 615)


def test_create_writes_stored_ends(env):
    products = env.client.get("/api/products").json()
    brownie = next(p for p in products if p["name"] == "布朗尼")
    ovens = env.client.get("/api/ovens").json()
    oven_id = ovens[-1]["id"]  # 二层石板炉，无占用
    res = env.client.post("/api/batches", json={"product_id": brownie["id"], "oven_id": oven_id, "start_min": 720})
    assert res.status_code == 200
    body = res.json()
    assert (body["ferment_end"], body["bake_end"]) == (720, 750)
    assert body["ends_mismatch"] is False
    with env.session() as db:
        b = db.scalar(select(Batch).where(Batch.code == body["code"]))
        assert (b.ferment_end_min, b.bake_end_min) == (720, 750)


def test_shortened_bake_end_served_as_stored_and_flagged(env):
    batch_id = next(b["id"] for b in env.client.get("/api/batches").json() if b["code"] == "BO-0900")
    # 绕过创建接口，直接把 BO-0900 的烘烤止改短一分钟：615 → 614
    with env.session() as db:
        b = db.get(Batch, batch_id)
        b.bake_end_min -= 1
        db.commit()

    # 读接口停在改短后的止点，并标出端点与产品时长不一致
    api_rows = {b["code"]: b for b in env.client.get("/api/batches").json()}
    assert api_rows["BO-0900"]["bake_end"] == 614
    assert api_rows["BO-0900"]["ferment_end"] == 580
    assert api_rows["BO-0900"]["ends_mismatch"] is True
    assert api_rows["BO-1030"]["ends_mismatch"] is False
    assert api_rows["BO-1000"]["ends_mismatch"] is False

    # 甘特色块同样停在 614 并标出不一致
    gantt = _gantt_by_code(env.client)
    assert gantt["BO-0900"]["bake"]["end_min"] == 614
    assert gantt["BO-0900"]["bake"]["ends_mismatch"] is True
    assert gantt["BO-0900"]["ferment"]["end_min"] == 580

    # 冲突检测/可开工共用的占炉数据源也读库里的止点
    with env.session() as db:
        occs = _all_occupancies(db)
    bake = next(o for o in occs if o.batch_id == batch_id and o.phase == "bake")
    assert (bake.interval.start, bake.interval.end) == (580, 614)

    # 库里的值没有被悄悄改写
    with env.session() as db:
        b = db.get(Batch, batch_id)
        assert (b.ferment_end_min, b.bake_end_min) == (580, 614)
