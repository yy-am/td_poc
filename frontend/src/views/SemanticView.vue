<template>
  <div class="semantic-container">
    <div class="page-header">
      <div>
        <h2>语义建模管理</h2>
        <p>管理物理表、语义模型、指标和维度的映射关系，并直接测试语义查询。</p>
      </div>
    </div>

    <el-card class="query-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>语义查询测试</span>
          <span class="card-hint">优先使用维度 / 指标名，而不是直接写 SQL</span>
        </div>
      </template>

      <div class="query-grid">
        <el-select v-model="queryForm.model_id" filterable placeholder="选择语义模型" @change="handleModelChange">
          <el-option
            v-for="model in models"
            :key="model.id"
            :label="`${model.label} (${model.source_table})`"
            :value="model.id"
          />
        </el-select>
        <el-input v-model="queryForm.dimensions" placeholder="维度，逗号分隔，例如：tax_period,taxpayer_id" clearable />
        <el-input v-model="queryForm.metrics" placeholder="指标，逗号分隔，例如：tax_payable,total_sales_amount" clearable />
        <el-input-number v-model="queryForm.limit" :min="1" :max="5000" controls-position="right" />
      </div>

      <div class="query-actions">
        <el-button type="primary" :loading="querying" @click="runQuery">执行语义查询</el-button>
        <el-button @click="resetQuery">清空</el-button>
      </div>

      <div v-if="queryResult" class="result-panel">
        <div v-if="queryResult.warnings?.length" class="warning-list">
          <el-alert
            v-for="warning in queryResult.warnings"
            :key="warning"
            :title="warning"
            type="warning"
            show-icon
            :closable="false"
          />
        </div>

        <div class="result-meta">
          <span>模型：{{ queryResult.model_label }}</span>
          <span>行数：{{ queryResult.row_count }}</span>
          <span>维度：{{ queryResult.selected_dimensions.join(', ') || '自动选择' }}</span>
          <span>指标：{{ queryResult.selected_metrics.join(', ') || '自动选择' }}</span>
        </div>

        <div v-if="queryResult.rows?.length" class="table-wrap">
          <el-table :data="queryResult.rows" size="small" stripe max-height="420" class="dark-table">
            <el-table-column
              v-for="column in queryResult.columns"
              :key="column"
              :prop="column"
              :label="column"
              min-width="140"
              show-overflow-tooltip
            />
          </el-table>
        </div>

        <div class="sql-box">
          <div class="section-title">生成的 SQL</div>
          <pre>{{ queryResult.sql }}</pre>
        </div>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" class="dark-tabs">
      <el-tab-pane label="物理模型" name="physical">
        <div class="model-grid">
          <div v-for="m in physicalModels" :key="m.id" class="model-card" @click="openDetail(m)">
            <div class="model-card-header">
              <el-icon color="#409eff"><Coin /></el-icon>
              <span class="model-name">{{ m.label }}</span>
            </div>
            <div class="model-meta">
              <el-tag size="small" type="info">{{ m.source_table }}</el-tag>
              <el-tag size="small" :type="m.status === 'active' ? 'success' : 'warning'">{{ m.status }}</el-tag>
            </div>
            <p class="model-desc">{{ m.description }}</p>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="语义模型" name="semantic">
        <div class="model-grid">
          <div v-for="m in semanticModels" :key="m.id" class="model-card" @click="openDetail(m)">
            <div class="model-card-header">
              <el-icon color="#67c23a"><Connection /></el-icon>
              <span class="model-name">{{ m.label }}</span>
            </div>
            <div class="model-meta">
              <el-tag size="small" type="success">语义层</el-tag>
              <el-tag size="small" type="info">{{ m.source_table }}</el-tag>
            </div>
            <p class="model-desc">{{ m.description }}</p>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="指标模型" name="metric">
        <div class="model-grid">
          <div v-for="m in metricModels" :key="m.id" class="model-card" @click="openDetail(m)">
            <div class="model-card-header">
              <el-icon color="#e6a23c"><TrendCharts /></el-icon>
              <span class="model-name">{{ m.label }}</span>
            </div>
            <div class="model-meta">
              <el-tag size="small" type="warning">指标</el-tag>
            </div>
            <p class="model-desc">{{ m.description }}</p>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="detailVisible" :title="selectedModel?.label || '模型详情'" size="520px" class="dark-drawer">
      <template v-if="selectedModel">
        <el-descriptions :column="1" border class="dark-desc">
          <el-descriptions-item label="标识">{{ selectedModel.name }}</el-descriptions-item>
          <el-descriptions-item label="源表">{{ selectedModel.source_table }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ selectedModel.model_type }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedModel.status }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="drawer-title">表结构</h4>
        <el-table :data="tableColumns" size="small" stripe max-height="420" class="dark-table">
          <el-table-column prop="column_name" label="字段" width="160" />
          <el-table-column prop="data_type" label="类型" width="120" />
          <el-table-column prop="comment" label="注释" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getApiBase } from '../config/runtime'
import type { SemanticModel } from '../types/agent'

const API = getApiBase()

const models = ref<SemanticModel[]>([])
const activeTab = ref('physical')
const detailVisible = ref(false)
const selectedModel = ref<SemanticModel | null>(null)
const tableColumns = ref<any[]>([])
const querying = ref(false)
const queryResult = ref<any | null>(null)

const queryForm = ref({
  model_id: null as number | null,
  dimensions: '',
  metrics: '',
  limit: 100,
})

const physicalModels = computed(() => models.value.filter(m => m.model_type === 'physical'))
const semanticModels = computed(() => models.value.filter(m => m.model_type === 'semantic'))
const metricModels = computed(() => models.value.filter(m => m.model_type === 'metric'))

onMounted(async () => {
  await loadModels()
  if (models.value.length > 0) {
    queryForm.value.model_id = models.value[0].id
    await loadSchema(models.value[0])
  }
})

async function loadModels() {
  const { data } = await axios.get(`${API}/semantic/models`)
  models.value = data
}

async function loadSchema(model: SemanticModel) {
  try {
    const { data } = await axios.get(`${API}/datasource/tables/${model.source_table}/schema`)
    tableColumns.value = data.columns || []
  } catch {
    tableColumns.value = []
  }
}

async function openDetail(model: SemanticModel) {
  selectedModel.value = model
  detailVisible.value = true
  queryForm.value.model_id = model.id
  await loadSchema(model)
}

async function handleModelChange(modelId: number | null) {
  const model = models.value.find(item => item.id === modelId)
  if (model) {
    await loadSchema(model)
  }
}

async function runQuery() {
  if (!queryForm.value.model_id) {
    ElMessage.warning('请选择一个语义模型')
    return
  }

  querying.value = true
  try {
    const payload = {
      model_id: queryForm.value.model_id,
      dimensions: splitTokens(queryForm.value.dimensions),
      metrics: splitTokens(queryForm.value.metrics),
      limit: queryForm.value.limit,
    }
    const { data } = await axios.post(`${API}/semantic/query`, payload)
    queryResult.value = data
  } catch (error: any) {
    const detail = error?.response?.data?.detail || error?.message || '语义查询失败'
    ElMessage.error(detail)
  } finally {
    querying.value = false
  }
}

function resetQuery() {
  queryForm.value.dimensions = ''
  queryForm.value.metrics = ''
  queryForm.value.limit = 100
  queryResult.value = null
}

function splitTokens(value: string): string[] {
  return value
    .split(',')
    .map(token => token.trim())
    .filter(Boolean)
}
</script>

<style scoped>
.semantic-container {
  padding: 24px 32px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  font-size: 22px;
  color: #e0e0e0;
  margin-bottom: 6px;
}

.page-header p {
  color: #888;
  font-size: 14px;
}

.query-card,
.model-card,
.dark-drawer :deep(.el-drawer__body) {
  background: #16213e;
  border: 1px solid #2a2a4a;
}

.query-card {
  margin-bottom: 20px;
  border-radius: 14px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  color: #eef3ff;
}

.card-hint {
  color: #8fa5c9;
  font-size: 12px;
}

.query-grid {
  display: grid;
  grid-template-columns: 1.3fr 1.2fr 1.2fr 160px;
  gap: 12px;
}

.query-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}

.result-panel {
  margin-top: 16px;
  display: grid;
  gap: 14px;
}

.warning-list {
  display: grid;
  gap: 8px;
}

.result-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  color: #b8c7e6;
  font-size: 13px;
}

.table-wrap {
  overflow: hidden;
  border-radius: 12px;
}

.sql-box {
  border-radius: 12px;
  background: rgba(7, 12, 22, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.06);
  padding: 12px 14px;
}

.section-title {
  color: #9fd7ff;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.sql-box pre {
  margin: 0;
  color: #dce7fb;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  padding: 16px 0;
}

.model-card {
  border-radius: 12px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.2s;
}

.model-card:hover {
  border-color: #409eff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
}

.model-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.model-name {
  font-size: 15px;
  font-weight: 600;
  color: #e0e0e0;
}

.model-meta {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.model-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
}

.drawer-title {
  margin: 20px 0 10px;
  color: #e0e0e0;
}

:deep(.el-tabs__item) {
  color: #a0a0a0;
}

:deep(.el-tabs__item.is-active) {
  color: #409eff;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper),
:deep(.el-input-number__decrease),
:deep(.el-input-number__increase) {
  background: #0f1728 !important;
  border-color: #2a2a4a !important;
  box-shadow: none !important;
}

:deep(.el-input__inner),
:deep(.el-select__selected-item),
:deep(.el-input-number__inner) {
  color: #e0e0e0;
}

:deep(.el-tabs__content) {
  overflow: visible;
}

:deep(.el-drawer__header) {
  color: #f2f6ff;
}

:deep(.el-descriptions__label),
:deep(.el-descriptions__content) {
  color: #dce7fb;
}

.dark-table :deep(.el-table__header) {
  background: rgba(8, 17, 32, 0.96);
}

.dark-table :deep(.el-table__body tr) {
  background: rgba(18, 33, 26, 0.95);
}
</style>
