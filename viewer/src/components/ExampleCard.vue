<template>
  <div class="example-card" :class="{ 'is-pending': pending }">
    <div class="card-header">
      <span class="filepath">{{ example.filepath }}</span>
      <span class="badge kind">{{ example.span_kind }}</span>
      <span v-if="example.span_name" class="badge name">{{ example.span_name }}</span>
      <span class="meta">{{ example.middle_lines }} lines</span>
      <span class="meta">score: {{ example.complexity_score?.toFixed(2) }}</span>
      <span class="meta index">#{{ example._index }}</span>
      <span v-if="pending" class="badge pending-badge" :class="pending">
        {{ pending === 'accepted' ? 'pending accept' : 'pending reject' }}
      </span>
      <button v-if="pending" class="btn btn-undo" @click="$emit('undo', { sourceFile, index: example._index })">undo</button>
      <button v-if="!pending && showReject" class="btn btn-reject" @click="$emit('move', { sourceFile, index: example._index, destFile: 'reject.jsonl' })">reject</button>
      <button v-if="!pending && showAccept" class="btn btn-accept" @click="$emit('move', { sourceFile, index: example._index, destFile: 'train.jsonl' })">accept</button>
    </div>

    <div v-if="crossFileContext" class="section">
      <div class="section-toggle" @click="showContext = !showContext">
        {{ showContext ? '▾' : '▸' }} Cross-file context ({{ crossFileLines.length }} files)
      </div>
      <CodeBlock v-if="showContext" :code="crossFileContext" :language="language" variant="context" />
    </div>

    <div class="section">
      <div class="section-toggle" @click="showPrefix = !showPrefix">
        {{ showPrefix ? '▾' : '▸' }} Prefix ({{ prefixLineCount }} lines)
      </div>
      <CodeBlock v-if="showPrefix" :code="localPrefix" :language="language" variant="prefix" label="prefix" />
    </div>

    <div class="section middle-section">
      <CodeBlock :code="example.middle" :language="language" variant="middle" label="middle (prediction target)" />
    </div>

    <div class="section">
      <div class="section-toggle" @click="showSuffix = !showSuffix">
        {{ showSuffix ? '▾' : '▸' }} Suffix ({{ suffixLineCount }} lines)
      </div>
      <CodeBlock v-if="showSuffix" :code="example.suffix" :language="language" variant="suffix" label="suffix" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import CodeBlock from './CodeBlock.vue'

const props = defineProps({
  example: { type: Object, required: true },
  language: { type: String, default: '' },
  sourceFile: { type: String, default: '' },
  pending: { type: String, default: null }, // 'accepted' | 'rejected' | null
})

defineEmits(['move', 'undo'])

const showReject = computed(() => props.sourceFile && props.sourceFile !== 'reject.jsonl')
const showAccept = computed(() => props.sourceFile === 'reject.jsonl')

const showContext = ref(false)
const showPrefix = ref(false)
const showSuffix = ref(false)

// Separate cross-file context lines (// --- filename ---) from the prefix
const crossFileLines = computed(() => {
  const lines = (props.example.prefix || '').split('\n')
  const contextFiles = []
  let inContext = true
  for (const line of lines) {
    if (inContext && /^\/\/ --- .+ ---$/.test(line)) {
      contextFiles.push(line)
    } else {
      inContext = false
    }
  }
  return contextFiles
})

const crossFileContext = computed(() => {
  if (!crossFileLines.value.length) return ''
  const lines = (props.example.prefix || '').split('\n')
  // Find where the actual local prefix starts (after all cross-file context)
  let endOfContext = 0
  for (let i = 0; i < lines.length; i++) {
    if (/^\/\/ --- .+ ---$/.test(lines[i])) {
      // Find the next header or end of context block
      endOfContext = i
    } else if (endOfContext > 0) {
      break
    }
  }
  // Context is everything up to where the local code starts
  // Detect: lines that are part of cross-file blocks
  const contextLines = []
  let isContext = false
  for (let i = 0; i < lines.length; i++) {
    if (/^\/\/ --- .+ ---$/.test(lines[i])) {
      isContext = true
      contextLines.push(lines[i])
    } else if (isContext && lines[i].trim() === '') {
      // Blank line might be between context blocks
      if (i + 1 < lines.length && /^\/\/ --- .+ ---$/.test(lines[i + 1])) {
        contextLines.push(lines[i])
      } else {
        break
      }
    } else if (isContext) {
      contextLines.push(lines[i])
    } else {
      break
    }
  }
  return contextLines.join('\n')
})

const localPrefix = computed(() => {
  if (!crossFileContext.value) return props.example.prefix || ''
  const full = props.example.prefix || ''
  const ctxLen = crossFileContext.value.length
  return full.slice(ctxLen).replace(/^\n+/, '')
})

const prefixLineCount = computed(() => (localPrefix.value.match(/\n/g) || []).length + 1)
const suffixLineCount = computed(() => ((props.example.suffix || '').match(/\n/g) || []).length + 1)
</script>

<style scoped>
.example-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
  transition: opacity 0.2s;
}
.example-card.is-pending {
  opacity: 0.5;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.filepath {
  font-family: monospace;
  font-size: 13px;
  color: var(--text);
}
.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.kind { background: var(--accent-soft); color: var(--accent); }
.name { background: rgba(108, 182, 255, 0.15); color: #6cb6ff; }
.meta { font-size: 12px; color: var(--text-muted); }
.index { margin-left: auto; }
.pending-badge.accepted { background: rgba(63, 185, 80, 0.2); color: #3fb950; }
.pending-badge.rejected { background: rgba(248, 81, 73, 0.2); color: #f85149; }
.btn {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  background: transparent;
  color: var(--text-muted);
  transition: all 0.15s;
}
.btn:hover { color: var(--text); }
.btn-reject { border-color: #f85149; color: #f85149; }
.btn-reject:hover { background: rgba(248, 81, 73, 0.15); }
.btn-accept { border-color: #3fb950; color: #3fb950; }
.btn-accept:hover { background: rgba(63, 185, 80, 0.15); }
.btn-undo { border-color: var(--text-muted); }
.btn-undo:hover { background: rgba(255, 255, 255, 0.05); }
.section-toggle {
  padding: 6px 16px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
}
.section-toggle:hover { color: var(--text); }
.middle-section { border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
</style>
