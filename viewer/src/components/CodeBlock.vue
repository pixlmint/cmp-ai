<template>
  <div class="code-block" :class="variant">
    <div class="code-label" v-if="label">{{ label }}</div>
    <pre><code ref="codeEl" v-html="highlighted"></code></pre>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import hljs from 'highlight.js'

const props = defineProps({
  code: { type: String, default: '' },
  language: { type: String, default: '' },
  variant: { type: String, default: '' }, // 'middle', 'prefix', 'suffix', 'context'
  label: { type: String, default: '' },
})

const highlighted = computed(() => {
  if (!props.code) return ''
  const lang = mapLanguage(props.language)
  try {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(props.code, { language: lang }).value
    }
  } catch { /* fallback */ }
  return hljs.highlightAuto(props.code).value
})

function mapLanguage(lang) {
  const map = { php: 'php', python: 'python', py: 'python', javascript: 'javascript', js: 'javascript', typescript: 'typescript', ts: 'typescript', lua: 'lua', go: 'go', rust: 'rust', java: 'java', ruby: 'ruby', c: 'c', cpp: 'cpp' }
  return map[(lang || '').toLowerCase()] || lang || ''
}
</script>

<style scoped>
.code-block {
  border-radius: 4px;
  overflow: hidden;
}
.code-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 12px;
  color: var(--text-muted);
  background: rgba(255,255,255,0.03);
}
pre {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  background: var(--code-bg);
}
.middle pre {
  background: var(--middle-bg);
  border-left: 3px solid var(--middle-border);
}
.context pre {
  background: rgba(76, 175, 80, 0.06);
  border-left: 3px solid rgba(76, 175, 80, 0.3);
}
.prefix pre, .suffix pre {
  opacity: 0.75;
}
</style>

<style>
/* highlight.js theme — github-dark-dimmed inspired */
.hljs { color: #adbac7; }
.hljs-keyword { color: #f47067; }
.hljs-string { color: #96d0ff; }
.hljs-number { color: #6cb6ff; }
.hljs-function { color: #dcbdfb; }
.hljs-title { color: #dcbdfb; }
.hljs-comment { color: #636e7b; font-style: italic; }
.hljs-variable { color: #f69d50; }
.hljs-built_in { color: #6cb6ff; }
.hljs-type { color: #6cb6ff; }
.hljs-attr { color: #6cb6ff; }
.hljs-params { color: #adbac7; }
.hljs-literal { color: #6cb6ff; }
.hljs-meta { color: #636e7b; }
</style>
