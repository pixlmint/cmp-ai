<template>
  <div class="dataset-layout">
    <aside class="sidebar">
      <FilterPanel
        :facets="facets"
        :filters="filters"
        @update:filters="onFiltersUpdate"
      />
    </aside>
    <main class="main-content">
      <DatasetOverview v-if="metadata" :metadata="metadata" :files="files" :activeFile="activeFile" @selectFile="selectFile" />

      <SearchBar v-model="searchQuery" @search="doSearch" />

      <div v-if="loading" class="loading">Loading...</div>

      <template v-if="!loading && examples.length">
        <ExampleList :examples="examples" :language="metadata?.language || 'python'" />
        <Pagination
          :page="page"
          :totalPages="totalPages"
          :total="total"
          @update:page="goToPage"
        />
      </template>

      <div v-if="!loading && !examples.length && hasLoaded" class="empty">
        No examples found.
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'
import FilterPanel from '../components/FilterPanel.vue'
import DatasetOverview from '../components/DatasetOverview.vue'
import SearchBar from '../components/SearchBar.vue'
import ExampleList from '../components/ExampleList.vue'
import Pagination from '../components/Pagination.vue'

const router = useRouter()
const metadata = ref(null)
const files = ref([])
const activeFile = ref('train.jsonl')
const facets = ref({ span_kinds: [], filepaths: [], complexity_range: { min: 0, max: 0 } })
const filters = reactive({ span_kinds: [], filepath: '', complexity_min: null, complexity_max: null })
const examples = ref([])
const page = ref(1)
const totalPages = ref(0)
const total = ref(0)
const loading = ref(false)
const hasLoaded = ref(false)
const searchQuery = ref('')

onMounted(async () => {
  try {
    const status = await api.status()
    if (!status.open) {
      router.push('/')
      return
    }
    metadata.value = await api.metadata()
    // Derive file list from metadata
    files.value = []
    if (metadata.value.train_examples) files.value.push({ name: 'train.jsonl', examples: metadata.value.train_examples })
    if (metadata.value.val_examples) files.value.push({ name: 'val.jsonl', examples: metadata.value.val_examples })
    await loadFacets()
    await loadExamples()
  } catch {
    router.push('/')
  }
})

async function loadFacets() {
  facets.value = await api.facets(activeFile.value)
}

async function loadExamples() {
  loading.value = true
  try {
    const params = {
      file: activeFile.value,
      page: page.value,
      per_page: 20,
    }
    if (filters.span_kinds.length) params.span_kinds = filters.span_kinds.join(',')
    if (filters.filepath) params.filepath = filters.filepath
    if (filters.complexity_min != null) params.complexity_min = filters.complexity_min
    if (filters.complexity_max != null) params.complexity_max = filters.complexity_max

    let data
    if (searchQuery.value) {
      data = await api.search({ ...params, q: searchQuery.value })
    } else {
      data = await api.examples(params)
    }
    examples.value = data.examples
    totalPages.value = data.total_pages
    total.value = data.total
    hasLoaded.value = true
  } finally {
    loading.value = false
  }
}

function selectFile(f) {
  activeFile.value = f
  page.value = 1
  loadFacets()
  loadExamples()
}

function onFiltersUpdate(newFilters) {
  Object.assign(filters, newFilters)
  page.value = 1
  loadExamples()
}

function goToPage(p) {
  page.value = p
  loadExamples()
}

function doSearch() {
  page.value = 1
  loadExamples()
}
</script>

<style scoped>
.dataset-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: calc(100vh - 49px);
}
.sidebar {
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  padding: 16px;
  overflow-y: auto;
}
.main-content {
  padding: 20px 24px;
  overflow-y: auto;
}
.loading {
  color: var(--text-muted);
  padding: 40px;
  text-align: center;
}
.empty {
  color: var(--text-muted);
  padding: 40px;
  text-align: center;
}
</style>
