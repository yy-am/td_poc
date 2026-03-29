<template>
  <div class="settings-container">
    <div class="page-header">
      <h2>系统设置</h2>
    </div>

    <el-card class="dark-card" shadow="never">
      <template #header>
        <span>大模型配置</span>
      </template>
      <el-form label-width="120px">
        <el-form-item label="API Base URL">
          <el-input v-model="llmConfig.baseUrl" placeholder="https://jeniya.cn/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="llmConfig.apiKey" type="password" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-select v-model="llmConfig.model">
            <el-option label="DeepSeek V3.2" value="deepseek-v3.2" />
            <el-option label="GPT-4o" value="gpt-4o" />
            <el-option label="GLM-4" value="glm-4" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="dark-card" shadow="never" style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>Mock数据管理</span>
          <el-button type="warning" @click="generateMock" :loading="generating">
            重新生成Mock数据
          </el-button>
        </div>
      </template>
      <p style="color: #a0a0a0; font-size: 14px">
        点击按钮将清空所有业务数据并重新生成28张表约29000+行Mock数据。
        包含10家企业、24个月数据，以及故意设置的税务-会计差异。
      </p>
      <el-alert v-if="mockResult" :title="mockResult" type="success" style="margin-top: 12px" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import axios from 'axios'
import { getApiBase } from '../config/runtime'

const API = getApiBase()

const llmConfig = reactive({
  baseUrl: 'https://jeniya.cn/v1',
  apiKey: '',
  model: 'deepseek-v3.2',
})

const generating = ref(false)
const mockResult = ref('')

async function generateMock() {
  generating.value = true
  mockResult.value = ''
  try {
    const { data } = await axios.post(`${API}/mock/generate`)
    mockResult.value = data.message || '数据生成成功'
  } catch (e: any) {
    mockResult.value = '生成失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.settings-container {
  padding: 24px 32px;
  max-width: 800px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 22px;
  color: #e0e0e0;
}

.dark-card {
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
}

.dark-card :deep(.el-card__header) {
  border-bottom: 1px solid #2a2a4a;
  color: #e0e0e0;
  font-weight: 600;
}

.dark-card :deep(.el-input__inner) {
  background: #0f0f23;
  border-color: #2a2a4a;
  color: #e0e0e0;
}

.dark-card :deep(.el-form-item__label) {
  color: #a0a0a0;
}
</style>
