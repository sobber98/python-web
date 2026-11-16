import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardPage } from '@/pages/DashboardPage'
import { GithubPage } from '@/pages/GithubPage'
import { LoginPage } from '@/pages/LoginPage'
import { SettingsPage } from '@/pages/SettingsPage'
import type { ManagedApp } from '@/types'

const demoApp: ManagedApp = {
  id: 1,
  name: '演示应用',
  slug: 'demo',
  script_name: 'main.py',
  status: 'installing',
  desired_running: true,
  pid: null,
  last_error: '',
  progress: { stage: 'installing', percent: 70, message: '正在安装依赖...' },
  dependencies: { inferred: ['requests'], manual: ['requests==2.32.3'] },
  source: { type: 'upload', repo: '', branch: '', path: '', commit: '' },
  created_at: '2026-01-01 00:00:00',
  updated_at: '2026-01-01 00:00:00',
}

const githubSettingsPayload = {
  token_configured: true,
  token_hint: '****abcd',
  webhook_secret: 'whsec_demo',
  webhook_url: 'http://localhost/api/github/webhook',
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function stubApi(routes: Record<string, unknown>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path in routes) return jsonResponse(routes[path])
      return jsonResponse({ error: 'Not found' }, 404)
    }),
  )
}

function renderPage(ui: ReactElement, route: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/login" element={ui} />
          <Route path="/settings" element={ui} />
          <Route path="/github" element={ui} />
          <Route path="/apps/:appId" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoginPage', () => {
  it('渲染管理员登录表单的中文文案', async () => {
    stubApi({ '/api/auth/session': { authenticated: false } })
    renderPage(<LoginPage />, '/login')

    expect(screen.getByRole('heading', { name: '管理员登录' })).toBeInTheDocument()
    expect(screen.getByLabelText('管理员密码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /进入控制台/ })).toBeInTheDocument()
  })
})

describe('DashboardPage', () => {
  it('无应用时显示创建引导', async () => {
    stubApi({ '/api/apps': { apps: [] } })
    renderPage(<DashboardPage />, '/')

    expect(screen.getByText('应用管理')).toBeInTheDocument()
    expect(await screen.findByText('创建第一个应用')).toBeInTheDocument()
  })

  it('渲染应用详情、上传与安装进度文案', async () => {
    stubApi({
      '/api/apps': { apps: [demoApp] },
      '/api/apps/1': demoApp,
      '/api/apps/1/logs': { logs: '服务日志输出' },
    })
    renderPage(<DashboardPage />, '/apps/1')

    expect((await screen.findAllByText('演示应用')).length).toBeGreaterThan(0)
    expect(screen.getByText('上传与依赖')).toBeInTheDocument()
    expect(screen.getByText('安装进度')).toBeInTheDocument()
    expect(screen.getByText('正在安装依赖...')).toBeInTheDocument()
    expect(screen.getByText('推断依赖')).toBeInTheDocument()
    expect(screen.getByText('requests')).toBeInTheDocument()
    expect(await screen.findByText('服务日志输出')).toBeInTheDocument()
  })
})

describe('SettingsPage', () => {
  const settingsPayload = {
    presets: [
      { key: 'official', label: 'PyPI 官方源', url: 'https://pypi.org/simple' },
      { key: 'tsinghua', label: '清华大学', url: 'https://pypi.tuna.tsinghua.edu.cn/simple' },
      { key: 'custom', label: '自定义', url: '' },
    ],
    selector: 'official',
    custom_url: '',
    effective_url: 'https://pypi.org/simple',
  }

  it('渲染 pip 镜像源预设', async () => {
    stubApi({ '/api/settings': settingsPayload, '/api/github': githubSettingsPayload })
    renderPage(<SettingsPage />, '/settings')

    expect(await screen.findByText('pip 镜像源')).toBeInTheDocument()
    expect(await screen.findByText('PyPI 官方源')).toBeInTheDocument()
    expect(screen.getByText('清华大学')).toBeInTheDocument()
    expect(screen.getByText('自定义')).toBeInTheDocument()
  })

  it('渲染修改管理员密码表单', async () => {
    stubApi({ '/api/settings': settingsPayload, '/api/github': githubSettingsPayload })
    renderPage(<SettingsPage />, '/settings')

    expect(await screen.findByText('修改管理员密码')).toBeInTheDocument()
    expect(screen.getByLabelText('当前密码')).toBeInTheDocument()
    expect(screen.getByLabelText(/^新密码/)).toBeInTheDocument()
    expect(screen.getByLabelText('确认新密码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /更新密码/ })).toBeInTheDocument()
  })

  it('渲染 GitHub 集成设置', async () => {
    stubApi({ '/api/settings': settingsPayload, '/api/github': githubSettingsPayload })
    renderPage(<SettingsPage />, '/settings')

    expect(await screen.findByText('GitHub 集成')).toBeInTheDocument()
    expect(await screen.findByLabelText(/^GitHub Token/)).toBeInTheDocument()
    expect(screen.getByLabelText(/^Webhook 地址/)).toHaveValue(
      'http://localhost/api/github/webhook',
    )
    expect(screen.getByRole('button', { name: /保存 GitHub 设置/ })).toBeInTheDocument()
  })
})

describe('GithubPage', () => {
  it('渲染仓库导入表单与目录约定', async () => {
    stubApi({ '/api/github': githubSettingsPayload })
    renderPage(<GithubPage />, '/github')

    expect(screen.getByRole('heading', { name: 'GitHub 部署' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^仓库地址/)).toBeInTheDocument()
    expect(screen.getByLabelText(/^分支/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /拉取并部署/ })).toBeInTheDocument()
    expect(await screen.findByText('目录约定')).toBeInTheDocument()
  })
})
