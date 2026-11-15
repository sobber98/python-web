import clsx from 'clsx'
import { Layers, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { ApiError } from '@/lib/api'
import { useCreateApp } from '@/lib/queries'
import type { ManagedApp } from '@/types'

interface AppSidebarProps {
  apps: ManagedApp[]
  activeAppId: number | null
  loading: boolean
}

export function AppSidebar({ apps, activeAppId, loading }: AppSidebarProps) {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const createApp = useCreateApp()

  const createError =
    createApp.error instanceof ApiError ? createApp.error.message : createApp.error ? '创建失败' : ''

  return (
    <Card className="h-fit p-5 lg:sticky lg:top-24">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="size-4 text-accent" />
          <h2 className="text-sm font-semibold text-white">应用</h2>
        </div>
        <span className="rounded-full border border-white/10 bg-white/[0.06] px-2 py-0.5 text-[11px] font-medium text-slate-400">
          {apps.length}
        </span>
      </div>

      <form
        className="mt-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          const value = name.trim()
          if (!value || createApp.isPending) return
          createApp.mutate(value, {
            onSuccess: (app) => {
              setName('')
              navigate(`/apps/${app.id}`)
            },
          })
        }}
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="新应用名称"
          maxLength={60}
          className="min-w-0 flex-1 rounded-xl border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20"
        />
        <Button type="submit" size="sm" loading={createApp.isPending} aria-label="创建应用">
          <Plus className="size-4" />
        </Button>
      </form>

      {createError ? <p className="mt-2 text-xs text-rose-400">{createError}</p> : null}

      <nav className="mt-4 grid max-h-[26rem] grid-cols-1 gap-1 overflow-y-auto pr-1">
        {loading ? (
          <div className="grid gap-2">
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-14 animate-pulse rounded-2xl bg-white/[0.04]" />
            ))}
          </div>
        ) : null}

        {!loading &&
          apps.map((app) => (
            <Link
              key={app.id}
              to={`/apps/${app.id}`}
              className={clsx(
                'group flex min-w-0 items-center justify-between gap-3 rounded-2xl border px-3 py-2.5 transition',
                app.id === activeAppId
                  ? 'border-accent/25 bg-accent/[0.08]'
                  : 'border-transparent hover:border-white/10 hover:bg-white/[0.05]',
              )}
            >
              <span className="min-w-0">
                <span
                  className={clsx(
                    'block truncate text-sm font-medium',
                    app.id === activeAppId ? 'text-white' : 'text-slate-300 group-hover:text-white',
                  )}
                >
                  {app.name}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-slate-500">{app.slug}</span>
              </span>
              <StatusBadge status={app.status} subtle />
            </Link>
          ))}

        {!loading && apps.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/10 px-3 py-6 text-center text-xs leading-relaxed text-slate-500">
            还没有应用
            <br />
            在上方输入名称即可创建第一个。
          </p>
        ) : null}
      </nav>
    </Card>
  )
}
