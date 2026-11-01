"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { MockBanner } from "@/components/MockBanner";
import { QueryEditor } from "@/components/QueryEditor";
import { Button, Card, ErrorNote, Spinner, inputCls } from "@/components/ui";
import { api, type Health, type ProfileDraft, type QueryItem } from "@/lib/api";

type Step = "url" | "profile";

export default function NewBusiness() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("url");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProfileDraft | null>(null);
  const [queries, setQueries] = useState<QueryItem[]>([]);
  const [aliases, setAliases] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [samples, setSamples] = useState(5);
  const [engines, setEngines] = useState<string[]>([]);

  useEffect(() => {
    api.health().then((h) => {
      setHealth(h);
      setSamples(h.samples_per_query);
      setEngines(h.engines.map((e) => e.id));
    }).catch(() => {});
  }, []);

  async function analyze(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const d = await api.infer(url);
      setDraft(d);
      setAliases(d.aliases.join(", "));
      setQueries(d.queries.map((q) => ({ ...q, active: true })));
      setStep("profile");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    if (!draft) return;
    setBusy(true);
    try {
      const r = await api.suggestQueries(draft);
      setQueries(r.queries.map((q) => ({ ...q, active: true })));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const b = await api.createBusiness({
        url: draft.url,
        name: draft.name,
        category: draft.category,
        location: draft.location,
        description: draft.description,
        aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean),
        queries: queries.filter((q) => q.text.trim()),
        run_now: true,
        engines,
        samples_per_query: samples,
      });
      router.push(`/b/${b.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const activeQ = queries.filter((q) => q.active && q.text.trim()).length;
  const totalCalls = activeQ * engines.length * samples;
  const missing = draft ? (["name", "category", "location"] as const).filter((k) => !draft[k].trim()) : [];

  if (step === "url") {
    return (
      <div className="mx-auto max-w-xl py-10">
        <MockBanner />
        <h1 className="text-2xl font-semibold tracking-tight">Check a business</h1>
        <p className="mt-2 text-ink-2">We&apos;ll read the website to work out what the business does and where, then suggest the questions to test.</p>
        <form onSubmit={analyze} className="mt-6 flex gap-2">
          <input className={inputCls} placeholder="yourbusiness.com" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus required />
          <Button type="submit" disabled={busy || !url.trim()}>{busy ? <Spinner /> : "Analyze"}</Button>
        </form>
        {error && <div className="mt-4"><ErrorNote>{error}</ErrorNote></div>}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <button onClick={() => setStep("url")} className="text-sm text-muted hover:text-ink">← Change URL</button>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Confirm the details</h1>
        {draft && !draft.scrape_ok && (
          <p className="mt-2 text-sm text-ink-2">We couldn&apos;t read {draft.domain}, so please fill these in yourself.</p>
        )}
      </div>

      {draft && (
        <Card title="Business" subtitle="These drive the questions we ask and how we recognise you in answers.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Business name" missing={!draft.name.trim()}>
              <input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            <Field label="Other names / spellings" hint="Comma-separated, e.g. a short name or old name">
              <input className={inputCls} value={aliases} onChange={(e) => setAliases(e.target.value)} />
            </Field>
            <Field label="What customers search for" hint="e.g. “LED wall rental”" missing={!draft.category.trim()}>
              <input className={inputCls} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} />
            </Field>
            <Field label="Main service area" hint="City, State" missing={!draft.location.trim()}>
              <input className={inputCls} value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })} />
            </Field>
          </div>
        </Card>
      )}

      <Card
        title="Questions to test"
        subtitle="Edit these so they sound like your real customers. More questions give a more reliable score."
        actions={<Button variant="secondary" onClick={regenerate} disabled={busy || missing.length > 0}>Regenerate</Button>}
      >
        <QueryEditor queries={queries} onChange={setQueries} />
      </Card>

      <Card title="Measurement" subtitle="AI answers vary from one ask to the next, so each question is asked several times.">
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex flex-wrap gap-3">
            {(health?.engines ?? []).map((e) => (
              <label key={e.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[var(--accent)]"
                  checked={engines.includes(e.id)}
                  onChange={(ev) => setEngines(ev.target.checked ? [...engines, e.id] : engines.filter((x) => x !== e.id))}
                />
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: `var(--engine-${e.id})` }} />
                {e.label}
              </label>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            Samples per question
            <select className={`${inputCls} w-20`} value={samples} onChange={(e) => setSamples(Number(e.target.value))}>
              {[1, 3, 5, 8, 10].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <span className="text-sm text-muted tabular">{totalCalls} AI answers</span>
        </div>
      </Card>

      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="flex justify-end">
        <Button onClick={start} disabled={busy || missing.length > 0 || activeQ === 0 || engines.length === 0}>
          {busy ? <Spinner /> : "Run visibility check"}
        </Button>
      </div>
    </div>
  );
}

function Field({ label, hint, missing, children }: { label: string; hint?: string; missing?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 flex items-baseline justify-between text-sm font-medium">
        {label}
        {missing && <span className="text-xs font-normal text-critical">Required</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}
