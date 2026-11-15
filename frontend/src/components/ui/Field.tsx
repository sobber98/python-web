import clsx from 'clsx'
import type { ReactNode } from 'react'

interface FieldProps {
  label: string
  htmlFor?: string
  hint?: ReactNode
  error?: string
  children: ReactNode
  className?: string
}

export function Field({ label, htmlFor, hint, error, children, className }: FieldProps) {
  return (
    <label className={clsx('grid gap-2', className)} htmlFor={htmlFor}>
      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
        {label}
      </span>
      {children}
      {error ? <span className="text-xs text-rose-400">{error}</span> : null}
      {hint ? <span className="text-xs leading-relaxed text-slate-500">{hint}</span> : null}
    </label>
  )
}

export const inputClassName =
  'w-full rounded-2xl border border-white/10 bg-ink-950/60 px-4 py-3 text-sm text-slate-100 ' +
  'placeholder:text-slate-600 transition focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20'
