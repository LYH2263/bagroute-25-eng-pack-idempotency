import { useEffect, useState } from "react";
import { api } from "../api/client";
type R = { id: number; name: string };
type Bag = { id: number; bag_index: number; weight_kg: number; volume_l: number; items: { stop_name: string }[] };
export default function PackPage() {
  const [routes, setRoutes] = useState<R[]>([]);
  const [rid, setRid] = useState<number | "">("");
  const [idemKey, setIdemKey] = useState("");
  const [bags, setBags] = useState<Bag[]>([]);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  useEffect(() => { api<R[]>("/routes").then(r => { setRoutes(r); if (r[0]) setRid(r[0].id); }); }, []);
  async function run() {
    setMsg(""); setErr("");
    try {
      const key = idemKey.trim();
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
        value={idemKey}
        onChange={e => setIdemKey(e.target.value)}
        placeholder="幂等键（可选）"
      />
      <button onClick={run}>按路线顺序双约束装袋</button>
    </div>
    <div className="hint">
      幂等键用于安全重试：同一路线携带相同键重复装袋时，直接返回首次成功的袋结果，不会重复生成袋或拒收记录；留空或更换键则按现网语义重新覆盖装袋。
    </div>
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
