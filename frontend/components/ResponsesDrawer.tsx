"use client";

import { useEffect, useState } from "react";
import { Badge, EngineDot, Spinner } from "@/components/ui";
import { ENGINE_LABEL, type EngineResponse, api } from "@/lib/api";

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Render answer text with markdown links made clickable and the target highlighted. */
function AnswerText({ text, names }: { text: string; names: string[] }) {
  const pattern = names.filter((n) => n.length >= 3).map(escapeRe).join("|");
  const re = pattern ? new RegExp(`(${pattern})`, "gi") : null;
  const lines = text.split("\n");
  return (
    <div className="prose-answer whitespace-pre-wrap text-sm leading-relaxed">
      {lines.map((line, i) => {
        const clean = line.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, "$1");
        const parts = re ? clean.split(re) : [clean];
        return (
          <p key={i}>
            {/* split() with a capturing group puts matches at odd indices */}
            {parts.map((p, k) => (re && k % 2 === 1 ? <mark key={k} className="target">{p}</mark> : <span key={k}>{p}</span>))}
          </p>
        );
      })}
    </div>
  );
}

export function ResponsesDrawer({ runId, queryId, engine, names, onClose }: {
  runId: number;
  queryId: number;
  engine: string;
  names: string[];
  onClose: () => void;
}) {
  const [items, setItems] = useState<EngineResponse[] | null>(null);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    setItems(null);
    setIdx(0);
    api.responses(runId, { query_id: queryId, engine }).then(setItems).catch(() => setItems([]));
  }, [runId, queryId, engine]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const r = items?.[idx];
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        role="dialog"
        aria-label="AI answers"
        className="flex h-full w-full max-w-2xl flex-col overflow-hidden border-l border-line bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line p-5">
          <div>
            <div className="flex items-center gap-2 text-sm text-ink-2"><EngineDot engine={engine} />{ENGINE_LABEL[engine]}</div>
            <h3 className="mt-1 font-semibold">{items?.[0]?.query_text ?? "…"}</h3>
          </div>
          <button onClick={onClose} className="rounded-md px-2 py-1 text-muted hover:bg-surface-2" aria-label="Close">✕</button>
        </header>
        {!items ? (
          <div className="flex flex-1 items-center justify-center text-muted"><Spinner /></div>
        ) : items.length === 0 ? (
          <p className="p-5 text-sm text-muted">No answers recorded.</p>
        ) : (
          <>
            <nav className="flex flex-wrap gap-1 border-b border-line px-5 py-3">
              {items.map((x, i) => (
                <button
                  key={x.id}
                  onClick={() => setIdx(i)}
                  className={`rounded-md px-2.5 py-1 text-sm ${i === idx ? "bg-surface-2 font-medium" : "text-muted hover:text-ink"}`}
                >
                  Answer {i + 1} {x.error ? "⚠" : x.target_mentioned ? "✓" : "✕"}
                </button>
              ))}
            </nav>
            {r && (
              <div className="flex-1 space-y-4 overflow-y-auto p-5">
                <div className="flex flex-wrap gap-2">
                  {r.error ? <Badge tone="critical">Error</Badge>
                    : r.target_mentioned ? <Badge tone="good">You were mentioned{r.target_position ? ` · #${r.target_position}` : ""}</Badge>
                    : <Badge tone="critical">Not mentioned</Badge>}
                  {r.target_linked && <Badge tone="accent">Linked to your site</Badge>}
                </div>
                {r.error ? <p className="text-sm text-critical">{r.error}</p> : <AnswerText text={r.text} names={names} />}
                {r.mentions.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Businesses detected</div>
                    <ol className="list-decimal pl-5 text-sm">
                      {r.mentions.map((m) => (
                        <li key={m.position} className={m.is_target ? "font-semibold" : ""}>{m.name}{m.domain ? <span className="text-muted"> · {m.domain}</span> : null}</li>
                      ))}
                    </ol>
                  </div>
                )}
                {r.citations.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Sources cited</div>
                    <ul className="space-y-1 text-sm">
                      {r.citations.map((c, i) => (
                        <li key={i} className="break-words"><a href={c.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{c.title || c.domain}</a> <span className="text-muted">· {c.domain}</span></li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
