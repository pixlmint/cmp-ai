<template>
  <div class="pagination" v-if="totalPages > 1">
    <button :disabled="page <= 1" @click="$emit('update:page', page - 1)">&lt;</button>

    <button
      v-for="p in visiblePages"
      :key="p"
      :class="{ active: p === page, ellipsis: p === '...' }"
      :disabled="p === '...'"
      @click="p !== '...' && $emit('update:page', p)"
    >{{ p }}</button>

    <button :disabled="page >= totalPages" @click="$emit('update:page', page + 1)">&gt;</button>

    <span class="total">{{ total }} results</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  page: { type: Number, required: true },
  totalPages: { type: Number, required: true },
  total: { type: Number, default: 0 },
})

defineEmits(['update:page'])

const visiblePages = computed(() => {
  const pages = []
  const p = props.page
  const tp = props.totalPages

  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
    return pages
  }

  pages.push(1)
  if (p > 3) pages.push('...')
  for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) {
    pages.push(i)
  }
  if (p < tp - 2) pages.push('...')
  pages.push(tp)

  return pages
})
</script>

<style scoped>
.pagination {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 16px 0;
  justify-content: center;
}
.pagination button {
  min-width: 36px;
  height: 36px;
  padding: 0 8px;
  font-size: 14px;
}
.pagination button.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.pagination button.ellipsis {
  border: none;
  background: transparent;
  cursor: default;
}
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.total { margin-left: 12px; font-size: 13px; color: var(--text-muted); }
</style>
