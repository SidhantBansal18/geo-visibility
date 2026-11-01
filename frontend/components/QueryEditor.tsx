"use client";

import { Button, inputCls } from "@/components/ui";
import { KIND_LABEL, type QueryItem, type QueryKind } from "@/lib/api";

const KINDS: QueryKind[] = ["unbranded", "use_case", "comparison", "branded"];

const KIND_HELP: Record<QueryKind, string> = {
  unbranded: "“best X in city”: the core of your score",
  use_case: "a specific situation you serve",
  comparison: "customer comparing options",
  branded: "asks about you by name; shown separately, not scored",
};

export function QueryEditor({ queries, onChange }: { queries: QueryItem[]; onChange: (q: QueryItem[]) => void }) {
  const update = (i: number, patch: Partial<QueryItem>) => onChange(queries.map((q, j) => (j === i ? { ...q, ...patch } : q)));
  const remove = (i: number) => onChange(queries.filter((_, j) => j !== i));
  const add = () => onChange([...queries, { text: "", kind: "unbranded", active: true }]);

  return (
    <div className="space-y-2">
      <ul className="space-y-2">
        {queries.map((q, i) => (
          <li key={q.id ?? `new-${i}`} className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
            <input
              type="checkbox"
              checked={q.active}
              onChange={(e) => update(i, { active: e.target.checked })}
              aria-label="Include this question"
              className="h-4 w-4 accent-[var(--accent)]"
            />
            <input
              className={`${inputCls} flex-1 ${q.active ? "" : "opacity-50"}`}
              value={q.text}
              placeholder="A question a customer would ask an AI assistant"
              onChange={(e) => update(i, { text: e.target.value })}
            />
            <select
              className={`${inputCls} sm:w-36`}
              value={q.kind}
              onChange={(e) => update(i, { kind: e.target.value as QueryKind })}
              title={KIND_HELP[q.kind]}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>{KIND_LABEL[k]}</option>
              ))}
            </select>
            <button type="button" onClick={() => remove(i)} className="rounded-md px-2 py-1 text-muted hover:bg-surface-2 hover:text-ink" aria-label="Remove question">
              ✕
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <Button type="button" variant="secondary" onClick={add} disabled={queries.length >= 30}>+ Add question</Button>
        <p className="text-xs text-muted">
          {queries.filter((q) => q.active && q.text.trim()).length} active · Branded questions are reported separately and don&apos;t count toward the score.
        </p>
      </div>
    </div>
  );
}
