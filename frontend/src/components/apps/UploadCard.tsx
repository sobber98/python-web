import clsx from 'clsx'
import { CheckCircle2, FileCode2, UploadCloud, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, inputClassName } from '@/components/ui/Field'
import { ProgressBar } from '@/components/ui/ProgressBar'
import { PROGRESS_STAGE_LABELS, formatBytes } from '@/lib/format'
import { useUploadScript } from '@/lib/queries'
import type { ManagedApp } from '@/types'

interface UploadCardProps {
  app: ManagedApp
}

export function UploadCard({ app }: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [localError, setLocalError] = useState('')
  const [manualDependencies, setManualDependencies] = useState(app.dependencies.manual.join('\n'))
  const upload = useUploadScript(app.id)

  const pickFile = (nextFile: File | undefined) => {
    if (!nextFile) return
    if (!nextFile.name.toLowerCase().endsWith('.py')) {
      setLocalError('只支持上传 .py 文件。')
      return
    }
    setLocalError('')
    upload.cancel()
    setFile(nextFile)
  }

  useEffect(() => {
    if (upload.success) setFile(null)
  }, [upload.success])

  const onUpload = () => {
    if (!file || upload.active) return
    upload.upload(file, manualDependencies)
  }

  const installVisible = app.progress.percent > 0 || Boolean(app.progress.message)
  const stageLabel = PROGRESS_STAGE_LABELS[app.progress.stage] ?? app.progress.stage
  const errorMessage = localError || upload.error

  return (
    <Card className="p-6">
      <CardHeader
        title="上传与依赖"
        description="上传 .py 文件后自动解析依赖、安装并重启应用。"
        icon={<UploadCloud className="size-4" />}
      />

      <div className="mt-5 grid gap-4">
        <input
          ref={inputRef}
          type="file"
          accept=".py"
          className="hidden"
          onChange={(event) => {
            pickFile(event.target.files?.[0])
            event.target.value = ''
          }}
        />

        <div
          role={file ? undefined : 'button'}
          tabIndex={file ? undefined : 0}
          aria-label={file ? undefined : '选择或拖入 Python 文件'}
          onClick={file ? undefined : () => inputRef.current?.click()}
          onKeyDown={
            file
              ? undefined
              : (event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    inputRef.current?.click()
                  }
                }
          }
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            pickFile(event.dataTransfer.files?.[0])
          }}
          className={clsx(
            'grid cursor-pointer place-items-center rounded-2xl border border-dashed px-5 py-8 text-center transition',
            dragging
              ? 'border-accent/60 bg-accent/[0.08]'
              : 'border-white/15 bg-ink-950/40 hover:border-accent/40 hover:bg-white/[0.03]',
          )}
        >
          {file ? (
            <div className="flex w-full items-center gap-3 text-left">
              <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-accent/20 bg-accent/10 text-accent">
                <FileCode2 className="size-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-white">{file.name}</span>
                <span className="mt-0.5 block text-xs text-slate-500">{formatBytes(file.size)}</span>
              </span>
              <button
                type="button"
                aria-label="移除已选文件"
                onClick={(event) => {
                  event.stopPropagation()
                  setFile(null)
                  upload.cancel()
                }}
                className="grid size-8 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-white/10 hover:text-white"
              >
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <div className="grid place-items-center gap-2">
              <UploadCloud className="size-7 text-accent" />
              <p className="text-sm font-medium text-slate-200">点击选择或拖入 Python 文件</p>
              <p className="text-xs text-slate-500">仅支持 .py，上传后会自动重启当前应用</p>
            </div>
          )}
        </div>

        <Field
          label="手动依赖"
          htmlFor="manual-dependencies"
          hint="每行一个，支持 requests==2.32.3 形式；手动依赖会优先于自动推断。"
        >
          <textarea
            id="manual-dependencies"
            rows={5}
            spellCheck={false}
            value={manualDependencies}
            onChange={(event) => setManualDependencies(event.target.value)}
            placeholder={'requests==2.32.3\nbeautifulsoup4'}
            className={clsx(inputClassName, 'resize-y font-mono text-xs leading-relaxed')}
          />
        </Field>

        {errorMessage ? (
          <p className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-300">
            {errorMessage}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">上传完成后将自动停止旧进程并重新部署。</p>
          <Button onClick={onUpload} loading={upload.active} disabled={!file}>
            <UploadCloud className="size-4" />
            上传并部署
          </Button>
        </div>

        {upload.active || upload.percent > 0 || upload.success ? (
          <div className="grid gap-2 rounded-2xl border border-white/[0.08] bg-ink-950/40 p-4" aria-live="polite">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-medium">上传进度</span>
              <span className="font-mono text-slate-300">{upload.percent}%</span>
            </div>
            <ProgressBar percent={upload.percent} />
            {upload.success ? (
              <p className="flex items-center gap-1.5 text-xs text-accent">
                <CheckCircle2 className="size-3.5" />
                文件已送达，正在后台解析依赖并安装。
              </p>
            ) : null}
          </div>
        ) : null}

        {installVisible ? (
          <div className="grid gap-2 rounded-2xl border border-white/[0.08] bg-ink-950/40 p-4" aria-live="polite">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-2 font-medium">
                安装进度
                <span className="rounded-full border border-white/10 bg-white/[0.06] px-2 py-0.5 text-[10px] text-slate-400">
                  {stageLabel}
                </span>
              </span>
              <span className="font-mono text-slate-300">{app.progress.percent}%</span>
            </div>
            <ProgressBar
              percent={app.progress.percent}
              tone={app.progress.stage === 'failed' ? 'danger' : 'accent'}
            />
            {app.progress.message ? (
              <p className="text-xs leading-relaxed text-slate-400">{app.progress.message}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  )
}
