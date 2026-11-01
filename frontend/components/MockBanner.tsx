"use client";

import { useEffect, useState } from "react";
import { api, type Health } from "@/lib/api";

export function MockBanner() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    api.health().then(setH).catch(() => {});
  }, []);
  if (!h) return null;
  if (h.mock)
    return (
      <div className="mb-6 rounded-lg border border-line bg-surface-2 px-4 py-2.5 text-left text-sm text-ink-2">
        <strong className="text-ink">Demo mode.</strong> AI answers are simulated (GEO_MOCK=1). Add API keys to the backend to measure real engines.
      </div>
    );
  if (h.engines.length === 0)
    return (
      <div className="mb-6 rounded-lg border border-line bg-surface-2 px-4 py-2.5 text-left text-sm text-ink-2">
        <strong className="text-ink">No AI engines configured.</strong> Set OPENAI_API_KEY, GEMINI_API_KEY or PERPLEXITY_API_KEY in the backend, or
        GEO_MOCK=1 to try a demo.
      </div>
    );
  return null;
}
