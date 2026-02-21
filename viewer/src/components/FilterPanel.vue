<template>
  <div class="filter-panel">
    <h3>Filters</h3>

    <div class="filter-section">
      <label class="filter-label">Span Kind</label>
      <div v-for="sk in facets.span_kinds" :key="sk.name" class="checkbox-row">
        <label>
          <input
            type="checkbox"
            :value="sk.name"
            :checked="selected.span_kinds.includes(sk.name)"
            @change="toggleSpanKind(sk.name)"
          />
          {{ sk.name }} <span class="count">({{ sk.count }})</span>
        </label>
      </div>
    </div>

    <div class="filter-section">
      <label class="filter-label">Filepath</label>
      <input
        v-model="filepathQuery"
        type="text"
        placeholder="Filter by path..."
        class="filter-input"
        @input="emitFilters"
      />
    </div>

    <div class="filter-section" v-if="facets.complexity_range">
      <label class="filter-label">Complexity</label>
      <div class="range-row">
        <input
          type="number"
          :min="facets.complexity_range.min"
          :max="facets.complexity_range.max"
          :step="0.1"
          :placeholder="facets.complexity_range.min.toFixed(1)"
          v-model.number="complexityMin"
          class="range-input"
          @change="emitFilters"
        />
        <span class="range-sep">—</span>
        <input
          type="number"
          :min="facets.complexity_range.min"
          :max="facets.complexity_range.max"
          :step="0.1"
          :placeholder="facets.complexity_range.max.toFixed(1)"
          v-model.number="complexityMax"
          class="range-input"
          @change="emitFilters"
        />
      </div>
    </div>

    <button class="clear-btn" @click="clearAll">Clear all</button>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'

const props = defineProps({
  facets: { type: Object, required: true },
  filters: { type: Object, required: true },
})

const emit = defineEmits(['update:filters'])

const selected = reactive({ span_kinds: [...(props.filters.span_kinds || [])] })
const filepathQuery = ref(props.filters.filepath || '')
const complexityMin = ref(props.filters.complexity_min)
const complexityMax = ref(props.filters.complexity_max)

function toggleSpanKind(kind) {
  const idx = selected.span_kinds.indexOf(kind)
  if (idx >= 0) selected.span_kinds.splice(idx, 1)
  else selected.span_kinds.push(kind)
  emitFilters()
}

function emitFilters() {
  emit('update:filters', {
    span_kinds: [...selected.span_kinds],
    filepath: filepathQuery.value,
    complexity_min: complexityMin.value || null,
    complexity_max: complexityMax.value || null,
  })
}

function clearAll() {
  selected.span_kinds = []
  filepathQuery.value = ''
  complexityMin.value = null
  complexityMax.value = null
  emitFilters()
}
</script>

<style scoped>
.filter-panel h3 {
  font-size: 14px;
  margin-bottom: 16px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.filter-section { margin-bottom: 20px; }
.filter-label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.checkbox-row {
  margin-bottom: 4px;
}
.checkbox-row label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}
.count { color: var(--text-muted); font-size: 12px; }
.filter-input { width: 100%; }
.range-row { display: flex; align-items: center; gap: 6px; }
.range-input { width: 80px; }
.range-sep { color: var(--text-muted); }
.clear-btn {
  width: 100%;
  font-size: 12px;
  color: var(--text-muted);
  border: 1px dashed var(--border);
  background: transparent;
}
</style>
