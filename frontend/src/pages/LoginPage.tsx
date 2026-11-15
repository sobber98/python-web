import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Activity, KeyRound, ShieldCheck, TerminalSquare, UploadCloud } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/Button'
import { Field, inputClassName } from '@/components/ui/Field'
import { api, ApiError } from '@/lib/api'
import { queryKeys, useSession } from '@/lib/queries'

const features = [
  {
    icon: UploadCloud,
    title: '上传即部署',
    description: '自动解析依赖、创建独立虚拟环境并重启进程。',
  },
  {
    icon: Activity,
    title: '状态实时可见',
    description: '安装进度、运行状态和日志统一在一个控制台中。',
  },
  {
    icon: ShieldCheck,
    title: '管理员专属',
    description: '基于会话的登录保护，所有管理操作均需认证。',
  },
]

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const session = useSession()
  const [password, setPassword] = useState('')
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const login = useMutation({
    mutationFn: api.login,
    onSuccess: () => {
      queryClient.setQueryData(queryKeys.session, { authenticated: true })
      navigate(from, { replace: true })
    },
  })

  if (session.data?.authenticated) {
    return <Navigate to={from} replace />
  }

  const errorMessage =
    login.error instanceof ApiError ? login.error.message : login.error ? '登录失败，请稍后重试。' : ''

  return (
    <div className="relative grid min-h-screen overflow-hidden lg:grid-cols-[1.1fr_0.9fr]">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-32 -top-32 size-[28rem] rounded-full bg-accent/15 blur-[120px]" />
        <div className="absolute -right-24 top-1/3 size-[30rem] rounded-full bg-brand/20 blur-[130px]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.025)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
      </div>

      <section className="relative hidden flex-col justify-between p-12 lg:flex xl:p-16">
        <Logo />
        <div className="max-w-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-accent">
            Trusted Admin Console
          </p>
          <h1 className="mt-5 text-5xl font-bold leading-[1.05] tracking-tight text-white">
            把 Python 脚本，
            <br />
            变成一个可控的后台应用。
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-slate-400">
            上传脚本、安装依赖、启动进程、查看日志——所有操作都在同一个现代化控制台完成。
          </p>

          <div className="mt-10 grid gap-4">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="flex items-start gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4"
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent/20 bg-accent/10 text-accent">
                  <feature.icon className="size-5" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-white">{feature.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-400">{feature.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-slate-600">仅用于可信管理员与可信代码，不构成安全沙箱。</p>
      </section>

      <section className="relative flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md animate-fade-up rounded-[2rem] border border-white/10 bg-ink-900/80 p-8 shadow-glow backdrop-blur-2xl sm:p-10">
          <div className="flex items-center justify-between lg:hidden">
            <Logo compact />
          </div>

          <span className="mt-2 grid size-12 place-items-center rounded-2xl border border-accent/20 bg-accent/10 text-accent lg:mt-0">
            <KeyRound className="size-6" />
          </span>
          <h2 className="mt-5 text-2xl font-semibold tracking-tight text-white">管理员登录</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">
            使用 config.toml 中配置的 admin_password 进入控制台。
          </p>

          <form
            className="mt-7 grid gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (!password.trim() || login.isPending) return
              login.mutate(password)
            }}
          >
            <Field label="管理员密码" htmlFor="password">
              <input
                id="password"
                type="password"
                autoFocus
                autoComplete="current-password"
                className={inputClassName}
                placeholder="请输入管理员密码"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>

            {errorMessage ? (
              <p className="rounded-xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-300">
                {errorMessage}
              </p>
            ) : null}

            <Button type="submit" className="mt-2 w-full" loading={login.isPending}>
              进入控制台
              <ArrowRight className="size-4" />
            </Button>
          </form>

          <div className="mt-6 flex items-center gap-2 border-t border-white/5 pt-5 text-xs text-slate-500">
            <TerminalSquare className="size-4" />
            会话由签名 Cookie 保护，退出登录后立即失效。
          </div>
        </div>
      </section>
    </div>
  )
}
