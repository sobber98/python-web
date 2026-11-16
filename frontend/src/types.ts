export type AppStatus = 'new' | 'installing' | 'starting' | 'running' | 'stopped' | 'error'

export interface AppProgress {
  stage: string
  percent: number
  message: string
}

export interface AppDependencies {
  inferred: string[]
  manual: string[]
}

export interface AppSource {
  type: 'upload' | 'github'
  repo: string
  branch: string
  path: string
  commit: string
}

export interface ManagedApp {
  id: number
  name: string
  slug: string
  script_name: string | null
  status: AppStatus
  desired_running: boolean
  pid: number | null
  ports: number[]
  last_error: string
  progress: AppProgress
  dependencies: AppDependencies
  source: AppSource
  created_at: string
  updated_at: string
}

export interface AppListResponse {
  apps: ManagedApp[]
}

export interface SessionResponse {
  authenticated: boolean
}

export interface LogsResponse {
  logs: string
}

export interface MirrorPreset {
  key: string
  label: string
  url: string
}

export interface SettingsResponse {
  presets: MirrorPreset[]
  selector: string
  custom_url: string
  effective_url: string
}

export interface GithubSettingsResponse {
  token_configured: boolean
  token_hint: string
  webhook_secret: string
  webhook_url: string
}

export interface GithubImportResponse {
  accepted: boolean
  repo: string
  branch: string
  commit: string
  warnings: string[]
  apps: ManagedApp[]
}

export interface GithubDeployResponse {
  accepted: boolean
  branch: string
  commit: string
}

export interface ApiMessageResponse {
  ok: boolean
}
