import clsx from 'clsx'
import { TerminalSquare } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface LogoProps {
  compact?: boolean
}

export function Logo({ compact = false }: LogoProps) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-10 place-items-center rounded-2xl bg-gradient-to-br from-accent to-brand text-ink-950 shadow-accent">
        <TerminalSquare className="size-5" strokeWidth={2.2} />
      </span>
      {compact ? null : (
        <span className="hidden leading-tight sm:block">
          <span className="block text-sm font-bold tracking-tight text-white">Python 管理平台</span>
          <span className="block text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
            Trusted Console
          </span>
        </span>
      )}
    </div>
  )
}

interface NavItemProps {
  to: string
  active: boolean
  icon: ReactNode
  label: string
}

export function NavItem({ to, active, icon, label }: NavItemProps) {
  return (
    <Link
      to={to}
      className={clsx(
        'inline-flex h-9 items-center gap-2 rounded-full px-4 text-sm font-medium transition',
        active
          ? 'bg-white/10 text-white shadow-inner shadow-white/5'
          : 'text-slate-400 hover:bg-white/[0.06] hover:text-slate-200',
      )}
    >
      {icon}
      {label}
    </Link>
  )
}
