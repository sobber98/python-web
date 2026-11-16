import clsx from 'clsx'
import { AlertCircle, CheckCircle2, Github, GitBranch, Rocket, Settings2 } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Field, inputClassName } from '@/components/ui/Field'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { ApiError } from '@/lib/api'
import { useGithubSettings, useImportGithubRepo } from '@/lib/queries'

export function GithubPage() {
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('')
  const [manualDependencies, setManualDependencies] = useState('')
  const importRepo = useImportGithubRepo()
  const githubQuery = useGithubSettings()

  const errorMessage =
    importRepo.error instanceof ApiError
      ? importRepo.error.message
      : importRepo.error
        ? '拉取仓库失败，请稍后重试。'
        : ''
  const result = importRepo.data

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!repoUrl.trim() || importRepo.isPending) return
    importRepo.mutate({ repoUrl, branch, manualDependencies })
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">Deploy</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white">GitHub 部署</h1>
          <p className="mt-1 text-sm text-slate-500">
            从 GitHub 仓库拉取 Python 代码，按目录结构自动创建或更新托管应用。
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Github className="size-3.5" />
          {githubQuery.data?.token_configured
            ? `已配置 Token（${githubQuery.data.token_hint}）`
            : '未配置 Token，仅支持公开仓库'}
          <Link to="/settings" className="text-accent hover:underline">
            配置
          </Link>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="p-6">
          <CardHeader
            title="拉取仓库"
            description="默认分支留空即可；私有仓库请先在系统设置中配置 GitHub Token。"
            icon={<Github className="size-4" />}
          />
          <form className="mt-5 grid gap-4" onSubmit={submit}>
            <Field
              label="仓库地址"
              htmlFor="repo-url"
              hint="支持 https://github.com/owner/repo、git@github.com:owner/repo.git 或 owner/repo。"
            >
              <input
                id="repo-url"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                placeholder="https://github.com/owner/repo"
                spellCheck={false}
                className={inputClassName}
              />
            </Field>

            <Field
              label="分支"
              htmlFor="repo-branch"
              hint="留空时自动使用仓库默认分支；Webhook 只会自动部署与这里匹配的分支。"
            >
              <div className="relative">
                <GitBranch className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                <input
                  id="repo-branch"
                  value={branch}
                  onChange={(event) => setBranch(event.target.value)}
                  placeholder="main"
                  spellCheck={false}
                  className={clsx(inputClassName, 'pl-11 font-mono')}
                />
              </div>
            </Field>

            <Field
              label="手动依赖（可选）"
              htmlFor="repo-manual-dependencies"
              hint="每行一个；会覆盖同名自动推断依赖，并应用到本次导入的所有应用。"
            >
              <textarea
                id="repo-manual-dependencies"
                rows={4}
                value={manualDependencies}
                onChange={(event) => setManualDependencies(event.target.value)}
                placeholder={'requests==2.32.3\nbeautifulsoup4'}
                spellCheck={false}
                className={clsx(inputClassName, 'resize-y font-mono text-xs leading-relaxed')}
              />
            </Field>

            {errorMessage ? (
              <p className="flex items-start gap-2 rounded-xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-300">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <span className="break-all">{errorMessage}</span>
              </p>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-500">导入后会在后台依次同步代码、安装依赖并启动应用。</p>
              <Button type="submit" loading={importRepo.isPending} disabled={!repoUrl.trim()}>
                <Rocket className="size-4" />
                拉取并部署
              </Button>
            </div>
          </form>

          {result ? (
            <div className="mt-5 grid gap-3 rounded-2xl border border-white/[0.08] bg-ink-950/40 p-4" aria-live="polite">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                <span className="flex items-center gap-1.5 text-accent">
                  <CheckCircle2 className="size-3.5" />
                  已接收 {result.repo}
                  {result.branch ? ` · ${result.branch}` : ''}
                  {result.commit ? ` · ${result.commit.slice(0, 7)}` : ''}
                </span>
                <span>{result.apps.length} 个应用</span>
              </div>

              <ul className="grid gap-1.5">
                {result.apps.map((app) => (
                  <li key={app.id}>
                    <Link
                      to={`/apps/${app.id}`}
                      className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2 transition hover:border-accent/30 hover:bg-white/[0.06]"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-slate-200">{app.name}</span>
                        <span className="block truncate font-mono text-[11px] text-slate-500">
                          {app.source.path}
                        </span>
                      </span>
                      <StatusBadge status={app.status} subtle />
                    </Link>
                  </li>
                ))}
              </ul>

              {result.warnings.length > 0 ? (
                <ul className="grid gap-1 text-xs text-amber-300">
                  {result.warnings.map((warning) => (
                    <li key={warning} className="flex gap-1.5">
                      <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </Card>

        <Card className="h-fit p-6">
          <div className="flex items-center gap-2">
            <Settings2 className="size-4 text-accent" />
            <h2 className="text-sm font-semibold text-white">目录约定</h2>
          </div>
          <ul className="mt-4 grid gap-3 text-sm leading-relaxed text-slate-400">
            <li className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
              仓库顶层的每个 <code className="text-accent">.py</code> 文件会创建一个独立应用。
            </li>
            <li className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
              包含多个 Python 文件的顶层目录会作为一个应用，入口优先 
              <code className="text-accent">main.py</code>、
              <code className="text-accent">app.py</code>、
              <code className="text-accent">run.py</code>、
              <code className="text-accent">__main__.py</code>。
            </li>
            <li className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
              应用目录内的 <code className="text-accent">requirements.txt</code> 会被自动读取并合并安装。
            </li>
            <li className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
              <code className="text-accent">tests</code>、<code className="text-accent">docs</code>、
              <code className="text-accent">.github</code> 等目录会被跳过。
            </li>
            <li className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-accent" />
              重新导入同一仓库时，已存在的应用会原地更新，不会重复创建。
            </li>
          </ul>
        </Card>
      </div>
    </div>
  )
}
