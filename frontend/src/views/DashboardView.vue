<template>
  <div class="dashboard-container">
    <div class="page-header">
      <h2>数据资产总览</h2>
      <el-button type="primary" @click="refreshData" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{{ tables.length }}</div>
        <div class="stat-label">数据表</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ totalRows.toLocaleString() }}</div>
        <div class="stat-label">数据行数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ modelCount }}</div>
        <div class="stat-label">语义模型</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">10</div>
        <div class="stat-label">企业主体</div>
      </div>
    </div>

    <!-- 数据表列表 -->
    <h3 class="section-title">数据表概览</h3>
    <el-table :data="tables" stripe size="small" class="dark-table" max-height="500">
      <el-table-column prop="table_name" label="表名" width="300">
        <template #default="{ row }">
          <el-link type="primary" @click="viewTable(row.table_name)">{{ row.table_name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="row_count" label="行数" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ row.row_count?.toLocaleString() }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="分类" width="120">
        <template #default="{ row }">
          <el-tag :type="getCategory(row.table_name).type" size="small">
            {{ getCategory(row.table_name).label }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 表结构弹窗 -->
    <el-dialog v-model="schemaVisible" :title="`表结构: ${schemaTable}`" width="700px">
      <el-table :data="schemaColumns" size="small" stripe max-height="400">
        <el-table-column prop="column_name" label="字段" width="200" />
        <el-table-column prop="data_type" label="类型" width="150" />
        <el-table-column prop="nullable" label="可空" width="80" />
        <el-table-column prop="comment" label="注释" />
      </el-table>
      <h4 style="margin: 16px 0 8px">数据预览 (前5行)</h4>
      <el-table :data="schemaPreview" size="small" stripe max-height="200">
        <el-table-column v-for="col in previewColumns" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { getApiBase } from '../config/runtime'
import type { TableInfo } from '../types/agent'

const API = getApiBase()
const tables = ref<TableInfo[]>([])
const modelCount = ref(0)
const loading = ref(false)
const schemaVisible = ref(false)
const schemaTable = ref('')
const schemaColumns = ref<any[]>([])
const schemaPreview = ref<any[]>([])
const previewColumns = ref<string[]>([])

const totalRows = computed(() => tables.value.reduce((sum, t) => sum + (t.row_count || 0), 0))

onMounted(() => refreshData())

async function refreshData() {
  loading.value = true
  try {
    const [tablesRes, modelsRes] = await Promise.all([
      axios.get(`${API}/datasource/tables`),
      axios.get(`${API}/semantic/models`),
    ])
    tables.value = tablesRes.data
    modelCount.value = modelsRes.data.length
  } finally {
    loading.value = false
  }
}

async function viewTable(name: string) {
  schemaTable.value = name
  const { data } = await axios.get(`${API}/datasource/tables/${name}/schema`)
  schemaColumns.value = data.columns || []
  schemaPreview.value = data.preview || []
  previewColumns.value = schemaColumns.value.map((c: any) => c.column_name)
  schemaVisible.value = true
}

function getCategory(name: string): { label: string; type: string } {
  if (name.startsWith('enterprise')) return { label: '企业', type: '' }
  if (name.startsWith('tax_')) return { label: '税务', type: 'danger' }
  if (name.startsWith('acct_')) return { label: '账务', type: 'warning' }
  if (name.startsWith('recon_')) return { label: '对账', type: 'success' }
  if (name.startsWith('sys_') || name.startsWith('dict_')) return { label: '系统', type: 'info' }
  return { label: '其他', type: 'info' }
}
</script>

<style scoped>
.dashboard-container {
  padding: 24px 32px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 22px;
  color: #e0e0e0;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  background: linear-gradient(135deg, #409eff, #67c23a);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.stat-label {
  font-size: 14px;
  color: #888;
  margin-top: 6px;
}

.section-title {
  font-size: 16px;
  color: #e0e0e0;
  margin-bottom: 12px;
}
</style>
