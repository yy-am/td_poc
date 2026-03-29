<template>
  <div class="chat-container">
    <aside class="session-panel">
      <el-button type="primary" class="new-chat-btn" @click="newSession">新建对话</el-button>
      <el-input v-model="sessionKeyword" placeholder="搜索对话" clearable class="session-search" />
      <div class="session-list">
        <button
          v-for="session in filteredSessions"
          :key="session.session_id"
          class="session-item"
          :class="{ active: session.session_id === chatStore.currentSession }"
          type="button"
          @click="switchSession(session.session_id)"
        >
          <span class="session-title">{{ session.title || session.session_id }}</span>
          <span class="session-time">{{ formatTime(session.created_at) }}</span>
        </button>
      </div>
    </aside>

    <main class="chat-main">
      <section class="message-stream">
        <div v-if="chatStore.messages.length === 0 && !isThinking" class="welcome">
          <h2>真正的 Agentic 分析助手</h2>
          <p>先给出计划全景图，再根据真实工具调用和证据更新计划。</p>
          <div class="quick-queries">
            <button v-for="query in quickQueries" :key="query" class="quick-card" type="button" @click="sendMessage(query)">
              {{ query }}
            </button>
          </div>
        </div>

        <template v-for="message in chatStore.messages" :key="message.id">
          <div v-if="message.role === 'user'" class="message user-message">
            <div class="user-bubble">{{ message.content }}</div>
          </div>
          <div v-else class="message assistant-message">
            <AgentPlanGraphBoard v-if="message.steps?.length" :steps="message.steps" />
            <div v-else class="assistant-fallback">{{ message.content }}</div>
          </div>
        </template>

        <div v-if="isThinking" class="message assistant-message">
          <AgentPlanGraphBoard :steps="currentSteps" :is-streaming="true" />
        </div>
      </section>

      <footer class="input-area">
        <div class="input-wrapper">
          <el-input
            v-model="inputText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 5 }"
            placeholder="输入你的问题，例如：分析某企业 2024 年 Q3 的增值税申报与账务收入差异"
            :disabled="isThinking"
            @keydown.enter.exact="handleEnter"
          />
          <el-button type="primary" class="send-btn" :loading="isThinking" @click="handleSend">发送</el-button>
        </div>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AgentPlanGraphBoard from '../components/chat/AgentPlanGraphBoard.vue'
import { useWebSocket } from '../composables/useWebSocket'
import { useChatStore } from '../stores/chat'
import type { AgentStep } from '../types/agent'

const chatStore = useChatStore()
const inputText = ref('')
const sessionKeyword = ref('')

const quickQueries = [
  '分析华兴科技 2024 年 Q3 增值税申报收入与账务收入的差异',
  '查看当前系统里有哪些税务和账务表',
  '比较所有企业 2024 年的企业所得税调整情况',
  '哪些企业的税负率明显偏低，并说明可能风险',
]

const filteredSessions = computed(() => {
  const keyword = sessionKeyword.value.trim().toLowerCase()
  if (!keyword) return chatStore.sessions
  return chatStore.sessions.filter(session => (session.title || '').toLowerCase().includes(keyword))
})

const socketState = ref(useWebSocket(chatStore.currentSession || 'default'))
const currentSteps = computed<AgentStep[]>(() => socketState.value.steps)
const isThinking = computed<boolean>(() => socketState.value.isThinking)

onMounted(async () => {
  await chatStore.loadSessions()
  if (!chatStore.currentSession) {
    const sessionId = await chatStore.createSession()
    await activateSession(sessionId)
    return
  }
  await activateSession(chatStore.currentSession)
})

watch(() => socketState.value.isThinking, (value, previousValue) => {
  if (!value && previousValue && socketState.value.steps.length > 0) {
    chatStore.addAssistantMessage([...socketState.value.steps])
  }
})

async function activateSession(sessionId: string) {
  socketState.value.disconnect()
  chatStore.currentSession = sessionId
  if ('loadMessages' in chatStore && typeof (chatStore as any).loadMessages === 'function') {
    await (chatStore as any).loadMessages(sessionId)
  } else {
    chatStore.messages = []
  }
  socketState.value = useWebSocket(sessionId)
  socketState.value.connect()
}

async function newSession() {
  const sessionId = await chatStore.createSession()
  await activateSession(sessionId)
}

async function switchSession(sessionId: string) {
  if (sessionId === chatStore.currentSession) return
  await activateSession(sessionId)
}

function handleEnter(event: KeyboardEvent) {
  if (event.shiftKey) return
  event.preventDefault()
  handleSend()
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text || isThinking.value) return
  sendMessage(text)
}

function sendMessage(text: string) {
  inputText.value = ''
  chatStore.addUserMessage(text)
  socketState.value.send(text)
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getMonth() + 1}/${date.getDate()}`
}
</script>

<style scoped>
.chat-container{display:flex;height:100vh;background:linear-gradient(180deg,#07111f,#0a1528)}
.session-panel{width:260px;border-right:1px solid rgba(255,255,255,.08);padding:18px 14px;background:linear-gradient(180deg,#101a2e,#0b1323);display:flex;flex-direction:column;gap:12px}
.new-chat-btn{width:100%}
.session-search :deep(.el-input__wrapper){background:rgba(255,255,255,.04);box-shadow:none;border:1px solid rgba(255,255,255,.08)}
.session-list{display:flex;flex-direction:column;gap:8px;overflow:auto;padding-right:4px}
.session-item{display:flex;justify-content:space-between;align-items:center;gap:10px;text-align:left;border:none;border-radius:14px;padding:12px;background:rgba(255,255,255,.04);color:#d7e2f7;cursor:pointer}
.session-item.active{background:rgba(84,199,255,.16);outline:1px solid rgba(84,199,255,.22)}
.session-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
.session-time{font-size:12px;color:#9db1d5}
.chat-main{flex:1;display:flex;flex-direction:column;min-width:0}
.message-stream{flex:1;overflow:auto;padding:28px 34px 18px;display:flex;flex-direction:column;gap:20px}
.welcome{text-align:center;padding:72px 0 28px}
.welcome h2{margin:0 0 12px;color:#eef4ff;font-size:32px}
.welcome p{margin:0;color:#b8c8e3;font-size:15px}
.quick-queries{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;max-width:840px;margin:28px auto 0}
.quick-card{border:none;border-radius:16px;padding:18px;background:rgba(255,255,255,.05);color:#d6e1f6;text-align:left;cursor:pointer;transition:.2s}
.quick-card:hover{background:rgba(84,199,255,.14)}
.message{display:flex}
.user-message{justify-content:flex-end}
.user-bubble{max-width:min(720px,74%);padding:14px 18px;border-radius:20px 20px 8px 20px;background:linear-gradient(135deg,#2f7fff,#46b0ff);color:#fff;line-height:1.8;white-space:pre-wrap}
.assistant-message{display:block}
.assistant-fallback{max-width:900px;padding:16px 18px;border-radius:18px;background:rgba(255,255,255,.05);color:#e4ecfa;line-height:1.8;white-space:pre-wrap}
.input-area{padding:18px 34px 24px;border-top:1px solid rgba(255,255,255,.08);background:rgba(8,15,27,.8);backdrop-filter:blur(10px)}
.input-wrapper{max-width:1100px;margin:0 auto;display:flex;gap:12px;align-items:flex-end}
.input-wrapper :deep(.el-textarea__inner){background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#eef4ff;border-radius:16px;padding:14px 16px;line-height:1.7;resize:none}
.send-btn{height:48px;padding:0 22px;border-radius:14px}
@media (max-width:1100px){.chat-container{flex-direction:column}.session-panel{width:auto;height:auto;border-right:none;border-bottom:1px solid rgba(255,255,255,.08)}.quick-queries{grid-template-columns:1fr}.message-stream{padding:22px 18px 14px}.input-area{padding:16px 18px 20px}}
</style>
