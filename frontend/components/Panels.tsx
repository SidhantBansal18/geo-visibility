"use client";

import { useState } from "react";
import { Badge, Card, EngineDot, Status } from "@/components/ui";
import {
  type Audit, type Competitor, ENGINE_LABEL, ENGINE_ORDER, KIND_LABEL, type Recommendation, type SourceGap, type Summary, api, pct,
} from "@/lib/api";

const CAT_LABEL: Record<Recommendation["category"], string> = { source_gap: "Off-site", site: "Your website", content: "Content" };

export function Recommendations({ recs }: { recs: Recommendation[] }) {
  const [items, setItems] = useState(recs);
  const [open, setOpen] = useState<number | null>(recs[0]?.id ?? null);

  async function toggle(r: Recommendation) {
    setItems((xs) => xs.map((x) => (x.id === r.id ? { ...x, done: !x.done } : x)));
    try {
      await api.setRecDone(r.id, !r.done);
    } catch {
      setItems((xs) => xs.map((x) => (x.id === r.id ? { ...x, done: r.done } : x)));
    }
  }

  return (
    <Card title="What to do next" subtitle="Ranked by likely impact. Each one shows what we saw in your results, plus a reference.">
      {items.length === 0 ? (
        <p className="text-sm text-muted">No recommendations. You&apos;re in good shape for these questions.</p>
      ) : (
        <ol className="divide-y divide-[var(--border)]">
          {items.map((r, i) => {
            const isOpen = open === r.id;
            const observed = r.evidence.filter((e) => e.kind === "observed");
            const refs = r.evidence.filter((e) => e.kind === "reference");
            return (
              <li key={r.id} className="py-3">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={r.done}
                    onChange={() => toggle(r)}
                    className="mt-1 h-4 w-4 accent-[var(--accent)]"
                    aria-label={`Mark “${r.title}” as done`}
                  />
                  <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(isOpen ? null : r.id)} aria-expanded={isOpen}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm text-muted tabular">{i + 1}.</span>
                      <span className={`font-medium ${r.done ? "text-muted line-through" : ""}`}>{r.title}</span>
                      <Badge>{CAT_LABEL[r.category]}</Badge>
                    </div>
                  </button>
                  <span className="text-muted">{isOpen ? "−" : "+"}</span>
                </div>
                {isOpen && (
                  <div className="ml-7 mt-2 space-y-3 text-sm">
                    <p className="text-ink-2">{r.detail}</p>
                    {observed.length > 0 && (
                      <div>
                        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Seen in your results</div>
                        <ul className="space-y-1">
                          {observed.map((e, k) => (
                            <li key={k} className="break-words">
                              {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{e.label}</a> : e.label}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {refs.length > 0 && (
                      <div>
                        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Reference</div>
                        <ul className="space-y-1">
                          {refs.map((e, k) => (
                            <li key={k}><a href={e.url ?? "#"} target="_blank" rel="noreferrer" className="text-accent hover:underline">{e.label}</a></li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

function Meter({ value, color = "var(--accent)" }: { value: number; color?: string }) {
  return (
    <div className="h-2 w-full rounded-full bg-surface-2">
      <div className="h-2 rounded-full" style={{ width: `${Math.max(2, value * 100)}%`, background: color }} />
    </div>
  );
}

export function Competitors({ items, targetName, targetRate }: { items: Competitor[]; targetName: string; targetRate: number }) {
  const rows = [...items.slice(0, 10)];
  return (
    <Card title="Who AI recommends instead" subtitle="Businesses named in answers to your non-branded questions.">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Business</th>
              <th className="w-40 pr-3 font-medium">Appears in</th>
              <th className="pr-3 text-right font-medium">Avg. pos.</th>
              <th className="pr-1 font-medium">Engines</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-line bg-surface-2">
              <td className="py-2 pr-3 font-medium">{targetName} <span className="text-xs font-normal text-muted">(you)</span></td>
              <td className="pr-3"><div className="flex items-center gap-2"><Meter value={targetRate} color="var(--ink)" /><span className="w-10 text-right tabular">{pct(targetRate)}</span></div></td>
              <td className="pr-3 text-right text-muted">–</td>
              <td />
            </tr>
            {rows.map((c) => (
              <tr key={c.name} className="border-t border-line">
                <td className="py-2 pr-3">
                  <div className="font-medium">{c.name}</div>
                  {c.domain && <a href={`https://${c.domain}`} target="_blank" rel="noreferrer" className="text-xs text-muted hover:text-accent">{c.domain}</a>}
                </td>
                <td className="pr-3"><div className="flex items-center gap-2"><Meter value={c.appearance_rate} /><span className="w-10 text-right tabular">{pct(c.appearance_rate)}</span></div></td>
                <td className="pr-3 text-right tabular">#{c.avg_position.toFixed(1)}</td>
                <td className="pr-1">
                  <div className="flex gap-1">
                    {ENGINE_ORDER.filter((e) => c.engines[e]).map((e) => (
                      <span key={e} title={`${ENGINE_LABEL[e]}: ${c.engines[e]} answers`}><EngineDot engine={e} /></span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function SourceGaps({ items }: { items: SourceGap[] }) {
  const rows = items.filter((s) => s.type !== "own" && s.type !== "competitor").slice(0, 10);
  const compSites = items.filter((s) => s.type === "competitor").reduce((n, s) => n + s.citations, 0);
  return (
    <Card
      title="Sources the engines rely on"
      subtitle="Pages cited in answers to your questions. Getting onto these is usually the fastest way to show up."
    >
      {rows.length === 0 ? (
        <p className="text-sm text-muted">The engines didn&apos;t cite any sources for these questions.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted">
              <tr>
                <th className="py-1.5 pr-3 font-medium">Source</th>
                <th className="pr-3 font-medium">Type</th>
                <th className="pr-3 text-right font-medium">Cited</th>
                <th className="pr-3 font-medium" title="Share of the answers citing this source that mentioned you">You mentioned</th>
                <th className="pr-1 font-medium">On the page?</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.domain} className="border-t border-line align-top">
                  <td className="py-2 pr-3">
                    <a href={s.pages[0]?.url} target="_blank" rel="noreferrer" className="font-medium hover:text-accent">{s.domain}</a>
                    {s.pages[0]?.title && <div className="max-w-xs truncate text-xs text-muted" title={s.pages[0].title}>{s.pages[0].title}</div>}
                    {s.top_competitors.length > 0 && <div className="text-xs text-muted">with {s.top_competitors.slice(0, 2).join(", ")}</div>}
                  </td>
                  <td className="pr-3"><Badge>{s.type_label}</Badge></td>
                  <td className="pr-3 text-right tabular">
                    {s.citations}×
                    <div className="mt-1 flex justify-end gap-1">
                      {ENGINE_ORDER.filter((e) => s.engines[e]).map((e) => (
                        <span key={e} title={`${ENGINE_LABEL[e]}: ${s.engines[e]}`}><EngineDot engine={e} /></span>
                      ))}
                    </div>
                  </td>
                  <td className="pr-3 tabular">{pct(s.target_in_answers_rate)}</td>
                  <td className="pr-1">
                    {s.listed === true ? <Status state="good" label="Listed" />
                      : s.listed === false ? <Status state="critical" label="Not found" />
                      : <Status state="unknown" label="Not checked" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {compSites > 0 && (
            <p className="mt-3 text-xs text-muted">Engines also cited competitors&apos; own websites {compSites} times (not shown).</p>
          )}
        </div>
      )}
    </Card>
  );
}

const SEQ = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6"];

function seqColor(v: number | null) {
  if (v == null) return "transparent";
  if (v === 0) return `var(${SEQ[0]})`;
  return `var(${SEQ[Math.min(6, 1 + Math.floor(v * 6))]})`;
}

export function QueryMatrix({ summary, onSelect }: { summary: Summary; onSelect: (queryId: number, engine: string) => void }) {
  const engines = ENGINE_ORDER.filter((e) => summary.engines.includes(e));
  return (
    <Card title="Question by question" subtitle="How often you were mentioned for each question. Click a cell to read the actual answers.">
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-[2px] text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="pb-1 pr-3 font-medium">Question</th>
              {engines.map((e) => (
                <th key={e} className="w-24 pb-1 text-center font-medium"><span className="inline-flex items-center gap-1.5"><EngineDot engine={e} />{ENGINE_LABEL[e]}</span></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {summary.matrix.map((row) => (
              <tr key={row.query_id}>
                <td className="py-1 pr-3">
                  <div>{row.text}</div>
                  <div className="text-xs text-muted">{KIND_LABEL[row.kind]}{row.kind === "branded" ? " · not scored" : ""}</div>
                </td>
                {engines.map((e) => {
                  const v = row.rates[e];
                  const dark = v != null && v >= 0.5;
                  return (
                    <td key={e} className="p-0">
                      <button
                        onClick={() => onSelect(row.query_id, e)}
                        className="h-10 w-full rounded text-center tabular outline-none ring-[var(--ink)] transition hover:ring-2 focus-visible:ring-2"
                        style={{ background: seqColor(v), color: dark ? "#fff" : "var(--ink)" }}
                        title={`${ENGINE_LABEL[e]} · “${row.text}”: mentioned in ${pct(v)} of answers`}
                      >
                        {v == null ? "–" : pct(v)}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center gap-2 text-xs text-muted">
        <span>0%</span>
        {SEQ.map((s) => <span key={s} className="h-3 w-6 rounded-sm" style={{ background: `var(${s})` }} />)}
        <span>100% of answers mention you</span>
      </div>
    </Card>
  );
}

const AUDIT_ROWS: { key: string; label: string; good: (v: unknown) => boolean; show?: (v: unknown) => string }[] = [
  { key: "search_bots_blocked", label: "AI search crawlers allowed", good: (v) => Array.isArray(v) && v.length === 0, show: (v) => (Array.isArray(v) && v.length ? `Blocks ${v.join(", ")}` : "") },
  { key: "local_business_schema", label: "LocalBusiness structured data", good: Boolean },
  { key: "faq", label: "FAQ / Q&A content", good: Boolean },
  { key: "reviews_on_site", label: "Reviews on site", good: Boolean },
  { key: "word_count", label: "Homepage content", good: (v) => Number(v) >= 500, show: (v) => `~${v} words` },
  { key: "meta_description", label: "Meta description", good: Boolean },
  { key: "sitemap", label: "XML sitemap", good: Boolean },
  { key: "https", label: "HTTPS", good: Boolean },
];

export function SiteAudit({ audit, competitors }: { audit: Audit | null; competitors: Audit[] }) {
  const cols = [audit, ...competitors].filter(Boolean) as Audit[];
  if (!audit) return null;
  return (
    <Card title="Website readiness" subtitle="Your site compared with the competitors that show up most.">
      {!audit.ok && <p className="mb-3 text-sm text-critical">We couldn&apos;t check your site: {audit.error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Check</th>
              {cols.map((a, i) => (
                <th key={a.domain + i} className="pr-3 font-medium">{i === 0 ? "You" : a.name || a.domain}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {AUDIT_ROWS.map((row) => (
              <tr key={row.key} className="border-t border-line">
                <td className="py-2 pr-3">{row.label}</td>
                {cols.map((a, i) => {
                  if (!a.ok) return <td key={i} className="pr-3"><Status state="unknown" label="n/a" /></td>;
                  const v = a.checks[row.key];
                  const ok = row.good(v);
                  const extra = row.show?.(v);
                  return <td key={i} className="pr-3"><Status state={ok ? "good" : "critical"} label={extra || (ok ? "Yes" : "No")} /></td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {competitors.some((c) => c.mock) && <p className="mt-2 text-xs text-muted">Competitor audits are simulated in demo mode.</p>}
    </Card>
  );
}
