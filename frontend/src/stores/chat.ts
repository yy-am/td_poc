import axios from 'axios'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getApiBase } from '../config/runtime'
import type { AgentStep, ChatMessage, Session, SessionMessageRecord } from '../types/agent'

const API = getApiBase()

function mapConversationMessage(record: SessionMessageRecord): ChatMessage {
  const base: ChatMessage = {
    id: record.id.toString(),
    role: record.role === 'assistant' ? 'assistant' : 'user',
    content: record.content,
    timestamp: record.created_at,
    metadata: record.metadata || undefined,
  }

  if (record.role === 'assistant' && record.metadata?.steps) {
    base.steps = record.metadata.steps as AgentStep[]
  }

  return base
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>([])
  const currentSession = ref<string>('')
  const messages = ref<ChatMessage[]>([])

  async function loadSessions() {
    const { data } = await axios.get(`${API}/sessions`)
    sessions.value = data
  }

  async function loadMessages(sessionId: string) {
    const { data } = await axios.get(`${API}/sessions/${sessionId}/messages`)
    messages.value = data.map(mapConversationMessage)
    currentSession.value = sessionId
    return messages.value
  }

  async function createSession(title?: string) {
    const { data } = await axios.post(`${API}/sessions`, { title: title || '新会话' })
    sessions.value = [data, ...sessions.value.filter(s => s.session_id !== data.session_id)]
    currentSession.value = data.session_id
    messages.value = []
    return data.session_id
  }

  async function renameSession(sessionId: string, title: string) {
    const { data } = await axios.patch(`${API}/sessions/${sessionId}`, { title })
    sessions.value = sessions.value.map(session => session.session_id === sessionId ? data : session)
    return data
  }

  async function deleteSession(sessionId: string) {
    await axios.delete(`${API}/sessions/${sessionId}`)
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    if (currentSession.value === sessionId) {
      currentSession.value = ''
      messages.value = []
    }
  }

  function addUserMessage(content: string) {
    messages.value.push({
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    })
  }

  function addAssistantMessage(steps: AgentStep[]) {
    const answerStep = [...steps].reverse().find(step => step.type === 'answer')
    messages.value.push({
      id: Date.now().toString(),
      role: 'assistant',
      content: answerStep?.content || '',
      steps,
      timestamp: new Date().toISOString(),
    })
  }

  return {
    sessions,
    currentSession,
    messages,
    loadSessions,
    loadMessages,
    createSession,
    renameSession,
    deleteSession,
    addUserMessage,
    addAssistantMessage,
  }
})
