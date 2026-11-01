"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { QueryEditor } from "@/components/QueryEditor";
import { Button, Card, ErrorNote, Spinner, inputCls } from "@/components/ui";
import { api, type Business, type QueryItem } from "@/lib/api";

export default function Settings() {
  const { id } = useParams<{ id: string }>();
  const bid = Number(id);
  const router = useRouter();
  const [biz, setBiz] = useState<Business | null>(null);
  const [aliases, setAliases] = useState("");
  const [queries, setQueries] = useState<QueryItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.business(bid).then((b) => {
      setBiz(b);
      setAliases(b.aliases.join(", "));
      setQueries(b.queries ?? []);
    }).catch((e) => setError((e as Error).message));
  }, [bid]);

  async function save() {
    if (!biz) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api.patchBusiness(bid, {
        name: biz.name, category: biz.category, location: biz.location,
        aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean),
        recheck_enabled: biz.recheck_enabled, recheck_days: biz.recheck_days,
      });
      setQueries(await api.replaceQueries(bid, queries.filter((q) => q.text.trim())));
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete ${biz?.name} and all of its history? This can't be undone.`)) return;
    await api.deleteBusiness(bid);
    router.push("/");
  }

  if (!biz) return error ? <ErrorNote>{error}</ErrorNote> : <div className="flex justify-center py-20 text-muted"><Spinner /></div>;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link href={`/b/${bid}`} className="text-sm text-muted hover:text-ink">← Back to dashboard</Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Questions & settings</h1>
        <p className="mt-1 text-sm text-ink-2">Changes apply from the next check. Keep questions stable to make trends comparable.</p>
      </div>

      <Card title="Business">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium">Name<input className={`${inputCls} mt-1`} value={biz.name} onChange={(e) => setBiz({ ...biz, name: e.target.value })} /></label>
          <label className="block text-sm font-medium">Other names<input className={`${inputCls} mt-1`} value={aliases} onChange={(e) => setAliases(e.target.value)} /></label>
          <label className="block text-sm font-medium">Category<input className={`${inputCls} mt-1`} value={biz.category} onChange={(e) => setBiz({ ...biz, category: e.target.value })} /></label>
          <label className="block text-sm font-medium">Location<input className={`${inputCls} mt-1`} value={biz.location} onChange={(e) => setBiz({ ...biz, location: e.target.value })} /></label>
        </div>
      </Card>

      <Card title="Questions">
        <QueryEditor queries={queries} onChange={setQueries} />
      </Card>

      <Card title="Automatic re-checks" subtitle="Tracking over time shows whether your changes are working.">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={biz.recheck_enabled} onChange={(e) => setBiz({ ...biz, recheck_enabled: e.target.checked })} />
            Re-check automatically
          </label>
          <label className="flex items-center gap-2">
            every
            <select className={`${inputCls} w-28`} value={biz.recheck_days} disabled={!biz.recheck_enabled} onChange={(e) => setBiz({ ...biz, recheck_days: Number(e.target.value) })}>
              {[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}
            </select>
          </label>
        </div>
      </Card>

      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex items-center justify-between">
        <Button variant="danger" onClick={remove}>Delete business</Button>
        <div className="flex items-center gap-3">
          {saved && <span className="text-sm text-good">Saved</span>}
          <Button onClick={save} disabled={saving}>{saving ? <Spinner /> : "Save"}</Button>
        </div>
      </div>
    </div>
  );
}
