<template>
  <div class="semantic-container">
    <div class="page-header">
      <h2>语义建模管理</h2>
      <p>按实体维度、原子事实、复合分析三层查看语义资产，并直接测试 semantic-first 查询。</p>
    </div>

    <el-card class="query-card" shadow="never">
      <template #header>
        <div class="query-card-header">
          <span>语义查询测试</span>
          <el-tag size="small" type="success">POST /api/v1/semantic/query</el-tag>
        </div>
      </template>

      <div class="query-grid">
        <el-select v-model="queryModelName" placeholder="选择语义模型" filterable>
          <el-option
            v-for="model in queryableModels"
            :key="model.name"
            :label="`${model.label} (${model.name})`"
            :value="model.name"
          />
        </el-select>
        <el-input v-model="queryDimensionsText" placeholder="维度，逗号分隔" />
        <el-input v-model="queryMetricsText" placeholder="指标，逗号分隔" />
        <el-input v-model="queryGrainText" placeholder="粒度，例如 month / quarter / year" />
      </div>

      <div class="query-grid">
        <el-input v-model="queryLimitText" placeholder="limit" />
        <el-input
          v-model="queryEntityFiltersText"
          type="textarea"
          :rows="2"
          placeholder='entity_filters JSON，例如 {"enterprise_name":["链龙商贸"]}'
        />
        <el-input
          v-model="queryResolvedFiltersText"
          type="textarea"
          :rows="2"
          placeholder='resolved_filters JSON，例如 {"taxpayer_id":["91320100..."]}'
        />
        <el-input
          v-model="queryFiltersText"
          type="textarea"
          :rows="2"
          placeholder='filters JSON，例如 [{"field":"tax_period","op":"between","value":["2024-01","2024-12"]}]'
        />
      </div>

      <div class="query-grid query-grid-wide">
        <el-input
          v-model="queryOrderText"
          type="textarea"
          :rows="2"
          placeholder='order JSON，例如 [{"field":"warning_count","direction":"desc"}]'
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
          <span v-if="queryResult.semantic_kind">类型: {{ kindLabel(queryResult.semantic_kind) }}</span>
          <span v-if="queryResult.semantic_grain">粒度: {{ queryResult.semantic_grain }}</span>
        </div>
        <div v-if="queryResult.resolved_filters && Object.keys(queryResult.resolved_filters).length" class="query-filters">
          已解析过滤: {{ JSON.stringify(queryResult.resolved_filters) }}
        </div>
        <div v-if="queryResult.resolution_log?.length" class="query-filters">
          解析日志: {{ queryResult.resolution_log.join('；') }}
        </div>
        <div v-if="queryResult.warnings.length" class="query-filters">
          提示: {{ queryResult.warnings.join('；') }}
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
      <el-tab-pane label="实体维度" name="entity_dimension">
        <div class="model-grid">
          <div v-for="model in entityModels" :key="model.id" class="model-card" @click="showDetail(model)">
            <div class="model-card-header">
              <span class="model-name">{{ model.label }}</span>
              <el-tag size="small" type="info">{{ kindLabel(model.semantic_kind) }}</el-tag>
            </div>
            <div class="model-meta">
              <el-tag size="small" :type="model.entry_enabled ? 'success' : 'info'">
                {{ model.entry_enabled ? '可作为入口' : '辅助模型' }}
              </el-tag>
              <el-tag size="small">{{ model.source_table }}</el-tag>
            </div>
            <p class="model-desc">{{ model.description }}</p>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="原子事实" name="atomic_fact">
        <div class="model-grid">
          <div v-for="model in atomicModels" :key="model.id" class="model-card" @click="showDetail(model)">
            <div class="model-card-header">
              <span class="model-name">{{ model.label }}</span>
              <el-tag size="small" type="warning">{{ kindLabel(model.semantic_kind) }}</el-tag>
            </div>
            <div class="model-meta">
              <el-tag size="small" type="success" v-if="model.has_yaml_definition">可语义查询</el-tag>
              <el-tag size="small">{{ model.source_table }}</el-tag>
            </div>
            <p class="model-desc">{{ model.description }}</p>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="复合分析" name="composite_analysis">
        <div class="model-grid">
          <div v-for="model in compositeModels" :key="model.id" class="model-card" @click="showDetail(model)">
            <div class="model-card-header">
              <span class="model-name">{{ model.label }}</span>
              <el-tag size="small" type="success">{{ kindLabel(model.semantic_kind) }}</el-tag>
            </div>
            <div class="model-meta">
              <el-tag size="small" type="success" v-if="model.entry_enabled">主题入口</el-tag>
              <el-tag size="small">{{ model.source_count || 0 }} sources / {{ model.join_count || 0 }} joins</el-tag>
            </div>
            <p class="model-desc">{{ model.description }}</p>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="detailVisible" :title="selectedModel?.label" size="560px">
      <template v-if="selectedModel">
        <el-descriptions :column="1" border class="dark-desc">
          <el-descriptions-item label="标识">{{ selectedModel.name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ kindLabel(selectedModel.semantic_kind) }}</el-descriptions-item>
          <el-descriptions-item label="领域">{{ selectedModel.semantic_domain || '-' }}</el-descriptions-item>
          <el-descriptions-item label="粒度">{{ selectedModel.semantic_grain || '-' }}</el-descriptions-item>
          <el-descriptions-item label="源表">{{ selectedModel.source_table }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedModel.status }}</el-descriptions-item>
          <el-descriptions-item label="回退策略">{{ selectedModel.fallback_policy || '-' }}</el-descriptions-item>
          <el-descriptions-item label="入口能力">{{ selectedModel.entry_enabled ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="实体解析">{{ selectedModel.supports_entity_resolution ? '支持' : '不支持' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-block">
          <div class="detail-title">业务术语</div>
          <div class="tag-list">
            <el-tag v-for="item in selectedModel.business_terms || []" :key="item" size="small">{{ item }}</el-tag>
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-title">分析模式</div>
          <div class="tag-list">
            <el-tag v-for="item in selectedModel.analysis_patterns || []" :key="item" size="small" type="success">
              {{ item }}
            </el-tag>
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-title">证据要求</div>
          <div class="tag-list">
            <el-tag v-for="item in selectedModel.evidence_requirements || []" :key="item" size="small" type="warning">
              {{ item }}
            </el-tag>
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-title">维度 / 指标</div>
          <div class="tag-list">
            <el-tag v-for="item in selectedModel.dimensions || []" :key="`d-${item}`" size="small" type="info">{{ item }}</el-tag>
            <el-tag v-for="item in selectedModel.metrics || []" :key="`m-${item}`" size="small" type="danger">{{ item }}</el-tag>
          </div>
        </div>

        <h4 class="schema-title">表结构</h4>
        <el-table :data="tableColumns" size="small" stripe max-height="360" class="dark-table">
          <el-table-column prop="column_name" label="字段名" width="180" />
          <el-table-column prop="data_type" label="类型" width="140" />
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
const activeTab = ref<'entity_dimension' | 'atomic_fact' | 'composite_analysis'>('entity_dimension')
const detailVisible = ref(false)
const selectedModel = ref<SemanticModel | null>(null)
const tableColumns = ref<any[]>([])
const queryLoading = ref(false)
const queryError = ref('')
const queryResult = ref<SemanticQueryResult | null>(null)
const queryModelName = ref('')
const queryDimensionsText = ref('')
const queryMetricsText = ref('')
const queryGrainText = ref('')
const queryLimitText = ref('20')
const queryFiltersText = ref('')
const queryEntityFiltersText = ref('')
const queryResolvedFiltersText = ref('')
const queryOrderText = ref('')

const queryableModels = computed(() => models.value.filter(model => model.has_yaml_definition))
const entityModels = computed(() => modelsByKind.value.entity_dimension)
const atomicModels = computed(() => modelsByKind.value.atomic_fact)
const compositeModels = computed(() => modelsByKind.value.composite_analysis)

const modelsByKind = computed(() => {
  const grouped = {
    entity_dimension: [] as SemanticModel[],
    atomic_fact: [] as SemanticModel[],
    composite_analysis: [] as SemanticModel[],
  }
  for (const model of models.value) {
    const kind = model.semantic_kind
    if (kind === 'entity_dimension' || kind === 'atomic_fact' || kind === 'composite_analysis') {
      grouped[kind].push(model)
    }
  }
  return grouped
})

onMounted(async () => {
  await loadCatalog()
  if (!queryModelName.value && queryableModels.value.length > 0) {
    queryModelName.value = queryableModels.value[0].name
  }
})

async function loadCatalog() {
  const { data } = await axios.get(`${API}/semantic/catalog`)
  if (Array.isArray(data)) {
    models.value = data
    return
  }
  if (Array.isArray(data?.models)) {
    models.value = data.models
    return
  }
  if (data?.models && typeof data.models === 'object') {
    models.value = Object.values(data.models).flat() as SemanticModel[]
    return
  }
  models.value = []
}

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
      grain: queryGrainText.value.trim() || undefined,
      filters: parseJsonArray(queryFiltersText.value),
      entity_filters: parseJsonObject(queryEntityFiltersText.value),
      resolved_filters: parseJsonObject(queryResolvedFiltersText.value),
      order: parseJsonArray(queryOrderText.value),
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

function parseJsonArray(value: string): any[] {
  if (!value.trim()) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function parseJsonObject(value: string): Record<string, any> {
  if (!value.trim()) return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function kindLabel(kind?: string | null) {
  return {
    entity_dimension: '实体维度',
    atomic_fact: '原子事实',
    composite_analysis: '复合分析',
  }[kind || ''] || kind || '-'
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
  margin-bottom: 12px;
}

.query-grid-wide {
  margin-top: 0;
}

.query-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.query-error {
  color: #f56c6c;
  font-size: 13px;
}

.query-result {
  margin-top: 16px;
}

.query-summary,
.query-filters {
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
  justify-content: space-between;
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
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.model-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
}

.detail-block {
  margin-top: 18px;
}

.detail-title,
.schema-title {
  margin: 20px 0 10px;
  color: #e0e0e0;
  font-size: 14px;
  font-weight: 600;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.el-tabs__item) {
  color: #a0a0a0;
}

:deep(.el-tabs__item.is-active) {
  color: #409eff;
}
</style>
