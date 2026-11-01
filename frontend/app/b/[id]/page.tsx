"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { MockBanner } from "@/components/MockBanner";
import { Competitors, QueryMatrix, Recommendations, SiteAudit, SourceGaps } from "@/components/Panels";
import { ResponsesDrawer } from "@/components/ResponsesDrawer";
import { EngineBars, ScoreHero } from "@/components/Score";
import { TrendChart } from "@/components/TrendChart";
import { Button, Card, ErrorNote, LinkButton, Spinner } from "@/components/ui";
import { api, type Business, type RunBrief, type RunDetail, fmtDate } from "@/lib/api";

export default function Dashboard() {
  const { id } = useParams<{ id: string }>();
  const bid = Number(id);
  const [biz, setBiz] = useState<Business | null>(null);
  const [runs, setRuns] = useState<RunBrief[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cell, setCell] = useState<{ q: number; e: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [b, rs] = await Promise.all([api.business(bid), api.runs(bid)]);
      setBiz(b);
      setRuns(rs);
      setError(null);
      return rs;
    } catch (e) {
      setError((e as Error).message);
      return [];
    }
  }, [bid]);

  // Initial load: select the latest completed run.
  useEffect(() => {
    load().then((rs) => {
      const done = rs.filter((r) => r.status === "done");
      setSelected(done.length ? done[done.length - 1].id : null);
    });
  }, [load]);

  // Poll while a run is in flight; jump to it when it finishes.
  const active = runs.find((r) => r.status === "queued" || r.status === "running");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(async () => {
      const rs = await load();
      const a = rs.find((r) => r.id === active.id);
      if (a && a.status === "done") setSelected(a.id);
    }, 1500);
    return () => clearInterval(t);
  }, [active?.id, load]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selected == null) return setRun(null);
    api.run(selected).then(setRun).catch((e) => setError((e as Error).message));
  }, [selected]);

  async function checkNow() {
    setStarting(true);
    try {
      await api.startRun(bid);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  if (!biz) return error ? <ErrorNote>{error}</ErrorNote> : <div className="flex justify-center py-20 text-muted"><Spinner /></div>;

  const doneRuns = runs.filter((r) => r.status === "done");
  const selIdx = doneRuns.findIndex((r) => r.id === selected);
  const prev = selIdx > 0 ? doneRuns[selIdx - 1].visibility : null;
  const lastFailed = runs.length && runs[runs.length - 1].status === "failed" ? runs[runs.length - 1] : null;
  const names = [biz.name, ...biz.aliases];

  return (
    <div className="space-y-6">
      <MockBanner />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{biz.name}</h1>
          <p className="text-sm text-ink-2">
            {biz.category} · {biz.location} ·{" "}
            <a href={biz.url} target="_blank" rel="noreferrer" className="hover:text-accent">{biz.domain}</a>
          </p>
          <p className="mt-1 text-xs text-muted">
            {biz.recheck_enabled ? `Re-checks every ${biz.recheck_days} days${biz.next_run_at ? ` · next ${fmtDate(biz.next_run_at)}` : ""}` : "Automatic re-checks off"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {doneRuns.length > 1 && (
            <select
              className="rounded-lg border border-line bg-surface px-2 py-2 text-sm"
              value={selected ?? ""}
              onChange={(e) => setSelected(Number(e.target.value))}
              aria-label="Choose a check to view"
            >
              {[...doneRuns].reverse().map((r) => (
                <option key={r.id} value={r.id}>{fmtDate(r.finished_at, true)}{r.trigger === "scheduled" ? " (auto)" : ""}</option>
              ))}
            </select>
          )}
          <LinkButton href={`/b/${bid}/settings`}>Questions & settings</LinkButton>
          <Button onClick={checkNow} disabled={!!active || starting}>{active || starting ? <Spinner /> : null}Check now</Button>
        </div>
      </div>

      {active && (
        <Card>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2"><Spinner /> Checking: {active.stage}</span>
            <span className="tabular text-muted">{active.progress_done} / {active.progress_total || "…"} answers</span>
          </div>
          <div className="mt-3 h-2 rounded-full bg-surface-2">
            <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${active.progress_total ? (100 * active.progress_done) / active.progress_total : 3}%` }} />
          </div>
        </Card>
      )}

      {lastFailed && !active && <ErrorNote>The last check failed: {lastFailed.error}</ErrorNote>}
      {error && <ErrorNote>{error}</ErrorNote>}

      {!run && !active && doneRuns.length === 0 && (
        <Card><p className="text-sm text-muted">No completed checks yet. Click “Check now” to run one.</p></Card>
      )}

      {run?.summary && (
        <>
          <ScoreHero summary={run.summary} prev={prev} />
          <div className="grid gap-6 lg:grid-cols-2">
            <EngineBars summary={run.summary} />
            <TrendChart runs={runs} />
          </div>
          <Recommendations key={run.id} recs={run.recommendations} />
          <SourceGaps items={run.source_gaps} />
          <Competitors items={run.competitors} targetName={biz.name} targetRate={run.summary.overall.mention_rate ?? 0} />
          <QueryMatrix summary={run.summary} onSelect={(q, e) => setCell({ q, e })} />
          <SiteAudit audit={run.site_audit} competitors={run.competitor_audits} />
          <p className="text-xs text-muted">
            Checked {fmtDate(run.finished_at, true)} · {run.summary.overall.n} scored answers · {run.samples_per_query} samples per question
            {run.summary.n_errors ? ` · ${run.summary.n_errors} engine errors excluded` : ""}. AI answers change over time; this is a snapshot.
          </p>
        </>
      )}

      {cell && run && (
        <ResponsesDrawer runId={run.id} queryId={cell.q} engine={cell.e} names={names} onClose={() => setCell(null)} />
      )}
    </div>
  );
}
