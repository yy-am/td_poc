import { ref, onUnmounted } from 'vue'
import { getWebSocketBase } from '../config/runtime'
import type { AgentStep } from '../types/agent'

const API_BASE = getWebSocketBase()

export function useWebSocket(initialSessionId: string) {
  const sessionId = ref(initialSessionId)
  const ws = ref<WebSocket | null>(null)
  const steps = ref<AgentStep[]>([])
  const isThinking = ref(false)
  const isConnected = ref(false)
  const error = ref<string | null>(null)
  const pendingMessage = ref<string | null>(null)

  function disconnect() {
    ws.value?.close()
    ws.value = null
    isConnected.value = false
    isThinking.value = false
  }

  function connect(nextSessionId?: string) {
    if (nextSessionId) {
      sessionId.value = nextSessionId
    }

    if (!sessionId.value) return
    if (ws.value?.readyState === WebSocket.OPEN) return

    if (ws.value && ws.value.readyState !== WebSocket.CLOSED) {
      disconnect()
    }

    ws.value = new WebSocket(`${API_BASE}/ws/chat/${sessionId.value}`)

    ws.value.onopen = () => {
      isConnected.value = true
      error.value = null
      if (pendingMessage.value) {
        const message = pendingMessage.value
        pendingMessage.value = null
        steps.value = []
        isThinking.value = true
        ws.value?.send(JSON.stringify({ content: message }))
      }
    }

    ws.value.onmessage = (event: MessageEvent) => {
      try {
        const step: AgentStep = JSON.parse(event.data)
        steps.value.push(step)
        isThinking.value = !step.is_final
      } catch (e) {
        console.error('消息解析失败:', e)
      }
    }

    ws.value.onclose = () => {
      isConnected.value = false
      if (pendingMessage.value) {
        pendingMessage.value = null
        error.value = '连接中断，消息未成功发送'
      }
      isThinking.value = false
    }

    ws.value.onerror = () => {
      error.value = '连接失败，请检查后端服务'
      isConnected.value = false
      pendingMessage.value = null
      isThinking.value = false
    }
  }

  function setSession(nextSessionId: string) {
    if (sessionId.value === nextSessionId) {
      return
    }
    sessionId.value = nextSessionId
    steps.value = []
    isThinking.value = false
    pendingMessage.value = null
    disconnect()
  }

  function send(message: string) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
      pendingMessage.value = message
      steps.value = []
      isThinking.value = true
      connect()
      return
    }
    pendingMessage.value = null
    steps.value = []
    isThinking.value = true
    ws.value.send(JSON.stringify({ content: message }))
  }

  onUnmounted(() => {
    disconnect()
  })

  return { sessionId, steps, isThinking, isConnected, error, connect, send, disconnect, setSession }
}
