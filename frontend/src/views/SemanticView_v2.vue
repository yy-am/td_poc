<template>
  <div class="semantic-container">
    <div class="page-header">
      <h2>语义建模管理</h2>
      <p>管理物理表、语义模型、指标和维度映射关系，并直接测试语义查询。</p>
    </div>

    <el-card class="query-card" shadow="never">
      <template #header>
        <div class="query-card-header">
          <span>语义查询测试</span>
          <el-tag size="small" type="success">POST /api/v1/semantic/query</el-tag>
        </div>
      </template>

      <div class="query-grid">
        <el-select v-model="queryModelName" placeholder="选择模型" filterable>
          <el-option
            v-for="m in queryableModels"
            :key="m.name"
            :label="`${m.label} (${m.name})`"
            :value="m.name"
          />
        </el-select>
        <el-input v-model="queryDimensionsText" placeholder="维度, 逗号分隔，例如 tax_period,taxpayer_id" />
        <el-input v-model="queryMetricsText" placeholder="指标, 逗号分隔，例如 tax_payable,total_sales_amount" />
        <el-input v-model="queryLimitText" placeholder="limit" />
      </div>

      <div class="query-grid query-grid-wide">
        <el-input
          v-model="queryFiltersText"
          type="textarea"
          :rows="2"
          placeholder='filters JSON，例如 [{"field":"tax_period","op":"between","value":["2024-01","2024-12"]}]'
        />
        <el-input
          v-model="queryOrderText"
          type="textarea"
          :rows="2"
          placeholder='order JSON，例如 [{"field":"tax_payable","direction":"desc"}]'
        />
      </div>

      <div class="query-actions">
        <el-button type="primary" :loading="queryLoading" @click="runSemanticQuery">执行测试</el-button>
        <span v-if="queryError" class="query-error">{{ queryError }}</span>
      </div>

      <div v-if="queryResult" class="query-result">
        <div class="query-summary">
          <span>结果行数: {{ queryResult.row_count }}</span>
          <span>模型: {{ queryResult.model_label }}</span>
          <span v-if="queryResult.warnings.length">提示: {{ queryResult.warnings.join('；') }}</span>
        </div>
        <pre class="sql-preview">{{ queryResult.sql }}</pre>
        <el-table :data="queryResult.rows" size="small" stripe max-height="360" class="dark-table">
          <el-table-column
            v-for="col in queryResult.columns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="140"
          />
        </el-table>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" class="dark-tabs">
      <el-tab-pane label="物理模型" name="physical">
        <div class="model-grid">
          <div v-for="m in physicalModels" :key="m.id" class="model-card" @click="showDetail(m)">
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
          <div v-for="m in semanticModels" :key="m.id" class="model-card" @click="showDetail(m)">
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
          <div v-for="m in metricModels" :key="m.id" class="model-card" @click="showDetail(m)">
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

    <el-drawer v-model="detailVisible" :title="selectedModel?.label" size="520px">
      <template v-if="selectedModel">
        <el-descriptions :column="1" border class="dark-desc">
          <el-descriptions-item label="标识">{{ selectedModel.name }}</el-descriptions-item>
          <el-descriptions-item label="源表">{{ selectedModel.source_table }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ selectedModel.model_type }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedModel.status }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="schema-title">表结构</h4>
        <el-table :data="tableColumns" size="small" stripe max-height="360" class="dark-table">
          <el-table-column prop="column_name" label="字段名" width="160" />
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
import { getApiBase } from '../config/runtime'
import type { SemanticModel, SemanticQueryResult } from '../types/agent'

const API = getApiBase()
const models = ref<SemanticModel[]>([])
const activeTab = ref('physical')
const detailVisible = ref(false)
const selectedModel = ref<SemanticModel | null>(null)
const tableColumns = ref<any[]>([])
const queryLoading = ref(false)
const queryError = ref('')
const queryResult = ref<SemanticQueryResult | null>(null)
const queryModelName = ref('vat_declaration')
const queryDimensionsText = ref('tax_period')
const queryMetricsText = ref('tax_payable')
const queryLimitText = ref('20')
const queryFiltersText = ref('')
const queryOrderText = ref('[{"field":"tax_payable","direction":"desc"}]')

const queryableModels = computed(() => models.value.filter(m => Boolean(m)))
const physicalModels = computed(() => models.value.filter(m => m.model_type === 'physical'))
const semanticModels = computed(() => models.value.filter(m => m.model_type === 'semantic'))
const metricModels = computed(() => models.value.filter(m => m.model_type === 'metric'))

onMounted(async () => {
  const { data } = await axios.get(`${API}/semantic/models`)
  models.value = data
  if (!models.value.find(item => item.name === queryModelName.value) && models.value.length > 0) {
    queryModelName.value = models.value[0].name
  }
})

async function showDetail(model: SemanticModel) {
  selectedModel.value = model
  detailVisible.value = true
  try {
    const { data } = await axios.get(`${API}/datasource/tables/${model.source_table}/schema`)
    tableColumns.value = data.columns || []
  } catch {
    tableColumns.value = []
  }
}

async function runSemanticQuery() {
  queryLoading.value = true
  queryError.value = ''
  queryResult.value = null
  try {
    const payload = {
      model_name: queryModelName.value,
      dimensions: parseCsv(queryDimensionsText.value),
      metrics: parseCsv(queryMetricsText.value),
      filters: parseJsonList(queryFiltersText.value),
      order: parseJsonList(queryOrderText.value),
      limit: Number.parseInt(queryLimitText.value, 10) || 20,
    }
    const { data } = await axios.post(`${API}/semantic/query`, payload)
    queryResult.value = data
  } catch (error: any) {
    queryError.value = error?.response?.data?.detail || error?.message || '查询失败'
  } finally {
    queryLoading.value = false
  }
}

function parseCsv(value: string): string[] {
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
}

function parseJsonList(value: string): any[] {
  if (!value.trim()) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}
</script>

<style scoped>
.semantic-container {
  padding: 24px 32px;
}

.page-header {
  margin-bottom: 24px;
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

.query-card {
  margin-bottom: 24px;
  background: #10182f;
  border: 1px solid #26324d;
}

.query-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.query-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.query-grid-wide {
  margin-top: 12px;
}

.query-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.query-error {
  color: #f56c6c;
  font-size: 13px;
}

.query-result {
  margin-top: 16px;
}

.query-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #cbd5e1;
  font-size: 13px;
  margin-bottom: 10px;
}

.sql-preview {
  margin: 0 0 12px;
  padding: 12px;
  border-radius: 8px;
  background: #0b1120;
  color: #a7f3d0;
  overflow: auto;
  white-space: pre-wrap;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  padding: 16px 0;
}

.model-card {
  background: #16213e;
  border: 1px solid #2a2a4a;
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

.schema-title {
  margin: 20px 0 10px;
  color: #e0e0e0;
}

:deep(.el-tabs__item) {
  color: #a0a0a0;
}

:deep(.el-tabs__item.is-active) {
  color: #409eff;
}
</style>
