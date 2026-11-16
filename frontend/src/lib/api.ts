import type {
  ApiMessageResponse,
  AppListResponse,
  GithubDeployResponse,
  GithubImportResponse,
  GithubSettingsResponse,
  LogsResponse,
  ManagedApp,
  SessionResponse,
  SettingsResponse,
} from '@/types'

export class ApiError extends Error {
  readonly status: number
  readonly payload: unknown

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

function extractMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>
    if (typeof record.error === 'string') return record.error
    if (typeof record.detail === 'string') return record.detail
  }
  return `请求失败（HTTP ${status}）`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  headers.set('Accept', 'application/json')

  const response = await fetch(path, {
    ...options,
    headers,
    credentials: 'same-origin',
  })

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    if (response.status === 401 && path !== '/api/auth/login' && window.location.pathname !== '/login') {
      window.location.replace('/login')
    }
    throw new ApiError(extractMessage(payload, response.status), response.status, payload)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  session: () => request<SessionResponse>('/api/auth/session'),
  login: (password: string) =>
    request<SessionResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  logout: () => request<ApiMessageResponse>('/api/auth/logout', { method: 'POST' }),

  listApps: () => request<AppListResponse>('/api/apps'),
  getApp: (appId: number) => request<ManagedApp>(`/api/apps/${appId}`),
  createApp: (name: string) =>
    request<ManagedApp>('/api/apps', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  deleteApp: (appId: number) =>
    request<ApiMessageResponse>(`/api/apps/${appId}`, { method: 'DELETE' }),
  startApp: (appId: number) =>
    request<ManagedApp>(`/api/apps/${appId}/start`, { method: 'POST' }),
  stopApp: (appId: number) =>
    request<ManagedApp>(`/api/apps/${appId}/stop`, { method: 'POST' }),
  restartApp: (appId: number) =>
    request<ManagedApp>(`/api/apps/${appId}/restart`, { method: 'POST' }),
  logs: (appId: number) => request<LogsResponse>(`/api/apps/${appId}/logs`),
  downloadUrl: (appId: number) => `/api/apps/${appId}/download`,

  settings: () => request<SettingsResponse>('/api/settings'),
  saveSettings: (source: string, customUrl: string) =>
    request<SettingsResponse>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ source, custom_url: customUrl }),
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<ApiMessageResponse>('/api/settings/password', {
      method: 'PUT',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  githubSettings: () => request<GithubSettingsResponse>('/api/github'),
  saveGithubSettings: (payload: {
    token?: string
    webhook_secret?: string
    regenerate_webhook_secret?: boolean
  }) =>
    request<GithubSettingsResponse>('/api/github', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  importGithubRepo: (repoUrl: string, branch: string, manualDependencies: string) =>
    request<GithubImportResponse>('/api/github/import', {
      method: 'POST',
      body: JSON.stringify({
        repo_url: repoUrl,
        branch,
        manual_dependencies: manualDependencies,
      }),
    }),
  redeployGithub: (appId: number, manualDependencies?: string) =>
    request<GithubDeployResponse>(`/api/apps/${appId}/github/deploy`, {
      method: 'POST',
      body: JSON.stringify({ manual_dependencies: manualDependencies ?? null }),
    }),
}
