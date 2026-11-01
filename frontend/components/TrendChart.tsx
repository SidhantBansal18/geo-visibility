"use client";

import { useState } from "react";
import {
  Area, CartesianGrid, ComposedChart, LabelList, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, EngineDot } from "@/components/ui";
import { ENGINE_LABEL, ENGINE_ORDER, type RunBrief, fmtDate } from "@/lib/api";

type Mode = "overall" | "engines";

export function TrendChart({ runs }: { runs: RunBrief[] }) {
  const [mode, setMode] = useState<Mode>("overall");
  const [table, setTable] = useState(false);
  const done = runs.filter((r) => r.status === "done" && r.visibility != null);
  const engines = ENGINE_ORDER.filter((e) => done.some((r) => r.per_engine[e] != null));

  const data = done.map((r, i) => ({
    id: r.id,
    label: `#${i + 1} · ${fmtDate(r.finished_at)}`,
    when: fmtDate(r.finished_at, true),
    overall: r.visibility,
    band: r.ci ? [r.ci[0], r.ci[1]] : null,
    // Range band as a stack: invisible base at the low bound + filled spread.
    bandLo: r.ci ? r.ci[0] : null,
    bandSpread: r.ci ? r.ci[1] - r.ci[0] : null,
    ...Object.fromEntries(engines.map((e) => [e, r.per_engine[e]])),
  }));
  const last = data.length - 1;

  // End-of-line labels: push apart so they never overlap (min gap in value units,
  // ~14px on the 216px-tall plot area).
  const PLOT_PX = 216;
  const MIN_GAP = (14 / PLOT_PX) * 100;
  const labelY: Record<string, number> = {};
  if (last >= 0) {
    const ends = engines
      .map((e) => ({ e, v: Number((data[last] as Record<string, unknown>)[e] ?? NaN) }))
      .filter((x) => !Number.isNaN(x.v))
      .sort((a, b) => b.v - a.v);
    let prev = Infinity;
    for (const x of ends) {
      const y = Math.min(x.v, prev - MIN_GAP);
      labelY[x.e] = y;
      prev = y;
    }
  }

  const controls = (
    <div className="flex items-center gap-1 text-sm">
      {(["overall", "engines"] as Mode[]).map((m) => (
        <button key={m} onClick={() => setMode(m)} className={`rounded-md px-2.5 py-1 ${mode === m ? "bg-surface-2 font-medium" : "text-muted hover:text-ink"}`}>
          {m === "overall" ? "Overall" : "By engine"}
        </button>
      ))}
      <span className="mx-1 h-4 border-l border-line" />
      <button onClick={() => setTable(!table)} className="rounded-md px-2.5 py-1 text-muted hover:text-ink">{table ? "Chart" : "Table"}</button>
    </div>
  );

  return (
    <Card title="Visibility over time" subtitle="Each point is one check. The shaded band is the likely range." actions={controls}>
      {data.length < 2 && !table ? (
        <p className="py-8 text-center text-sm text-muted">
          The trend appears after your next check. Re-checks run automatically on your schedule, or click “Check now”.
        </p>
      ) : table ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead className="text-left text-muted">
              <tr><th className="py-1.5 pr-4 font-medium">Check</th><th className="pr-4 font-medium">Overall</th><th className="pr-4 font-medium">Range</th>
                {engines.map((e) => <th key={e} className="pr-4 font-medium">{ENGINE_LABEL[e]}</th>)}</tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id} className="border-t border-line">
                  <td className="py-1.5 pr-4">{d.label}</td>
                  <td className="pr-4">{d.overall?.toFixed(0)}</td>
                  <td className="pr-4 text-muted">{d.band ? `${d.band[0].toFixed(0)}–${d.band[1].toFixed(0)}` : "–"}</td>
                  {engines.map((e) => <td key={e} className="pr-4">{(d as Record<string, unknown>)[e] != null ? Number((d as Record<string, unknown>)[e]).toFixed(0) : "–"}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {mode === "engines" && (
            <div className="mb-2 flex flex-wrap gap-4 text-sm">
              {engines.map((e) => <span key={e} className="flex items-center gap-1.5"><EngineDot engine={e} />{ENGINE_LABEL[e]}</span>)}
            </div>
          )}
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 10, right: 70, bottom: 0, left: -12 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" strokeWidth={1} />
                <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={8} tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} axisLine={{ stroke: "var(--axis)" }} />
                <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: "var(--muted)", fontSize: 12 }} tickLine={false} axisLine={false} />
                <Tooltip
                  cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <div className="rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-sm">
                        <div className="mb-1 font-medium">{label}</div>
                        {payload.filter((p) => !String(p.dataKey).startsWith("band")).map((p) => (
                          <div key={String(p.dataKey)} className="flex items-center gap-2 tabular">
                            {p.dataKey !== "overall" && <EngineDot engine={String(p.dataKey)} />}
                            <span className="text-ink-2">{p.dataKey === "overall" ? "Overall" : ENGINE_LABEL[String(p.dataKey)]}</span>
                            <span className="ml-auto pl-4 font-medium">{Number(p.value).toFixed(0)}</span>
                          </div>
                        ))}
                        {mode === "overall" && (() => {
                          const b = (payload[0]?.payload as { band: number[] | null })?.band;
                          return b ? <div className="mt-0.5 text-xs text-muted tabular">range {b[0].toFixed(0)}–{b[1].toFixed(0)}</div> : null;
                        })()}
                      </div>
                    ) : null
                  }
                />
                {/* Recharts 2 ignores children wrapped in fragments, so pass an array. */}
                {mode === "overall" ? [
                    <Area key="lo" dataKey="bandLo" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} activeDot={false} />,
                    <Area key="spread" dataKey="bandSpread" stackId="band" stroke="none" fill="var(--accent)" fillOpacity={0.14} isAnimationActive={false} activeDot={false} />,
                    <Line key="overall" dataKey="overall" stroke="var(--overall)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)" }} activeDot={{ r: 5 }} isAnimationActive={false} />,
                ] : (
                  engines.map((e) => (
                    <Line key={e} dataKey={e} stroke={`var(--engine-${e})`} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)" }} activeDot={{ r: 5 }} isAnimationActive={false} connectNulls>
                      <LabelList
                        dataKey={e}
                        content={({ x, y, index }) =>
                          index === last ? (
                            <text
                              x={Number(x) + 10}
                              y={Number(y) + 4 + ((Number((data[last] as Record<string, unknown>)[e]) - (labelY[e] ?? 0)) * PLOT_PX) / 100}
                              fontSize={12}
                              fill="var(--ink-2)"
                            >
                              {ENGINE_LABEL[e]}
                            </text>
                          ) : null
                        }
                      />
                    </Line>
                  ))
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Card>
  );
}
