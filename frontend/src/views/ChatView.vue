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

        <template v-for="(msg, index) in chatStore.messages" :key="msg.id">
          <div v-if="msg.role === 'user'" class="message user-message">
            <div class="message-content user-bubble">{{ msg.content }}</div>
          </div>

          <div v-else class="message assistant-message">
            <MultiAgentBoard
              v-if="msg.steps?.length"
              :steps="msg.steps"
              :question-text="getRelatedUserPrompt(index)"
            />
            <div v-else class="assistant-bubble">{{ msg.content }}</div>
          </div>
        </template>

        <div v-if="isThinking" class="message assistant-message">
          <MultiAgentBoard
            :steps="socket.steps.value"
            :is-streaming="true"
            :question-text="latestUserPrompt"
          />
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
import MultiAgentBoard from '../components/chat/MultiAgentBoardRefresh.vue'
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

const latestUserPrompt = computed(() => {
  for (let i = chatStore.messages.length - 1; i >= 0; i -= 1) {
    const message = chatStore.messages[i]
    if (message.role === 'user' && message.content.trim()) {
      return message.content
    }
  }
  return ''
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

function getRelatedUserPrompt(index: number) {
  for (let i = index - 1; i >= 0; i -= 1) {
    const message = chatStore.messages[i]
    if (message.role === 'user' && message.content.trim()) {
      return message.content
    }
  }
  return latestUserPrompt.value
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
  height: 100%;
  min-height: 0;
  background: transparent;
}

.session-panel {
  width: 280px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(244, 249, 255, 0.76)),
    radial-gradient(circle at top left, rgba(127, 215, 255, 0.14), transparent 24%);
  border-right: 1px solid rgba(89, 114, 145, 0.14);
  display: flex;
  flex-direction: column;
  padding: 18px 16px;
  gap: 14px;
  backdrop-filter: blur(18px);
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
  gap: 10px;
}

.session-item {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  padding: 14px;
  border-radius: 18px;
  cursor: pointer;
  color: var(--ink-soft);
  transition: all 0.2s ease;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(89, 114, 145, 0.1);
  box-shadow: 0 10px 24px rgba(38, 63, 95, 0.05);
}

.session-item:hover {
  background: rgba(244, 249, 255, 0.96);
  color: var(--ink);
  border-color: rgba(79, 135, 255, 0.18);
  transform: translateY(-1px);
}

.session-item.active {
  background: rgba(240, 247, 255, 0.96);
  color: var(--ink-strong);
  border-color: rgba(79, 135, 255, 0.22);
  box-shadow:
    inset 0 0 0 1px rgba(79, 135, 255, 0.12),
    0 14px 28px rgba(79, 135, 255, 0.08);
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
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--ink-soft);
}

.session-subtitle {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(102, 120, 141, 0.82);
}

.session-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.session-action {
  color: rgba(102, 120, 141, 0.82);
}

.session-action:hover {
  color: var(--accent-blue);
}

.session-action.danger:hover {
  color: var(--accent-red);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.message-stream {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 30px 20px;
}

.welcome {
  text-align: center;
  max-width: 980px;
  margin: 0 auto;
  padding: 54px 20px 34px;
  border-radius: 32px;
  border: 1px solid rgba(89, 114, 145, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(247, 251, 255, 0.82)),
    radial-gradient(circle at top center, rgba(127, 215, 255, 0.16), transparent 26%);
  box-shadow: var(--shadow-panel);
}

.welcome h2 {
  font-size: 34px;
  background: linear-gradient(135deg, #4f87ff, #6dd8c2);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 12px;
  letter-spacing: -0.05em;
}

.welcome p {
  color: var(--ink-soft);
  font-size: 15px;
  margin-bottom: 26px;
}

.quick-queries {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  max-width: 700px;
  margin: 0 auto;
}

.quick-card {
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(89, 114, 145, 0.12);
  border-radius: 18px;
  padding: 18px;
  cursor: pointer;
  color: var(--ink);
  font-size: 13px;
  transition: all 0.2s ease;
  text-align: left;
  box-shadow: 0 10px 24px rgba(38, 63, 95, 0.06);
}

.quick-card:hover {
  border-color: rgba(79, 135, 255, 0.22);
  background: rgba(243, 249, 255, 0.98);
  color: var(--ink-strong);
  transform: translateY(-1px);
}

.message {
  margin-bottom: 22px;
}

.socket-error-banner {
  margin: 0 auto 20px;
  max-width: 1100px;
  padding: 12px 16px;
  border-radius: 16px;
  border: 1px solid rgba(227, 107, 115, 0.26);
  background: rgba(255, 240, 242, 0.88);
  color: #b04754;
  font-size: 13px;
}

.user-message {
  display: flex;
  justify-content: flex-end;
}

.user-bubble,
.assistant-bubble {
  max-width: min(1080px, 86%);
  border-radius: 22px;
  padding: 14px 18px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.user-bubble {
  background: linear-gradient(135deg, #5e95ff, #7fd7ff);
  color: white;
  border-radius: 22px 22px 8px 22px;
  box-shadow: 0 16px 30px rgba(79, 135, 255, 0.18);
}

.assistant-bubble {
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(89, 114, 145, 0.12);
  color: var(--ink);
  box-shadow: 0 12px 26px rgba(38, 63, 95, 0.06);
}

.input-area {
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  z-index: 8;
  padding: 18px 30px 28px;
  border-top: 1px solid rgba(89, 114, 145, 0.12);
  background: linear-gradient(180deg, rgba(246, 250, 255, 0.2), rgba(246, 250, 255, 0.72));
  backdrop-filter: blur(18px);
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  max-width: 1100px;
  margin: 0 auto;
  padding: 10px;
  border-radius: 24px;
  border: 1px solid rgba(89, 114, 145, 0.12);
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 14px 28px rgba(38, 63, 95, 0.07);
}

.input-wrapper :deep(.el-textarea__inner) {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(89, 114, 145, 0.12);
  color: var(--ink-strong);
  border-radius: 18px;
  padding: 12px 16px;
  resize: none;
  box-shadow: none;
}

.input-wrapper :deep(.el-textarea__inner:focus) {
  border-color: rgba(79, 135, 255, 0.28);
}

.send-btn {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  box-shadow: 0 12px 24px rgba(79, 135, 255, 0.18);
}

:deep(.el-dialog) {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(89, 114, 145, 0.12);
  border-radius: 24px;
}

:deep(.el-dialog__title) {
  color: var(--ink-strong);
}

@media (max-width: 1120px) {
  .chat-container {
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }

  .session-panel {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid rgba(89, 114, 145, 0.12);
    max-height: 300px;
    min-height: 180px;
  }

  .session-list {
    min-height: 0;
  }

  .chat-main {
    min-height: 0;
  }

  .quick-queries {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .message-stream,
  .input-area {
    padding-left: 16px;
    padding-right: 16px;
  }

  .user-bubble,
  .assistant-bubble {
    max-width: 100%;
  }
}
</style>
