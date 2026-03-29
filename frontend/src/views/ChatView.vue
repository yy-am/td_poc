<template>
  <div class="chat-container">
    <aside class="session-panel">
      <el-button type="primary" class="new-chat-btn" @click="newSession">
        <el-icon><Plus /></el-icon>
        新建对话
      </el-button>

      <el-input
        v-model="searchTerm"
        class="session-search"
        placeholder="搜索会话标题"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <div class="session-list">
        <div
          v-for="session in visibleSessions"
          :key="session.session_id"
          :class="['session-item', { active: session.session_id === chatStore.currentSession }]"
          @click="selectSession(session.session_id)"
        >
          <el-icon class="session-icon"><ChatDotRound /></el-icon>
          <div class="session-body">
            <div class="session-title-row">
              <span class="session-title">{{ session.title }}</span>
              <span class="session-time">{{ formatSessionTime(session.updated_at) }}</span>
            </div>
            <div class="session-subtitle">{{ session.session_id }}</div>
          </div>
          <div class="session-actions">
            <el-icon class="session-action" @click.stop="openRenameDialog(session)"><EditPen /></el-icon>
            <el-icon class="session-action danger" @click.stop="handleDeleteSession(session.session_id)"><Delete /></el-icon>
          </div>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="message-stream">
        <div v-if="initError" class="socket-error-banner">
          {{ initError }}
        </div>

        <div v-if="chatStore.messages.length === 0" class="welcome">
          <h2>智税通 - 语义化智能问数</h2>
          <p>我可以帮您分析税务数据、账务数据，以及两者之间的差异。</p>
          <div class="quick-queries">
            <div class="quick-card" v-for="q in quickQueries" :key="q" @click="sendMessage(q)">
              {{ q }}
            </div>
          </div>
        </div>

        <template v-for="msg in chatStore.messages" :key="msg.id">
          <div v-if="msg.role === 'user'" class="message user-message">
            <div class="message-content user-bubble">{{ msg.content }}</div>
          </div>

          <div v-else class="message assistant-message">
            <MultiAgentBoard v-if="msg.steps?.length" :steps="msg.steps" />
            <div v-else class="assistant-bubble">{{ msg.content }}</div>
          </div>
        </template>

        <div v-if="isThinking" class="message assistant-message">
          <MultiAgentBoard :steps="socket.steps.value" :is-streaming="true" />
        </div>

        <div v-if="socketError" class="socket-error-banner">
          {{ socketError }}
        </div>
      </div>

      <div class="input-area">
        <div class="input-wrapper">
          <el-input
            v-model="inputText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="请输入您的问题，例如：分析华兴科技2024年Q3的税账差异"
            @keydown.enter.exact="handleEnter"
            :disabled="isThinking"
          />
          <el-button
            type="primary"
            circle
            :icon="isThinking ? 'Loading' : 'Promotion'"
            :loading="isThinking"
            @click="handleSend"
            class="send-btn"
          />
        </div>
      </div>
    </main>
  </div>

  <el-dialog v-model="renameDialogVisible" title="重命名会话" width="420px">
    <el-input v-model="renameTitle" maxlength="80" show-word-limit placeholder="输入新的会话标题" />
    <template #footer>
      <el-button @click="renameDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="renaming" @click="confirmRename">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useChatStore } from '../stores/chat'
import { useWebSocket } from '../composables/useWebSocket'
import MultiAgentBoard from '../components/chat/MultiAgentBoardClean.vue'
import type { Session } from '../types/agent'

const chatStore = useChatStore()
const socket = useWebSocket('')
const isThinking = socket.isThinking
const socketError = socket.error
const inputText = ref('')
const searchTerm = ref('')
const initError = ref('')
const renameDialogVisible = ref(false)
const renameTitle = ref('')
const renameTarget = ref<Session | null>(null)
const renaming = ref(false)

const quickQueries = [
  '分析华兴科技2024年Q3增值税申报收入与会计账面的差异',
  '哪家企业的增值税税负率最低？存在什么风险？',
  '对比所有企业2024年的纳税调整情况',
  '查看链龙商贸的税务风险指标预警',
]

const visibleSessions = computed(() => {
  const keyword = searchTerm.value.trim().toLowerCase()
  if (!keyword) return chatStore.sessions
  return chatStore.sessions.filter(session => {
    return [session.title, session.session_id, session.status].some(value => value?.toLowerCase().includes(keyword))
  })
})

onMounted(async () => {
  initError.value = ''

  try {
    await chatStore.loadSessions()
    const fallbackSessionId = chatStore.currentSession || chatStore.sessions[0]?.session_id
    if (fallbackSessionId) {
      try {
        await selectSession(fallbackSessionId)
        return
      } catch {
        // fall through and create a fresh session
      }
    }

    const sid = await chatStore.createSession()
    await selectSession(sid)
  } catch (error: any) {
    initError.value = error?.response?.data?.detail || error?.message || '聊天初始化失败，请检查前端代理或后端服务'
  }
})

async function selectSession(sessionId: string) {
  initError.value = ''
  socket.setSession(sessionId)
  await chatStore.loadMessages(sessionId)
  socket.connect(sessionId)
}

async function newSession() {
  const sid = await chatStore.createSession()
  await selectSession(sid)
}

async function handleDeleteSession(sessionId: string) {
  const wasCurrent = chatStore.currentSession === sessionId
  await chatStore.deleteSession(sessionId)

  if (!wasCurrent) return

  if (chatStore.sessions.length > 0) {
    await selectSession(chatStore.sessions[0].session_id)
    return
  }

  const sid = await chatStore.createSession()
  await selectSession(sid)
}

function openRenameDialog(session: Session) {
  renameTarget.value = session
  renameTitle.value = session.title
  renameDialogVisible.value = true
}

async function confirmRename() {
  const target = renameTarget.value
  const title = renameTitle.value.trim()
  if (!target || !title || renaming.value) return

  renaming.value = true
  try {
    await chatStore.renameSession(target.session_id, title)
    await chatStore.loadSessions()
    renameDialogVisible.value = false
  } finally {
    renaming.value = false
  }
}

function handleEnter(e: KeyboardEvent) {
  if (!e.shiftKey) {
    e.preventDefault()
    void handleSend()
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || socket.isThinking.value) return

  if (!chatStore.currentSession) {
    const sid = await chatStore.createSession()
    await selectSession(sid)
  }

  await sendMessage(text)
}

async function sendMessage(text: string) {
  inputText.value = ''
  chatStore.addUserMessage(text)
  socket.send(text)
}

watch(socket.isThinking, (val) => {
  if (!val && socket.steps.value.length > 0) {
    chatStore.addAssistantMessage([...socket.steps.value])
  }
})

function formatSessionTime(iso: string) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.chat-container {
  display: flex;
  height: 100vh;
  background: #0f0f23;
}

.session-panel {
  width: 280px;
  background: #16213e;
  border-right: 1px solid #2a2a4a;
  display: flex;
  flex-direction: column;
  padding: 12px;
  gap: 12px;
}

.new-chat-btn {
  width: 100%;
}

.session-search {
  width: 100%;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  display: grid;
  gap: 8px;
}

.session-item {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  padding: 12px;
  border-radius: 12px;
  cursor: pointer;
  color: #a0a0a0;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.02);
}

.session-item:hover {
  background: #1e3a5f;
  color: #e0e0e0;
}

.session-item.active {
  background: rgba(64, 158, 255, 0.16);
  color: #e8f2ff;
  box-shadow: inset 0 0 0 1px rgba(64, 158, 255, 0.28);
}

.session-icon {
  margin-top: 2px;
}

.session-body {
  min-width: 0;
}

.session-title-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.session-title {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  flex-shrink: 0;
  font-size: 11px;
  color: #8fa5c9;
}

.session-subtitle {
  margin-top: 4px;
  font-size: 11px;
  color: #7f8caa;
}

.session-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.session-action {
  color: #96a9cc;
}

.session-action:hover {
  color: #d7e4ff;
}

.session-action.danger:hover {
  color: #ff9a9a;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.message-stream {
  flex: 1;
  overflow-y: auto;
  padding: 24px 48px;
}

.welcome {
  text-align: center;
  padding: 80px 0 40px;
}

.welcome h2 {
  font-size: 28px;
  background: linear-gradient(135deg, #409eff, #67c23a);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 12px;
}

.welcome p {
  color: #a0a0a0;
  font-size: 15px;
  margin-bottom: 32px;
}

.quick-queries {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-width: 700px;
  margin: 0 auto;
}

.quick-card {
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  color: #c0c0c0;
  font-size: 13px;
  transition: all 0.2s;
  text-align: left;
}

.quick-card:hover {
  border-color: #409eff;
  background: #1e3a5f;
  color: #e0e0e0;
}

.message {
  margin-bottom: 20px;
}

.socket-error-banner {
  margin: 0 auto 20px;
  max-width: 900px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(245, 108, 108, 0.35);
  background: rgba(245, 108, 108, 0.12);
  color: #ffd2d2;
  font-size: 13px;
}

.user-message {
  display: flex;
  justify-content: flex-end;
}

.user-bubble,
.assistant-bubble {
  max-width: min(880px, 72%);
  border-radius: 18px;
  padding: 12px 18px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble {
  background: #409eff;
  color: white;
  border-radius: 18px 18px 4px 18px;
}

.assistant-bubble {
  background: rgba(22, 33, 62, 0.92);
  border: 1px solid #2a2a4a;
  color: #e0e0e0;
}

.input-area {
  padding: 16px 48px 24px;
  border-top: 1px solid #2a2a4a;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  max-width: 900px;
  margin: 0 auto;
}

.input-wrapper :deep(.el-textarea__inner) {
  background: #16213e;
  border: 1px solid #2a2a4a;
  color: #e0e0e0;
  border-radius: 12px;
  padding: 12px 16px;
  resize: none;
}

.input-wrapper :deep(.el-textarea__inner:focus) {
  border-color: #409eff;
}

.send-btn {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
}

:deep(.el-dialog) {
  background: #16213e;
  border: 1px solid #2a2a4a;
}

:deep(.el-dialog__title) {
  color: #f2f6ff;
}
</style>
