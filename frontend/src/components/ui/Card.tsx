import clsx from 'clsx'
import type { ReactNode } from 'react'

interface CardProps {
  className?: string
  children?: ReactNode
}

export function Card({ className, children }: CardProps) {
  return (
    <section
      className={clsx(
        'rounded-3xl border border-white/10 bg-white/[0.055] shadow-glow backdrop-blur-xl',
        className,
      )}
    >
      {children}
    </section>
  )
}

interface CardHeaderProps {
  title: string
  description?: string
  icon?: ReactNode
  actions?: ReactNode
}

export function CardHeader({ title, description, icon, actions }: CardHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        {icon ? (
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.06] text-accent">
            {icon}
          </span>
        ) : null}
        <div>
          <h2 className="text-base font-semibold text-white">{title}</h2>
          {description ? <p className="mt-1 text-sm text-slate-400">{description}</p> : null}
        </div>
      </div>
      {actions}
    </div>
  )
}
