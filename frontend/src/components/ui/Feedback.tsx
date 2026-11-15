import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'

export function FullPageLoader() {
  return (
    <div className="grid min-h-screen place-items-center bg-ink-950">
      <div className="flex items-center gap-3 text-sm text-slate-400">
        <Loader2 className="size-5 animate-spin text-accent" />
        正在加载控制台…
      </div>
    </div>
  )
}

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="grid place-items-center rounded-3xl border border-dashed border-white/10 bg-white/[0.02] px-6 py-16 text-center">
      <span className="grid size-14 place-items-center rounded-2xl border border-accent/20 bg-accent/10 text-accent">
        {icon}
      </span>
      <h2 className="mt-5 text-xl font-semibold text-white">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-400">{description}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  )
}
