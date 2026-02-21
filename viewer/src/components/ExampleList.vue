<template>
  <div class="example-list">
    <ExampleCard
      v-for="(ex, i) in examples"
      :key="ex._index ?? i"
      :example="ex"
      :language="language"
    />
  </div>
</template>

<script setup>
import ExampleCard from './ExampleCard.vue'

defineProps({
  examples: { type: Array, required: true },
  language: { type: String, default: 'python' },
})
</script>
