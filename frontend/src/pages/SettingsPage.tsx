import clsx from 'clsx'
import { Check, CheckCircle2, Globe2, Info, Save, Settings2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, inputClassName } from '@/components/ui/Field'
import { ApiError } from '@/lib/api'
import { useSaveSettings, useSettings } from '@/lib/queries'

export function SettingsPage() {
  const settingsQuery = useSettings()
  const saveSettings = useSaveSettings()
  const [source, setSource] = useState('official')
  const [customUrl, setCustomUrl] = useState('')
  const initialized = useRef(false)

  useEffect(() => {
    if (!settingsQuery.data || initialized.current) return
    setSource(settingsQuery.data.selector)
    setCustomUrl(settingsQuery.data.custom_url)
    initialized.current = true
  }, [settingsQuery.data])

  useEffect(() => {
    if (!saveSettings.data) return
    // 保存成功后同步服务端规范化后的值，避免本地状态与已保存值不一致。
    setSource(saveSettings.data.selector)
    setCustomUrl(saveSettings.data.custom_url)
  }, [saveSettings.data])

  const presets = settingsQuery.data?.presets ?? []
  const effectiveUrl =
    source === 'custom'
      ? customUrl.trim()
      : (presets.find((preset) => preset.key === source)?.url ?? '')
  const savedSettings = settingsQuery.data
  const dirty =
    !savedSettings || source !== savedSettings.selector || customUrl !== savedSettings.custom_url

  const errorMessage =
    saveSettings.error instanceof ApiError
      ? saveSettings.error.message
      : saveSettings.error
        ? '保存失败，请稍后重试。'
        : ''

  return (
    <div>
      <div className="mb-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">Preferences</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-white">系统设置</h1>
        <p className="mt-1 text-sm text-slate-500">
          配置上传与重启应用时 <code className="text-accent">pip install</code> 使用的依赖安装源。
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="p-6">
          <CardHeader
            title="pip 镜像源"
            description="未配置时默认使用 PyPI 官方源，行为与默认安装一致。"
            icon={<Settings2 className="size-4" />}
          />

          {settingsQuery.isLoading ? (
            <div className="mt-5 grid gap-2">
              {[0, 1, 2, 3].map((index) => (
                <div key={index} className="h-16 animate-pulse rounded-2xl bg-white/[0.04]" />
              ))}
            </div>
          ) : (
            <div className="mt-5 grid gap-2" role="radiogroup" aria-label="pip 镜像源">
              {presets.map((preset) => {
                const selected = source === preset.key
                return (
                  <button
                    key={preset.key}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setSource(preset.key)}
                    className={clsx(
                      'flex items-center gap-3 rounded-2xl border px-4 py-3.5 text-left transition',
                      selected
                        ? 'border-accent/40 bg-accent/[0.08]'
                        : 'border-white/[0.07] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]',
                    )}
                  >
                    <span
                      className={clsx(
                        'grid size-4 shrink-0 place-items-center rounded-full border',
                        selected ? 'border-accent bg-accent text-ink-950' : 'border-white/25',
                      )}
                    >
                      {selected ? <Check className="size-3" strokeWidth={3} /> : null}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-white">{preset.label}</span>
                      {preset.key === 'custom' ? (
                        <span className="mt-0.5 block text-xs text-slate-500">由你指定安装源地址</span>
                      ) : (
                        <span className="mt-0.5 block truncate font-mono text-xs text-slate-500">
                          {preset.url}
                        </span>
                      )}
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          {source === 'custom' ? (
            <div className="mt-4">
              <Field
                label="自定义镜像源 URL"
                htmlFor="custom-url"
                hint="支持 http 与 https；http 源会自动追加 --trusted-host。"
              >
                <input
                  id="custom-url"
                  type="url"
                  value={customUrl}
                  onChange={(event) => setCustomUrl(event.target.value)}
                  placeholder="https://mirrors.example.com/simple"
                  className={inputClassName}
                />
              </Field>
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/[0.07] bg-ink-950/40 px-4 py-3">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                当前生效
              </p>
              <p className="mt-1 break-all font-mono text-xs text-accent">
                {effectiveUrl || '（未设置，回退 PyPI 官方源）'}
              </p>
            </div>
            <Button
              onClick={() => saveSettings.mutate({ source, customUrl })}
              loading={saveSettings.isPending}
            >
              <Save className="size-4" />
              保存设置
            </Button>
          </div>

          {errorMessage ? (
            <p className="mt-3 rounded-xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-300">
              {errorMessage}
            </p>
          ) : null}
          {saveSettings.isSuccess && !dirty ? (
            <p className="mt-3 flex items-center gap-1.5 rounded-xl border border-accent/20 bg-accent/[0.08] px-3 py-2 text-sm text-accent">
              <CheckCircle2 className="size-4" />
              设置已保存，将在下次安装依赖时生效。
            </p>
          ) : null}
        </Card>

        <div className="grid h-fit gap-5">
          <Card className="p-6">
            <div className="flex items-center gap-2">
              <Globe2 className="size-4 text-accent" />
              <h2 className="text-sm font-semibold text-white">安装行为</h2>
            </div>
            <ul className="mt-4 grid gap-3 text-sm leading-relaxed text-slate-400">
              <li className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
                设置只影响后续的依赖安装，不会修改已创建虚拟环境中的包。
              </li>
              <li className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
                http 源会自动追加 <code className="text-slate-300">--trusted-host</code>，https 则直接使用。
              </li>
              <li className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
                每个应用使用独立虚拟环境，镜像源配置全局共享。
              </li>
            </ul>
          </Card>

          <Card className="p-6">
            <div className="flex items-center gap-2">
              <Info className="size-4 text-brand" />
              <h2 className="text-sm font-semibold text-white">提示</h2>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-400">
              如果你所在网络无法访问 PyPI，建议选择就近的国内镜像源以提升安装速度与稳定性。
            </p>
          </Card>
        </div>
      </div>
    </div>
  )
}
