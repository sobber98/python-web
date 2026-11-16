import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Github, LayoutGrid, LogOut, Settings } from 'lucide-react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { Logo, NavItem } from '@/components/Logo'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'

export function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isAppsActive = location.pathname === '/' || location.pathname.startsWith('/apps')
  const isGithubActive = location.pathname.startsWith('/github')
  const isSettingsActive = location.pathname.startsWith('/settings')

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear()
      navigate('/login', { replace: true })
    },
  })

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-white/5 bg-ink-950/75 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-6">
            <Logo />
            <nav className="hidden items-center gap-1 sm:flex">
              <NavItem to="/" active={isAppsActive} icon={<LayoutGrid className="size-4" />} label="应用" />
              <NavItem
                to="/github"
                active={isGithubActive}
                icon={<Github className="size-4" />}
                label="GitHub 部署"
              />
              <NavItem
                to="/settings"
                active={isSettingsActive}
                icon={<Settings className="size-4" />}
                label="系统设置"
              />
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <nav className="flex items-center gap-1 sm:hidden">
              <NavItem to="/" active={isAppsActive} icon={<LayoutGrid className="size-4" />} label="应用" />
              <NavItem
                to="/github"
                active={isGithubActive}
                icon={<Github className="size-4" />}
                label="GitHub"
              />
              <NavItem
                to="/settings"
                active={isSettingsActive}
                icon={<Settings className="size-4" />}
                label="设置"
              />
            </nav>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => logout.mutate()}
              loading={logout.isPending}
            >
              <LogOut className="size-4" />
              退出登录
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pb-16 pt-6 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-white/5 py-6 text-center text-xs text-slate-600">
        可信管理员控制台 · 仅运行你信任的 Python 代码
      </footer>
    </div>
  )
}
