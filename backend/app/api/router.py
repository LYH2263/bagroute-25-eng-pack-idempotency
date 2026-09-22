from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import (
    BagItem,
    DeliveryRoute,
    PackBag,
    PackRun,
    RejectRecord,
    SubscriberStop,
)
from app.schemas.schemas import (
    BagItemOut,
    BagOut,
    PackRequest,
    RejectOut,
    RouteOut,
    StopOut,
    WeightOut,
)
from app.services.pack_engine import StopItem, pack_route

api_router = APIRouter()


def _bag_out(db: Session, b: PackBag) -> BagOut:
    items = db.scalars(select(BagItem).where(BagItem.bag_id == b.id)).all()
    return BagOut(
        id=b.id,
        route_id=b.route_id,
        bag_index=b.bag_index,
        weight_kg=b.weight_kg,
        volume_l=b.volume_l,
        items=[
            BagItemOut(
                stop_id=i.stop_id,
                stop_name=i.stop_name,
                weight_kg=i.weight_kg,
                volume_l=i.volume_l,
            )
            for i in items
        ],
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/routes", response_model=list[RouteOut])
def routes(db: Session = Depends(get_db)):
    return db.scalars(select(DeliveryRoute).order_by(DeliveryRoute.id)).all()


@api_router.get("/stops", response_model=list[StopOut])
def stops(route_id: int | None = None, db: Session = Depends(get_db)):
    q = select(SubscriberStop).order_by(SubscriberStop.route_id, SubscriberStop.seq)
    if route_id is not None:
        q = q.where(SubscriberStop.route_id == route_id)
    return db.scalars(q).all()


@api_router.post("/pack", response_model=list[BagOut])
def pack(body: PackRequest, db: Session = Depends(get_db)):
    route = db.get(DeliveryRoute, body.route_id)
    if not route:
        raise HTTPException(404, "路线不存在")

    key = (body.idempotency_key or "").strip() or None
    if key is not None:
        run = db.scalar(
            select(PackRun).where(
                PackRun.route_id == route.id, PackRun.idempotency_key == key
            )
        )
        if run is not None:
            # 幂等重放：直接返回首次成功结果，库中袋行与拒收行保持不变
            bags = db.scalars(
                select(PackBag).where(PackBag.run_id == run.id).order_by(PackBag.bag_index)
            ).all()
            return [_bag_out(db, b) for b in bags]

    # clear previous pack for route
    old_bags = db.scalars(select(PackBag).where(PackBag.route_id == route.id)).all()
    for b in old_bags:
        for it in list(b.items):
            db.delete(it)
        db.delete(b)
    old_rej = db.scalars(select(RejectRecord).where(RejectRecord.route_id == route.id)).all()
    for r in old_rej:
        db.delete(r)
    old_runs = db.scalars(select(PackRun).where(PackRun.route_id == route.id)).all()
    for r in old_runs:
        db.delete(r)
    db.flush()

    stops = db.scalars(
        select(SubscriberStop).where(SubscriberStop.route_id == route.id).order_by(SubscriberStop.seq)
    ).all()
    items = [
        StopItem(s.id, s.seq, s.weight_kg, s.volume_l, s.name) for s in stops
    ]
    result = pack_route(items, route.max_weight_kg, route.max_volume_l)

    run: PackRun | None = None
    if key is not None:
        run = PackRun(route_id=route.id, idempotency_key=key)
        db.add(run)
        try:
            db.flush()
        except IntegrityError:
            # 并发下同令牌已被写入：回滚后按首次结果重放
            db.rollback()
            run = db.scalar(
                select(PackRun).where(
                    PackRun.route_id == route.id, PackRun.idempotency_key == key
                )
            )
            assert run is not None
            bags = db.scalars(
                select(PackBag).where(PackBag.run_id == run.id).order_by(PackBag.bag_index)
            ).all()
            return [_bag_out(db, b) for b in bags]

    out_bags: list[PackBag] = []
    for bag in result.bags:
        row = PackBag(
            route_id=route.id,
            run_id=run.id if run else None,
            bag_index=bag.bag_index,
            weight_kg=round(bag.weight_kg, 3),
            volume_l=round(bag.volume_l, 3),
        )
        db.add(row)
        db.flush()
        for it in bag.items:
            db.add(
                BagItem(
                    bag_id=row.id,
                    stop_id=it.stop_id,
                    stop_name=it.label,
                    weight_kg=it.weight_kg,
                    volume_l=it.volume_l,
                )
            )
        out_bags.append(row)
    for stop, reason in result.rejects:
        db.add(
            RejectRecord(
                route_id=route.id,
                run_id=run.id if run else None,
                stop_id=stop.stop_id,
                stop_name=stop.label,
                reason=reason,
            )
        )
    db.commit()
    return [_bag_out(db, b) for b in out_bags]


@api_router.get("/bags", response_model=list[BagOut])
def bags(db: Session = Depends(get_db)):
    rows = db.scalars(select(PackBag).order_by(PackBag.route_id, PackBag.bag_index)).all()
    return [_bag_out(db, b) for b in rows]


@api_router.get("/rejects", response_model=list[RejectOut])
def rejects(db: Session = Depends(get_db)):
    return db.scalars(select(RejectRecord).order_by(RejectRecord.id.desc())).all()


@api_router.get("/weights", response_model=list[WeightOut])
def weights(db: Session = Depends(get_db)):
    bags = db.scalars(select(PackBag).order_by(PackBag.id)).all()
    out = []
    for b in bags:
        route = db.get(DeliveryRoute, b.route_id)
        assert route
        out.append(
            WeightOut(
                bag_id=b.id,
                bag_index=b.bag_index,
                route_id=b.route_id,
                weight_kg=b.weight_kg,
                volume_l=b.volume_l,
                fill_weight_pct=round(100 * b.weight_kg / route.max_weight_kg, 1),
                fill_volume_pct=round(100 * b.volume_l / route.max_volume_l, 1),
            )
        )
    return out
