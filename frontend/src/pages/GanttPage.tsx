import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
type Block = { batch_id: number; code: string; oven_id: number; oven_label: string; phase: string; start_min: number; end_min: number; ends_mismatch?: boolean };
const DAY_START = 8 * 60, DAY_END = 18 * 60, SPAN = DAY_END - DAY_START;
function pct(m: number) { return ((m - DAY_START) / SPAN) * 100; }
export default function GanttPage() {
  const [blocks, setBlocks] = useState<Block[]>([]);
  useEffect(() => { api<Block[]>("/gantt").then(setBlocks); }, []);
  const rows = useMemo(() => {
    const map = new Map<number, { label: string; blocks: Block[] }>();
    for (const b of blocks) {
      if (!map.has(b.oven_id)) map.set(b.oven_id, { label: b.oven_label, blocks: [] });
      map.get(b.oven_id)!.blocks.push(b);
    }
    return [...map.entries()];
  }, [blocks]);
  return (<>
    <h2>甘特（生产占炉）</h2>
    <div className="axis"><div /><div className="axis-scale"><span>08:00</span><span>12:00</span><span>18:00</span></div></div>
    <div className="gantt">
      {rows.map(([oid, row]) => (
        <div className="gantt-row" key={oid}>
          <div>{row.label}</div>
          <div className="gantt-track">
            {row.blocks.map((b, i) => (
              <div key={i} className={`gantt-block ${b.phase}${b.ends_mismatch ? " mismatch" : ""}`}
                style={{ left: `${pct(b.start_min)}%`, width: `${((b.end_min - b.start_min) / SPAN) * 100}%` }}
                title={`${b.code} ${b.phase}${b.ends_mismatch ? "（端点与产品时长不一致）" : ""}`}>
                {b.ends_mismatch ? "⚠ " : ""}{b.code}/{b.phase === "ferment" ? "酵" : "烤"}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  </>);
}
