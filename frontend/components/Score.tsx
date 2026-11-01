"use client";

import { Card, EngineDot } from "@/components/ui";
import { ENGINE_LABEL, ENGINE_ORDER, type Summary, pct } from "@/lib/api";

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      <div className="mt-0.5 text-xs text-muted">{hint}</div>
    </div>
  );
}

export function ScoreHero({ summary, prev }: { summary: Summary; prev: number | null }) {
  const o = summary.overall;
  const v = o.visibility ?? 0;
  const delta = prev != null && o.visibility != null ? o.visibility - prev : null;
  const n = o.n;
  const halfWidth = o.ci ? (o.ci[1] - o.ci[0]) / 2 : 0;
  const noise = delta != null && Math.abs(delta) < halfWidth;
  return (
    <Card>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <div>
          <div className="text-sm text-ink-2">AI visibility score</div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="text-6xl font-semibold tracking-tight">{Math.round(v)}</span>
            <span className="text-muted">/ 100</span>
          </div>
          <div className="min-h-5">
            {delta != null && Math.abs(delta) >= 0.5 && (
              <span
                className="text-sm font-medium"
                style={{ color: noise ? "var(--muted)" : delta > 0 ? "var(--good-text)" : "var(--critical)" }}
                title={noise ? "This change is smaller than the normal run-to-run variation" : undefined}
              >
                {delta > 0 ? "▲" : "▼"} {Math.abs(Math.round(delta))} since last check{noise ? " (within normal variation)" : ""}
              </span>
            )}
          </div>
          {o.ci && (
            <p className="mt-2 text-sm text-ink-2">
              Likely range <strong className="tabular">{Math.round(o.ci[0])}–{Math.round(o.ci[1])}</strong>. AI answers vary, so treat
              differences inside this range as noise.
            </p>
          )}
          <p className="mt-2 text-xs text-muted">
            Share of {n} answers to {summary.n_queries_scored} non-branded questions where you were mentioned, averaged per question and engine.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Tile label="Ranked top 3" value={pct(o.top3_rate)} hint="of answers" />
          <Tile label="Linked to your site" value={pct(o.linked_rate)} hint="of answers" />
          <Tile label="Avg. position" value={o.avg_position != null ? `#${o.avg_position.toFixed(1)}` : "–"} hint="when listed" />
          <Tile label="Share of voice" value={pct(o.share_of_voice)} hint="of all businesses named" />
        </div>
      </div>
    </Card>
  );
}

/** Horizontal bars, one per engine, with the 95% range as a whisker and a direct label. */
export function EngineBars({ summary }: { summary: Summary }) {
  const engines = ENGINE_ORDER.filter((e) => summary.per_engine[e]);
  return (
    <Card title="By AI engine" subtitle="Visibility score per engine, with the likely range.">
      <ul className="space-y-4">
        {engines.map((e) => {
          const m = summary.per_engine[e];
          const v = m.visibility ?? 0;
          return (
            <li key={e} className="grid grid-cols-[6.5rem_minmax(0,1fr)_5.5rem] items-center gap-3" title={`${ENGINE_LABEL[e]}: ${v.toFixed(0)} (range ${m.ci?.[0] ?? "–"}–${m.ci?.[1] ?? "–"}), ${m.n} answers`}>
              <span className="flex items-center gap-2 text-sm"><EngineDot engine={e} />{ENGINE_LABEL[e]}</span>
              <div className="relative h-6">
                <div className="absolute inset-y-0 left-0 right-0 rounded" style={{ background: "var(--surface-2)" }} />
                <div className="absolute inset-y-1 left-0 rounded-r" style={{ width: `${Math.max(v, 0.5)}%`, background: `var(--engine-${e})` }} />
                {m.ci && (
                  <div className="absolute top-1/2 h-0 border-t-2" style={{ left: `${m.ci[0]}%`, width: `${m.ci[1] - m.ci[0]}%`, borderColor: "var(--ink-2)" }}>
                    <span className="absolute -top-[7px] left-0 h-3 border-l-2" style={{ borderColor: "var(--ink-2)" }} />
                    <span className="absolute -top-[7px] right-0 h-3 border-l-2" style={{ borderColor: "var(--ink-2)" }} />
                  </div>
                )}
              </div>
              <span className="text-right text-sm tabular">
                <strong>{Math.round(v)}</strong>
                {m.ci && <span className="text-muted"> ({Math.round(m.ci[0])}–{Math.round(m.ci[1])})</span>}
              </span>
            </li>
          );
        })}
      </ul>
      {summary.branded && (
        <p className="mt-5 border-t border-line pt-3 text-sm text-ink-2">
          When asked about you <em>by name</em>, engines mentioned you in <strong>{pct(summary.branded.mention_rate)}</strong> of answers.
          {summary.branded.mention_rate != null && summary.branded.mention_rate < 0.8 && " Low branded recognition usually means engines can't connect your name to your website and listings."}
        </p>
      )}
    </Card>
  );
}
