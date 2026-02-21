<template>
  <div class="search-bar">
    <form @submit.prevent="$emit('search')">
      <input
        :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
        type="text"
        placeholder="Search in prefix/middle/suffix..."
        class="search-input"
      />
      <button type="submit" class="search-btn">Search</button>
    </form>
  </div>
</template>

<script setup>
defineProps(['modelValue'])
defineEmits(['update:modelValue', 'search'])
</script>

<style scoped>
.search-bar { margin-bottom: 16px; }
.search-bar form { display: flex; gap: 8px; }
.search-input { flex: 1; }
.search-btn {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
  font-weight: 600;
}
</style>
