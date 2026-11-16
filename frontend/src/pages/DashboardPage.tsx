import { AlertCircle, Boxes, Loader2, PackageOpen } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { AppSidebar } from '@/components/apps/AppSidebar'
import { ControlCard } from '@/components/apps/ControlCard'
import { LogsCard } from '@/components/apps/LogsCard'
import { UploadCard } from '@/components/apps/UploadCard'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/Feedback'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { formatTime } from '@/lib/format'
import { useApps } from '@/lib/queries'
import type { ManagedApp } from '@/types'

function Stat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-ink-950/40 px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={mono ? 'mt-1 font-mono text-sm text-slate-200' : 'mt-1 text-sm text-slate-200'}>
        {value}
      </p>
    </div>
  )
}

function AppSummary({ app }: { app: ManagedApp }) {
  return (
    <Card className="relative overflow-hidden p-6">
      <div className="pointer-events-none absolute -right-20 -top-24 size-64 rounded-full bg-accent/10 blur-3xl" />
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">{app.slug}</p>
          <h1 className="mt-2 truncate text-3xl font-bold tracking-tight text-white sm:text-4xl">
            {app.name}
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            期望状态：{app.desired_running ? '保持运行' : '保持停止'} · 最后更新 {formatTime(app.updated_at)}
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <StatusBadge status={app.status} />
          <p className="text-xs text-slate-500">
            {app.pid ? `进程 PID ${app.pid}` : '当前没有运行中的进程'}
          </p>
        </div>
      </div>

      {app.last_error ? (
        <div className="relative mt-4 flex items-start gap-2 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-300">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <span className="break-all">{app.last_error}</span>
        </div>
      ) : null}

      <div className="relative mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <Stat label="进程 ID" value={app.pid ? String(app.pid) : '未运行'} mono />
        <Stat
          label="监听端口"
          value={app.ports.length > 0 ? app.ports.map((port) => `:${port}`).join(' ') : '未监听'}
          mono
        />
        <Stat label="脚本" value={app.script_name ?? '未上传'} />
        <Stat label="依赖" value={`${app.dependencies.inferred.length + app.dependencies.manual.length} 个`} />
        <Stat label="创建时间" value={formatTime(app.created_at)} />
      </div>
    </Card>
  )
}

function WorkspaceSkeleton() {
  return (
    <div className="grid gap-5">
      <Card className="h-56 animate-pulse bg-white/[0.03]" />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="h-80 animate-pulse bg-white/[0.03]" />
        <Card className="h-80 animate-pulse bg-white/[0.03]" />
      </div>
    </div>
  )
}

export function DashboardPage() {
  const { appId: appIdParam } = useParams()
  const navigate = useNavigate()
  const appsQuery = useApps()
  const apps = appsQuery.data?.apps ?? []
  const parsedAppId = appIdParam && /^\d+$/.test(appIdParam) ? Number(appIdParam) : null
  const app = parsedAppId === null ? null : (apps.find((item) => item.id === parsedAppId) ?? null)

  useEffect(() => {
    if (!appIdParam && apps.length > 0) {
      navigate(`/apps/${apps[0].id}`, { replace: true })
    }
  }, [appIdParam, apps, navigate])

  let workspace: ReactNode

  if (!appIdParam) {
    if (appsQuery.isLoading || apps.length > 0) {
      workspace = <WorkspaceSkeleton />
    } else if (appsQuery.isError) {
      workspace = (
        <EmptyState
          icon={<AlertCircle className="size-6" />}
          title="无法加载应用列表"
          description="请检查服务是否正常运行，然后刷新页面重试。"
          action={<Button onClick={() => void appsQuery.refetch()}>重新加载</Button>}
        />
      )
    } else {
      workspace = (
        <EmptyState
          icon={<PackageOpen className="size-6" />}
          title="创建第一个应用"
          description="在左侧输入应用名称并创建，然后上传 Python 文件。"
        />
      )
    }
  } else if (parsedAppId === null) {
    workspace = (
      <EmptyState
        icon={<Boxes className="size-6" />}
        title="应用不存在"
        description="该应用可能已被删除，请从左侧选择一个应用。"
        action={<Button onClick={() => navigate('/')}>返回应用列表</Button>}
      />
    )
  } else if (appsQuery.isLoading) {
    workspace = <WorkspaceSkeleton />
  } else if (appsQuery.isError || !app) {
    workspace = (
      <EmptyState
        icon={<Boxes className="size-6" />}
        title="应用不存在"
        description="该应用可能已被删除，请从左侧选择一个应用。"
        action={<Button onClick={() => navigate('/')}>返回应用列表</Button>}
      />
    )
  } else {
    const liveStatus = app.status === 'running' || app.status === 'installing' || app.status === 'starting'
    workspace = (
      <div className="grid min-w-0 grid-cols-1 gap-5">
        <AppSummary app={app} />
        <div className="grid min-w-0 grid-cols-1 items-start gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <UploadCard key={app.id} app={app} />
          <ControlCard app={app} />
        </div>
        <LogsCard appId={app.id} poll={liveStatus} />
      </div>
    )
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">Workspace</p>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-white">应用管理</h2>
          <p className="mt-1 text-sm text-slate-500">管理上传的 Python 脚本、依赖与后台进程。</p>
        </div>
        {appsQuery.isFetching ? (
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <Loader2 className="size-3.5 animate-spin" />
            同步状态中
          </span>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <AppSidebar apps={apps} activeAppId={parsedAppId} loading={appsQuery.isLoading} />
        <div className="min-w-0">{workspace}</div>
      </div>
    </div>
  )
}
