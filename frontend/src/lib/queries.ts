import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import { api, ApiError } from '@/lib/api'
import type { ManagedApp } from '@/types'

export const queryKeys = {
  session: ['session'] as const,
  apps: ['apps'] as const,
  app: (appId: number) => ['apps', appId] as const,
  logs: (appId: number) => ['apps', appId, 'logs'] as const,
  settings: ['settings'] as const,
}

export function useSession() {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: api.session,
    staleTime: 30_000,
    retry: false,
  })
}

export function useApps() {
  return useQuery({
    queryKey: queryKeys.apps,
    queryFn: api.listApps,
    refetchInterval: 4_000,
  })
}

export function useApp(appId: number | null) {
  return useQuery({
    queryKey: appId ? queryKeys.app(appId) : ['apps', 'none'],
    queryFn: () => api.getApp(appId as number),
    enabled: appId !== null,
    refetchInterval: 2_500,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  })
}

export function useLogs(appId: number | null) {
  return useQuery({
    queryKey: appId ? queryKeys.logs(appId) : ['apps', 'none', 'logs'],
    queryFn: () => api.logs(appId as number),
    enabled: appId !== null,
    refetchInterval: 4_000,
    retry: false,
  })
}

export function useCreateApp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.createApp,
    onSuccess: (app) => {
      queryClient.setQueryData(queryKeys.app(app.id), app)
      void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
    },
  })
}

type AppAction = 'start' | 'stop' | 'restart'

const appActions = {
  start: api.startApp,
  stop: api.stopApp,
  restart: api.restartApp,
}

export function useAppAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, action }: { appId: number; action: AppAction }) =>
      appActions[action](appId),
    onSuccess: (app: ManagedApp) => {
      queryClient.setQueryData(queryKeys.app(app.id), app)
      void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
      void queryClient.invalidateQueries({ queryKey: queryKeys.logs(app.id) })
    },
  })
}

export function useDeleteApp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.deleteApp,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
    },
  })
}

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: api.settings,
  })
}

export function useSaveSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ source, customUrl }: { source: string; customUrl: string }) =>
      api.saveSettings(source, customUrl),
    onSuccess: (settings) => {
      queryClient.setQueryData(queryKeys.settings, settings)
    },
  })
}

interface UploadState {
  active: boolean
  percent: number
  error: string | null
  success: boolean
}

const initialUploadState: UploadState = {
  active: false,
  percent: 0,
  error: null,
  success: false,
}

export function useUploadScript(appId: number) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<UploadState>(initialUploadState)

  const upload = useCallback(
    (file: File, manualDependencies: string) => {
      setState({ active: true, percent: 0, error: null, success: false })

      const formData = new FormData()
      formData.append('file', file)
      formData.append('manual_dependencies', manualDependencies)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', `/api/apps/${appId}/upload`)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest')
      xhr.withCredentials = true

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) return
        const percent = Math.round((event.loaded / event.total) * 100)
        setState((current) => ({ ...current, percent: Math.min(100, percent) }))
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          setState({ active: false, percent: 100, error: null, success: true })
          void queryClient.invalidateQueries({ queryKey: queryKeys.app(appId) })
          void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
          void queryClient.invalidateQueries({ queryKey: queryKeys.logs(appId) })
          return
        }
        if (xhr.status === 401) {
          window.location.replace('/login')
          return
        }
        let message = `上传失败（HTTP ${xhr.status}）`
        try {
          const payload = JSON.parse(xhr.responseText) as { error?: string; detail?: string }
          message = payload.error ?? payload.detail ?? message
        } catch {
          // 保持默认错误文案
        }
        setState({ active: false, percent: 0, error: message, success: false })
      }

      xhr.onerror = () => {
        setState({ active: false, percent: 0, error: '上传失败，请检查网络连接。', success: false })
      }

      xhr.send(formData)
    },
    [appId, queryClient],
  )

  const reset = useCallback(() => setState(initialUploadState), [])

  return { ...state, upload, reset }
}
