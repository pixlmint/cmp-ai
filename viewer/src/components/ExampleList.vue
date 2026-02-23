<template>
  <div class="example-list">
    <ExampleCard
      v-for="(ex, i) in examples"
      :key="ex._index ?? i"
      :example="ex"
      :language="language"
      :sourceFile="activeFile"
      :pending="getPending(ex._index)"
      @move="$emit('move', $event)"
      @undo="$emit('undo', $event)"
    />
  </div>
</template>

<script setup>
import ExampleCard from './ExampleCard.vue'

const props = defineProps({
  examples: { type: Array, required: true },
  language: { type: String, default: 'python' },
  activeFile: { type: String, default: '' },
  pendingMoves: { type: Object, default: () => ({}) },
})

defineEmits(['move', 'undo'])

function getPending(index) {
  const key = `${props.activeFile}:${index}`
  const move = props.pendingMoves[key]
  if (!move) return null
  return move.destFile === 'reject.jsonl' ? 'rejected' : 'accepted'
}
</script>
