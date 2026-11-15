import { Download, Play, RotateCw, Square, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { api, ApiError } from '@/lib/api'
import { useAppAction, useDeleteApp } from '@/lib/queries'
import type { ManagedApp } from '@/types'

interface ControlCardProps {
  app: ManagedApp
}

function DependencyChips({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {items.length === 0 ? (
          <span className="text-xs text-slate-600">暂无</span>
        ) : (
          items.map((item) => (
            <span
              key={item}
              className="rounded-full border border-accent/15 bg-accent/[0.08] px-2.5 py-1 font-mono text-[11px] text-accent"
            >
              {item}
            </span>
          ))
        )}
      </div>
    </div>
  )
}

export function ControlCard({ app }: ControlCardProps) {
  const navigate = useNavigate()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const action = useAppAction()
  const deleteApp = useDeleteApp()

  const runningAction = action.isPending ? action.variables?.action : null
  const canStart = !['installing', 'starting', 'running'].includes(app.status)
  const canStop = !['new', 'stopped'].includes(app.status)
  const canRestart = Boolean(app.script_name) && !['installing', 'starting'].includes(app.status)

  const errorMessage =
    action.error instanceof ApiError
      ? action.error.message
      : deleteApp.error instanceof ApiError
        ? deleteApp.error.message
        : ''

  return (
    <Card className="p-6">
      <CardHeader
        title="进程控制"
        description="启动、停止或重启当前应用，也可以下载已部署的脚本。"
        icon={<Play className="size-4" />}
      />

      <div className="mt-5 grid gap-2">
        <div className="grid grid-cols-3 gap-2">
          <Button
            size="sm"
            className="w-full"
            onClick={() => action.mutate({ appId: app.id, action: 'start' })}
            loading={runningAction === 'start'}
            disabled={!canStart}
          >
            <Play className="size-3.5" />
            启动
          </Button>
          <Button
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => action.mutate({ appId: app.id, action: 'stop' })}
            loading={runningAction === 'stop'}
            disabled={!canStop}
          >
            <Square className="size-3.5" />
            停止
          </Button>
          <Button
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={() => action.mutate({ appId: app.id, action: 'restart' })}
            loading={runningAction === 'restart'}
            disabled={!canRestart}
          >
            <RotateCw className="size-3.5" />
            重启
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {app.script_name ? (
            <a
              href={api.downloadUrl(app.id)}
              className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-full border border-white/10 bg-white/[0.07] px-3.5 text-xs font-semibold text-slate-100 transition hover:border-white/20 hover:bg-white/[0.12]"
            >
              <Download className="size-3.5" />
              下载脚本
            </a>
          ) : (
            <span className="inline-flex h-9 w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-full border border-white/5 px-3.5 text-xs font-semibold text-slate-600">
              <Download className="size-3.5" />
              下载脚本
            </span>
          )}
          <Button
            size="sm"
            variant="danger"
            className="w-full"
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 className="size-3.5" />
            删除
          </Button>
        </div>
      </div>

      {errorMessage ? (
        <p className="mt-3 rounded-xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-300">
          {errorMessage}
        </p>
      ) : null}

      <div className="mt-5 grid gap-4 border-t border-white/5 pt-5">
        <DependencyChips title="推断依赖" items={app.dependencies.inferred} />
        <DependencyChips title="手动依赖" items={app.dependencies.manual} />
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title={`删除应用「${app.name}」？`}
        description="该操作会停止进程并删除应用目录、虚拟环境与日志，且无法撤销。"
        busy={deleteApp.isPending}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => {
          deleteApp.mutate(app.id, {
            onSuccess: () => {
              setConfirmOpen(false)
              navigate('/')
            },
          })
        }}
      />
    </Card>
  )
}
