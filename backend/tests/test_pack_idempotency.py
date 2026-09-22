"""POST /api/pack 幂等令牌行为测试。

使用独立 SQLite 文件库，避免依赖 Postgres。
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="bagroute-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("SEED_ON_EMPTY", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.models import (
    BagItem,
    DeliveryRoute,
    PackBag,
    PackRun,
    RejectRecord,
    SubscriberStop,
)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def _make_route() -> int:
    db = SessionLocal()
    try:
        route = DeliveryRoute(name="测试线", max_weight_kg=8.0, max_volume_l=18.0)
        db.add(route)
        db.flush()
        db.add_all(
            [
                SubscriberStop(route_id=route.id, seq=1, name="一号点", weight_kg=2.0, volume_l=3.0),
                SubscriberStop(route_id=route.id, seq=2, name="二号点", weight_kg=3.0, volume_l=4.0),
                SubscriberStop(route_id=route.id, seq=3, name="超大件", weight_kg=99.0, volume_l=1.0),
                SubscriberStop(route_id=route.id, seq=4, name="三号点", weight_kg=1.0, volume_l=2.0),
            ]
        )
        db.commit()
        return route.id
    finally:
        db.close()


def _state(route_id: int):
    """返回 (袋 id 集合, 袋行数, 袋明细行数, 拒收行数)。"""
    db = SessionLocal()
    try:
        bags = db.scalars(select(PackBag).where(PackBag.route_id == route_id)).all()
        bag_ids = {b.id for b in bags}
        items = db.scalar(
            select(func.count(BagItem.id))
            .select_from(BagItem)
            .join(PackBag, BagItem.bag_id == PackBag.id)
            .where(PackBag.route_id == route_id)
        )
        rejects = db.scalar(
            select(func.count(RejectRecord.id)).where(RejectRecord.route_id == route_id)
        )
        return bag_ids, len(bags), items, rejects
    finally:
        db.close()


def _bump_stop(route_id: int, seq: int, weight_kg: float) -> None:
    """调整站点重量，使后续装袋结果内容发生变化。"""
    db = SessionLocal()
    try:
        stop = db.scalar(
            select(SubscriberStop).where(
                SubscriberStop.route_id == route_id, SubscriberStop.seq == seq
            )
        )
        stop.weight_kg = weight_kg
        db.commit()
    finally:
        db.close()


def test_same_token_replays_first_result(client):
    rid = _make_route()
    r1 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "t-1"})
    assert r1.status_code == 200
    ids1, bags1, items1, rejects1 = _state(rid)
    assert bags1 > 0 and rejects1 == 1  # 超大件被拒收

    # 即使站点数据已变化，同令牌重放仍直接返回首次成功结果
    _bump_stop(rid, seq=4, weight_kg=7.0)
    r2 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "t-1"})
    assert r2.status_code == 200
    assert r2.json() == r1.json()  # 返回与首次成功一致

    ids2, bags2, items2, rejects2 = _state(rid)
    assert ids2 == ids1  # 袋 id 集合不变
    assert bags2 == bags1  # 袋条数不增
    assert items2 == items1  # 袋明细不翻倍
    assert rejects2 == rejects1  # 拒收行不翻倍


def test_different_token_allows_new_bag_set(client):
    rid = _make_route()
    r1 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "t-1"})
    assert r1.status_code == 200
    _, bags1, _, rejects1 = _state(rid)

    _bump_stop(rid, seq=4, weight_kg=7.0)  # 三号点变重后需另起一袋
    r2 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "t-2"})
    assert r2.status_code == 200
    _, bags2, _, rejects2 = _state(rid)

    assert r2.json() != r1.json()  # 允许出现新袋集合
    assert bags2 == bags1 + 1  # 覆盖写为新结果，而非追加翻倍
    assert rejects2 == rejects1  # 拒收行不翻倍

    # 旧令牌的幂等记录随覆盖写清理，只保留当前令牌
    db = SessionLocal()
    try:
        keys = db.scalars(select(PackRun.idempotency_key)).all()
        assert keys == ["t-2"]
    finally:
        db.close()


def test_no_token_keeps_overwrite_semantics(client):
    rid = _make_route()
    r1 = client.post("/api/pack", json={"route_id": rid})
    assert r1.status_code == 200
    _, bags1, _, rejects1 = _state(rid)

    _bump_stop(rid, seq=4, weight_kg=7.0)
    r2 = client.post("/api/pack", json={"route_id": rid})
    assert r2.status_code == 200
    _, bags2, _, rejects2 = _state(rid)

    assert r2.json() != r1.json()  # 覆盖写：结果随数据更新
    assert bags2 == bags1 + 1
    assert rejects2 == rejects1
