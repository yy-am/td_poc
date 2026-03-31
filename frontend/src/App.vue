<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="app-sidebar">
      <div class="logo">
        <el-icon :size="28" color="#409eff"><DataAnalysis /></el-icon>
        <span class="logo-text">智税通</span>
      </div>
      <el-menu
        :default-active="currentRoute"
        router
        background-color="#1a1a2e"
        text-color="#a0a0a0"
        active-text-color="#409eff"
      >
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>问数工作台</span>
        </el-menu-item>
        <el-menu-item index="/semantic">
          <el-icon><Connection /></el-icon>
          <span>语义建模</span>
        </el-menu-item>
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据资产</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <span class="version">v1.0.0 POC</span>
      </div>
    </el-aside>

    <!-- 主内容 -->
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const currentRoute = computed(() => route.path)
</script>

<style scoped>
.app-container {
  height: 100vh;
  background-color: #0f0f23;
}

.app-sidebar {
  background-color: #1a1a2e;
  border-right: 1px solid #2a2a4a;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px;
  border-bottom: 1px solid #2a2a4a;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #409eff, #67c23a);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.el-menu {
  flex: 1;
  border-right: none;
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid #2a2a4a;
  text-align: center;
}

.version {
  font-size: 12px;
  color: #666;
}

.app-main {
  padding: 0;
  background-color: #0f0f23;
  overflow: auto;
  height: 100%;
  min-height: 0;
  display: flex;
}

.app-main > * {
  flex: 1;
  min-height: 0;
}
</style>
