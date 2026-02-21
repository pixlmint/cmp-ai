<template>
  <div class="overview" :class="{ collapsed }">
    <div class="overview-header" @click="collapsed = !collapsed">
      <h2>{{ metadata.language || 'Dataset' }} — {{ metadata.base_model || '' }}</h2>
      <span class="toggle">{{ collapsed ? '▸' : '▾' }}</span>
    </div>
    <div v-show="!collapsed" class="overview-body">
      <div class="stats-grid">
        <div class="stat">
          <span class="stat-value">{{ metadata.train_examples ?? '—' }}</span>
          <span class="stat-label">train</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ metadata.val_examples ?? '—' }}</span>
          <span class="stat-label">val</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ metadata.total_files ?? '—' }}</span>
          <span class="stat-label">files</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ metadata.max_middle_lines ?? '—' }}</span>
          <span class="stat-label">max middle lines</span>
        </div>
      </div>
      <div v-if="metadata.span_type_distribution" class="distribution">
        <span v-for="(count, kind) in metadata.span_type_distribution" :key="kind" class="dist-badge">
          {{ kind }}: {{ count }}
        </span>
      </div>
      <div class="file-tabs">
        <button
          v-for="f in files"
          :key="f.name"
          :class="['file-tab', { active: f.name === activeFile }]"
          @click="$emit('selectFile', f.name)"
        >{{ f.name }} ({{ f.examples }})</button>
      </div>
      <div class="flags">
        <span v-if="metadata.cross_file_context" class="flag on">cross-file</span>
        <span v-if="metadata.bm25_context" class="flag on">bm25</span>
        <span v-if="metadata.ast_fim" class="flag on">ast-fim</span>
        <span v-if="metadata.quality_filter" class="flag on">quality-filter</span>
        <span v-if="metadata.curriculum" class="flag on">curriculum</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps(['metadata', 'files', 'activeFile'])
defineEmits(['selectFile'])
const collapsed = ref(false)
</script>

<style scoped>
.overview {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
}
.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
}
.overview-header h2 { font-size: 16px; }
.toggle { color: var(--text-muted); }
.overview-body { padding: 0 16px 16px; }
.stats-grid {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
}
.stat { display: flex; flex-direction: column; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--accent); }
.stat-label { font-size: 12px; color: var(--text-muted); }
.distribution { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.dist-badge {
  background: var(--accent-soft);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
}
.file-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.file-tab { font-size: 13px; }
.file-tab.active { border-color: var(--accent); color: var(--accent); }
.flags { display: flex; gap: 6px; flex-wrap: wrap; }
.flag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: var(--border);
  color: var(--text-muted);
}
.flag.on { background: rgba(76, 175, 80, 0.2); color: var(--success); }
</style>
