import clsx from 'clsx'
import { RefreshCw, ScrollText } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { useLogs } from '@/lib/queries'

interface LogsCardProps {
  appId: number
  poll?: boolean
}

export function LogsCard({ appId, poll = true }: LogsCardProps) {
  const logsQuery = useLogs(appId, poll)
  const [autoScroll, setAutoScroll] = useState(true)
  const preRef = useRef<HTMLPreElement>(null)
  const logs = logsQuery.data?.logs ?? ''

  useEffect(() => {
    if (autoScroll && preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  return (
    <Card className="p-6">
      <CardHeader
        title="运行日志"
        description="应用运行时每 4 秒自动刷新，展示当前应用的最近输出。"
        icon={<ScrollText className="size-4" />}
        actions={
          <div className="flex items-center gap-2">
            <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(event) => setAutoScroll(event.target.checked)}
                className="size-3.5 accent-accent"
              />
              自动滚动
            </label>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void logsQuery.refetch()}
              aria-label="刷新日志"
            >
              <RefreshCw className={clsx('size-3.5', logsQuery.isFetching && 'animate-spin')} />
              刷新
            </Button>
          </div>
        }
      />

      <div className="relative mt-5">
        <pre
          ref={preRef}
          className="max-h-[32rem] min-h-[18rem] w-full overflow-auto whitespace-pre-wrap break-words rounded-2xl border border-white/5 bg-ink-950/80 p-4 font-mono text-xs leading-relaxed text-slate-300"
        >
          {logs || '暂无日志输出。应用启动后，日志会显示在这里。'}
        </pre>
        {logsQuery.isError ? (
          <p className="mt-2 text-xs text-rose-400">日志加载失败，请稍后重试。</p>
        ) : null}
      </div>
    </Card>
  )
}
