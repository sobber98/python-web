import type { AppStatus } from '@/types'

export const STATUS_LABELS: Record<AppStatus, string> = {
  new: '未配置',
  installing: '安装中',
  starting: '启动中',
  running: '运行中',
  stopped: '已停止',
  error: '错误',
}

export const PROGRESS_STAGE_LABELS: Record<string, string> = {
  idle: '空闲',
  upload_received: '已接收上传',
  parsing: '解析依赖',
  venv: '准备虚拟环境',
  installing: '安装依赖',
  starting: '启动进程',
  complete: '完成',
  failed: '失败',
}

export function formatTime(value: string): string {
  if (!value) return '—'
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const date = new Date(normalized.endsWith('Z') ? normalized : `${normalized}Z`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
