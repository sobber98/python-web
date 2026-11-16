import clsx from 'clsx'
import { ArrowDownWideNarrow, ChevronDown, Layers, Plus, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
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

type SortKey = 'created_desc' | 'created_asc' | 'name_asc' | 'name_desc'

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'created_desc', label: '创建时间：最新优先' },
  { value: 'created_asc', label: '创建时间：最早优先' },
  { value: 'name_asc', label: '名称：升序' },
  { value: 'name_desc', label: '名称：降序' },
]

const collator = new Intl.Collator('zh-Hans-CN', { sensitivity: 'base', numeric: true })

function sortApps(apps: ManagedApp[], sortKey: SortKey): ManagedApp[] {
  const sorted = [...apps]
  switch (sortKey) {
    case 'name_asc':
      return sorted.sort((left, right) => collator.compare(left.name, right.name))
    case 'name_desc':
      return sorted.sort((left, right) => collator.compare(right.name, left.name))
    case 'created_asc':
      return sorted.sort((left, right) => left.created_at.localeCompare(right.created_at))
    default:
      return sorted.sort((left, right) => right.created_at.localeCompare(left.created_at))
  }
}

export function AppSidebar({ apps, activeAppId, loading }: AppSidebarProps) {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('created_desc')
  const createApp = useCreateApp()

  const createError =
    createApp.error instanceof ApiError ? createApp.error.message : createApp.error ? '创建失败' : ''

  const visibleApps = useMemo(() => {
    const query = search.trim().toLowerCase()
    const matched = query
      ? apps.filter(
          (app) =>
            app.name.toLowerCase().includes(query) || app.slug.toLowerCase().includes(query),
        )
      : apps
    return sortApps(matched, sortKey)
  }, [apps, search, sortKey])

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

      <div className="mt-4 grid gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="搜索应用"
            placeholder="搜索应用名称"
            className="w-full rounded-xl border border-white/10 bg-ink-950/60 py-2 pl-9 pr-8 text-sm text-slate-100 placeholder:text-slate-600 focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20"
          />
          {search ? (
            <button
              type="button"
              onClick={() => setSearch('')}
              aria-label="清除搜索"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-slate-500 transition hover:text-slate-200"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>

        <div className="relative">
          <ArrowDownWideNarrow className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
          <select
            value={sortKey}
            onChange={(event) => setSortKey(event.target.value as SortKey)}
            aria-label="应用排序"
            className="w-full appearance-none rounded-xl border border-white/10 bg-ink-950/60 py-2 pl-9 pr-8 text-sm text-slate-200 focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/20"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value} className="bg-ink-950 text-slate-200">
                {option.label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
        </div>
      </div>

      <nav className="mt-4 grid max-h-[26rem] grid-cols-1 gap-1 overflow-y-auto pr-1" aria-label="应用列表">
        {loading ? (
          <div className="grid gap-2">
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-14 animate-pulse rounded-2xl bg-white/[0.04]" />
            ))}
          </div>
        ) : null}

        {!loading &&
          visibleApps.map((app) => (
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
                <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[11px] text-slate-500">
                  <span className="truncate">{app.slug}</span>
                  {app.ports.length > 0 ? (
                    <span className="shrink-0 font-mono text-accent/80">
                      {app.ports.map((port) => `:${port}`).join(' ')}
                    </span>
                  ) : null}
                </span>
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

        {!loading && apps.length > 0 && visibleApps.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/10 px-3 py-6 text-center text-xs leading-relaxed text-slate-500">
            没有匹配的应用
            <br />
            试试其他关键词。
          </p>
        ) : null}
      </nav>
    </Card>
  )
}
