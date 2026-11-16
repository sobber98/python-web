import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '@/lib/api'
import type { AppListResponse, ManagedApp } from '@/types'

export const queryKeys = {
  session: ['session'] as const,
  apps: ['apps'] as const,
  logs: (appId: number) => ['apps', appId, 'logs'] as const,
  settings: ['settings'] as const,
  github: ['github'] as const,
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
    refetchInterval: 3_000,
  })
}

export function useLogs(appId: number | null, poll = true) {
  return useQuery({
    queryKey: appId ? queryKeys.logs(appId) : ['apps', 'none', 'logs'],
    queryFn: () => api.logs(appId as number),
    enabled: appId !== null,
    refetchInterval: poll ? 4_000 : false,
    retry: false,
  })
}

export function useCreateApp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.createApp,
    onSuccess: (app) => {
      queryClient.setQueryData<AppListResponse>(queryKeys.apps, (current) =>
        current ? { apps: [app, ...current.apps] } : { apps: [app] },
      )
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
      queryClient.setQueryData<AppListResponse>(queryKeys.apps, (current) =>
        current
          ? { apps: current.apps.map((item) => (item.id === app.id ? app : item)) }
          : current,
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
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

export function useChangePassword() {
  return useMutation({
    mutationFn: ({
      currentPassword,
      newPassword,
    }: {
      currentPassword: string
      newPassword: string
    }) => api.changePassword(currentPassword, newPassword),
  })
}

export function useGithubSettings() {
  return useQuery({
    queryKey: queryKeys.github,
    queryFn: api.githubSettings,
  })
}

export function useSaveGithubSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      token?: string
      webhook_secret?: string
      regenerate_webhook_secret?: boolean
    }) => api.saveGithubSettings(payload),
    onSuccess: (settings) => {
      queryClient.setQueryData(queryKeys.github, settings)
    },
  })
}

export function useImportGithubRepo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      repoUrl,
      branch,
      manualDependencies,
    }: {
      repoUrl: string
      branch: string
      manualDependencies: string
    }) => api.importGithubRepo(repoUrl, branch, manualDependencies),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
    },
  })
}

export function useGithubRedeploy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      appId,
      manualDependencies,
    }: {
      appId: number
      manualDependencies?: string
    }) => api.redeployGithub(appId, manualDependencies),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
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
  const xhrRef = useRef<XMLHttpRequest | null>(null)

  const cancel = useCallback(() => {
    const xhr = xhrRef.current
    xhrRef.current = null
    xhr?.abort()
    setState(initialUploadState)
  }, [])

  useEffect(() => {
    return () => {
      xhrRef.current?.abort()
      xhrRef.current = null
    }
  }, [])

  const upload = useCallback(
    (file: File, manualDependencies: string) => {
      xhrRef.current?.abort()
      xhrRef.current = null
      setState({ active: true, percent: 0, error: null, success: false })

      const formData = new FormData()
      formData.append('file', file)
      formData.append('manual_dependencies', manualDependencies)

      const xhr = new XMLHttpRequest()
      xhrRef.current = xhr
      xhr.open('POST', `/api/apps/${appId}/upload`)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest')
      xhr.withCredentials = true

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable || xhrRef.current !== xhr) return
        const percent = Math.round((event.loaded / event.total) * 100)
        setState((current) => ({ ...current, percent: Math.min(100, percent) }))
      }

      xhr.onload = () => {
        if (xhrRef.current !== xhr) return
        xhrRef.current = null
        if (xhr.status >= 200 && xhr.status < 300) {
          setState({ active: false, percent: 100, error: null, success: true })
          void queryClient.invalidateQueries({ queryKey: queryKeys.apps })
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
        if (xhrRef.current !== xhr) return
        xhrRef.current = null
        setState({ active: false, percent: 0, error: '上传失败，请检查网络连接。', success: false })
      }

      xhr.onabort = () => {
        if (xhrRef.current === xhr) xhrRef.current = null
      }

      xhr.send(formData)
    },
    [appId, queryClient],
  )

  return { ...state, upload, cancel }
}
