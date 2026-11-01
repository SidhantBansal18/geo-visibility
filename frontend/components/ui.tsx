"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Card({ title, subtitle, actions, children, className = "" }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:opacity-90",
  secondary: "border border-line bg-surface hover:bg-surface-2",
  ghost: "hover:bg-surface-2",
  danger: "border border-line text-critical hover:bg-surface-2",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
    />
  );
}

export function LinkButton({ href, variant = "secondary", children }: { href: string; variant?: Variant; children: ReactNode }) {
  return (
    <Link href={href} className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition ${VARIANTS[variant]}`}>
      {children}
    </Link>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "good" | "critical" }) {
  const tones = {
    neutral: "bg-surface-2 text-ink-2",
    accent: "bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-accent",
    good: "bg-[color-mix(in_srgb,var(--good)_14%,transparent)] text-good",
    critical: "bg-[color-mix(in_srgb,var(--critical)_14%,transparent)] text-critical",
  };
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

/** Status always pairs an icon and a label with the color. */
export function Status({ state, label }: { state: "good" | "warning" | "critical" | "unknown"; label: string }) {
  const map = {
    good: { icon: "✓", color: "var(--good)" },
    warning: { icon: "!", color: "var(--warning)" },
    critical: { icon: "✕", color: "var(--critical)" },
    unknown: { icon: "?", color: "var(--muted)" },
  }[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span
        aria-hidden
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold"
        style={{ background: map.color, color: state === "warning" ? "#0b0b0b" : "#fff" }}
      >
        {map.icon}
      </span>
      <span>{label}</span>
    </span>
  );
}

export function EngineDot({ engine }: { engine: string }) {
  return <span aria-hidden className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: `var(--engine-${engine})` }} />;
}

export function Spinner() {
  return <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-label="Loading" />;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-lg border border-line bg-[color-mix(in_srgb,var(--critical)_8%,transparent)] px-4 py-3 text-sm">
      {children}
    </div>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-[color-mix(in_srgb,var(--accent)_25%,transparent)]";
