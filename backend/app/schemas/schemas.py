from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class RouteOut(BaseModel):
    id: int
    name: str
    max_weight_kg: float
    max_volume_l: float
    model_config = {"from_attributes": True}


class StopOut(BaseModel):
    id: int
    route_id: int
    seq: int
    name: str
    weight_kg: float
    volume_l: float
    model_config = {"from_attributes": True}


class BagItemOut(BaseModel):
    stop_id: int
    stop_name: str
    weight_kg: float
    volume_l: float


class BagOut(BaseModel):
    id: int
    route_id: int
    bag_index: int
    weight_kg: float
    volume_l: float
    items: list[BagItemOut] = []
    model_config = {"from_attributes": True}


class RejectOut(BaseModel):
    id: int
    route_id: int
    stop_id: int
    stop_name: str
    reason: str
    created_at: datetime
    model_config = {"from_attributes": True}


class PackRequest(BaseModel):
    route_id: int
    idempotency_key: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "可选幂等键：同一路线携带相同键重复装袋时，直接返回首次成功的袋结果，"
            "不会重复写入袋行或拒收行；不同键或不带键则保持覆盖写入语义。"
        ),
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def _blank_key_means_none(cls, v: object) -> object:
        # 空白字符串视为未携带幂等键，避免 "" 与 None 语义分裂
        if isinstance(v, str) and not v.strip():
            return None
        return v


class WeightOut(BaseModel):
    bag_id: int
    bag_index: int
    route_id: int
    weight_kg: float
    volume_l: float
    fill_weight_pct: float
    fill_volume_pct: float
