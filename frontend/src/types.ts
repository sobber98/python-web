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

export interface ManagedApp {
  id: number
  name: string
  slug: string
  script_name: string | null
  status: AppStatus
  desired_running: boolean
  pid: number | null
  last_error: string
  progress: AppProgress
  dependencies: AppDependencies
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

export interface ApiMessageResponse {
  ok: boolean
}

export interface UploadAcceptedResponse {
  accepted: boolean
  app_id: number
}
