import clsx from 'clsx'

import type { AppStatus } from '@/types'
import { STATUS_LABELS } from '@/lib/format'

const statusClasses: Record<AppStatus, string> = {
  new: 'border-white/10 bg-white/[0.08] text-slate-300',
  installing: 'border-amber-300/30 bg-amber-300/10 text-amber-200',
  starting: 'border-sky-300/30 bg-sky-300/10 text-sky-200',
  running: 'border-accent/30 bg-accent/10 text-accent',
  stopped: 'border-white/10 bg-white/[0.06] text-slate-400',
  error: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
}

const dotClasses: Record<AppStatus, string> = {
  new: 'bg-slate-400',
  installing: 'bg-amber-300 animate-pulse',
  starting: 'bg-sky-300 animate-pulse',
  running: 'bg-accent',
  stopped: 'bg-slate-500',
  error: 'bg-rose-400',
}

interface StatusBadgeProps {
  status: AppStatus
  subtle?: boolean
}

export function StatusBadge({ status, subtle = false }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold',
        subtle ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        statusClasses[status] ?? statusClasses.new,
      )}
    >
      <span className={clsx('size-1.5 rounded-full', dotClasses[status] ?? dotClasses.new)} />
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
