"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MockBanner } from "@/components/MockBanner";
import { Badge, ErrorNote, LinkButton, Spinner } from "@/components/ui";
import { api, type Business, fmtDate } from "@/lib/api";

export default function Home() {
  const [items, setItems] = useState<Business[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.businesses().then(setItems).catch((e) => setError(String(e.message ?? e)));
  }, []);

  if (error) return <ErrorNote>Couldn&apos;t reach the API: {error}. Is the backend running on port 8000?</ErrorNote>;
  if (!items) return <div className="flex justify-center py-20 text-muted"><Spinner /></div>;

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-2xl py-16 text-center">
        <MockBanner />
        <h1 className="text-3xl font-semibold tracking-tight">Do AI assistants recommend your business?</h1>
        <p className="mt-3 text-ink-2">
          Enter your website. We&apos;ll ask ChatGPT, Gemini and Perplexity the questions your customers ask, several times each,
          and show how often you come up, who shows up instead, and which sources they rely on.
        </p>
        <div className="mt-8"><LinkButton href="/new" variant="primary">Check my business</LinkButton></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <MockBanner />
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Your businesses</h1>
      </div>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((b) => {
          const run = b.latest_done_run;
          const active = b.latest_run && ["queued", "running"].includes(b.latest_run.status);
          return (
            <li key={b.id}>
              <Link href={`/b/${b.id}`} className="block rounded-xl border border-line bg-surface p-5 transition hover:border-accent">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{b.name}</div>
                    <div className="truncate text-sm text-muted">{b.category} · {b.location}</div>
                  </div>
                  {active && <Badge tone="accent">Checking…</Badge>}
                </div>
                <div className="mt-5 flex items-baseline gap-2">
                  <span className="text-4xl font-semibold">{run?.visibility != null ? Math.round(run.visibility) : "–"}</span>
                  <span className="text-sm text-muted">/ 100 visibility</span>
                </div>
                {run?.ci && <div className="text-xs text-muted tabular">likely range {Math.round(run.ci[0])}–{Math.round(run.ci[1])}</div>}
                <div className="mt-3 text-xs text-muted">
                  {run ? `Last checked ${fmtDate(run.finished_at)}` : "Not checked yet"}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
