"""幂等装袋：同键回放结果一致且袋/拒收行不翻倍，换键或裸调保持覆盖写入语义。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    DeliveryRoute,
    PackBag,
    RejectRecord,
    SubscriberStop,
)


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    db = TestingSession()
    route = DeliveryRoute(name="测试晨线", max_weight_kg=4.0, max_volume_l=10.0)
    db.add(route)
    db.flush()
    db.add_all(
        [
            SubscriberStop(route_id=route.id, seq=1, name="一号点", weight_kg=2.0, volume_l=3.0),
            SubscriberStop(route_id=route.id, seq=2, name="二号点", weight_kg=2.5, volume_l=3.0),
            SubscriberStop(route_id=route.id, seq=3, name="三号点", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=route.id, seq=4, name="超大件", weight_kg=9.0, volume_l=1.0),
        ]
    )
    db.commit()
    rid = route.id
    db.close()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    # 不使用 with 包裹，避免触发 lifespan 去连真实 Postgres
    yield TestClient(app), rid, TestingSession
    app.dependency_overrides.clear()


def _bag_ids(client, rid):
    r = client.get("/api/bags")
    assert r.status_code == 200
    return sorted(b["id"] for b in r.json() if b["route_id"] == rid)


def _row_count(session_factory, model, rid):
    db = session_factory()
    try:
        return len(db.scalars(select(model).where(model.route_id == rid)).all())
    finally:
        db.close()


def test_same_key_twice_replays_same_bags(env):
    client, rid, sf = env
    r1 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "k-1"})
    assert r1.status_code == 200
    r2 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "k-1"})
    assert r2.status_code == 200

    # 第二次调用直接返回与首次一致的结果，袋 id 集合不变
    assert r2.json() == r1.json()
    ids1 = sorted(b["id"] for b in r1.json())
    assert sorted(b["id"] for b in r2.json()) == ids1
    assert _bag_ids(client, rid) == ids1

    # 袋行与拒收行不因第二次调用而翻倍或替换
    assert _row_count(sf, PackBag, rid) == len(ids1)
    assert _row_count(sf, RejectRecord, rid) == 1  # 仅"超大件"一条


def test_different_key_allows_new_bag_set(env):
    client, rid, sf = env
    r1 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "k-1"})
    r2 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "k-2"})
    assert r2.status_code == 200

    ids1 = sorted(b["id"] for b in r1.json())
    ids2 = sorted(b["id"] for b in r2.json())
    # 换键后允许出现新袋集合（覆盖写入）
    assert ids1 != ids2
    assert set(ids1).isdisjoint(ids2)
    assert _bag_ids(client, rid) == ids2
    assert _row_count(sf, PackBag, rid) == len(ids2)
    assert _row_count(sf, RejectRecord, rid) == 1


def test_no_key_keeps_overwrite_semantics(env):
    client, rid, sf = env
    r1 = client.post("/api/pack", json={"route_id": rid})
    r2 = client.post("/api/pack", json={"route_id": rid})

    ids1 = sorted(b["id"] for b in r1.json())
    ids2 = sorted(b["id"] for b in r2.json())
    assert ids1 != ids2
    assert _bag_ids(client, rid) == ids2
    assert _row_count(sf, PackBag, rid) == len(ids2)
    assert _row_count(sf, RejectRecord, rid) == 1


def test_blank_key_treated_as_no_key(env):
    client, rid, sf = env
    r1 = client.post("/api/pack", json={"route_id": rid, "idempotency_key": "  "})
    r2 = client.post("/api/pack", json={"route_id": rid})

    ids1 = sorted(b["id"] for b in r1.json())
    ids2 = sorted(b["id"] for b in r2.json())
    # 空白键视为未携带，仍是覆盖写入
    assert ids1 != ids2
    assert _row_count(sf, PackBag, rid) == len(ids2)
