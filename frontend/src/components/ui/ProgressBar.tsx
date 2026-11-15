import clsx from 'clsx'

type Tone = 'accent' | 'brand' | 'warning' | 'danger'

const toneClasses: Record<Tone, string> = {
  accent: 'bg-gradient-to-r from-accent to-brand',
  brand: 'bg-gradient-to-r from-brand to-sky-300',
  warning: 'bg-gradient-to-r from-amber-300 to-orange-400',
  danger: 'bg-gradient-to-r from-rose-500 to-orange-400',
}

interface ProgressBarProps {
  percent: number
  tone?: Tone
  className?: string
  animated?: boolean
}

export function ProgressBar({ percent, tone = 'accent', className, animated = false }: ProgressBarProps) {
  const value = Math.max(0, Math.min(100, Math.round(percent)))
  return (
    <div className={clsx('h-2 overflow-hidden rounded-full bg-white/10', className)}>
      <div
        className={clsx(
          'h-full rounded-full transition-[width] duration-300 ease-out',
          toneClasses[tone],
          animated && 'bg-[length:200%_100%] animate-shimmer',
        )}
        style={{ width: `${value}%` }}
      />
    </div>
  )
}
