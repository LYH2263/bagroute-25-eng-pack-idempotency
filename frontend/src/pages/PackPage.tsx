import { useEffect, useState } from "react";
import { api } from "../api/client";
type R = { id: number; name: string };
type Bag = { id: number; bag_index: number; weight_kg: number; volume_l: number; items: { stop_name: string }[] };
export default function PackPage() {
  const [routes, setRoutes] = useState<R[]>([]);
  const [rid, setRid] = useState<number | "">("");
  const [token, setToken] = useState("");
  const [bags, setBags] = useState<Bag[]>([]);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  useEffect(() => { api<R[]>("/routes").then(r => { setRoutes(r); if (r[0]) setRid(r[0].id); }); }, []);
  async function run() {
    setMsg(""); setErr("");
    try {
      const key = token.trim();
      const out = await api<Bag[]>("/pack", {
        method: "POST",
        body: JSON.stringify(key ? { route_id: rid, idempotency_key: key } : { route_id: rid }),
      });
      setBags(out);
      setMsg(`完成装袋：${out.length} 袋`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (<>
    <h2>装袋</h2>
    <div className="toolbar">
      <select value={rid} onChange={e => setRid(Number(e.target.value))}>{routes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
      <input
        value={token}
        onChange={e => setToken(e.target.value)}
        placeholder="幂等令牌（可选）"
        title="填写后，同一路线用相同令牌重复装袋将直接返回首次结果，不会重复生成袋与拒收记录；留空或换令牌则重新覆盖装袋"
      />
      <button onClick={run}>按路线顺序双约束装袋</button>
    </div>
    <div className="hint">幂等令牌用于防止重复提交：同一路线携带相同令牌再次装袋时，直接返回首次成功结果，袋与拒收记录不会翻倍；不填或更换令牌则按现网语义覆盖重算。</div>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    {bags.map(b => (
      <div key={b.id}>
        <div className="mono">袋 {b.bag_index} · {b.weight_kg}kg / {b.volume_l}L</div>
        <div className="bag-row">{b.items.map((it, i) => <div className="bag-block" key={i}>{it.stop_name}</div>)}</div>
      </div>
    ))}
  </>);
}
