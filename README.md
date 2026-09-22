# BagRoute

投递装袋：按路线订户顺序装袋，重量与体积双约束，超限拒收。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4300 |
| API | http://localhost:9300 |
| API 文档 | http://localhost:9300/docs |
| Postgres | localhost:5444 |

健康检查：`GET http://localhost:9300/api/health`

## 页面

- `/routes` — 路线
- `/stops` — 订户点
- `/pack` — 装袋
- `/bags` — 袋明细
- `/rejects` — 拒收
- `/weights` — 袋重

## 使用说明

1. 查看路线与订户点顺序。
2. 在装袋页选择路线执行双约束装袋。
3. 袋明细与袋重查看结果，拒收页查看超限订户。

## 装袋接口与幂等令牌

`POST /api/pack` 请求体：

```json
{ "route_id": 1, "idempotency_key": "可选令牌" }
```

- `idempotency_key` 可选。同一路线携带相同令牌再次装袋时，接口直接返回首次成功的袋结果，库中袋行与拒收行不会翻倍或被替换。
- 不带令牌或更换令牌时保持覆盖写语义：清空该路线旧结果后重新装袋。
- 装袋页的"幂等令牌"输入框即对应此字段，用于防止重复提交。

## 开发与测试

```bash
docker compose exec api pytest -q
```
