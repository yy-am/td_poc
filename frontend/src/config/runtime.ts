const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '')

export function getApiBase(): string {
  const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined
  if (envBase && envBase.trim()) {
    return trimTrailingSlash(envBase.trim())
  }
  return '/api/v1'
}

export function getWebSocketBase(): string {
  const envBase = import.meta.env.VITE_WS_BASE_URL as string | undefined
  if (envBase && envBase.trim()) {
    return trimTrailingSlash(envBase.trim())
  }

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}`
  }

  return 'ws://localhost:5173'
}
