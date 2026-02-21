import { Router } from 'express'
import { store } from '../lib/store.js'
import { filterMetadata, extractFacets } from '../lib/filter.js'

const router = Router()

// Open a dataset directory
router.get('/open', async (req, res) => {
  const { path } = req.query
  if (!path) return res.status(400).json({ error: 'path is required' })

  try {
    const result = await store.open(path)
    res.json(result)
  } catch (err) {
    res.status(500).json({ error: err.message })
  }
})

// Indexing progress
router.get('/status', (req, res) => {
  res.json({
    indexing: store.indexing,
    progress: store.indexProgress,
    open: store.datasetPath != null,
    path: store.datasetPath,
  })
})

// Parsed metadata.json
router.get('/metadata', (req, res) => {
  if (!store.metadataJson) return res.status(404).json({ error: 'No dataset open' })
  res.json(store.metadataJson)
})

// Available filter facets for a file
router.get('/facets', (req, res) => {
  const file = req.query.file || 'train.jsonl'
  const f = store.getFile(file)
  if (!f) return res.status(404).json({ error: `File not found: ${file}` })

  res.json(extractFacets(f.metadata))
})

// Paginated examples with optional filters
router.get('/examples', async (req, res) => {
  const file = req.query.file || 'train.jsonl'
  const page = Math.max(1, parseInt(req.query.page) || 1)
  const perPage = Math.min(100, Math.max(1, parseInt(req.query.per_page) || 20))

  const f = store.getFile(file)
  if (!f) return res.status(404).json({ error: `File not found: ${file}` })

  // Build filters from query params
  const filters = {}
  if (req.query.span_kinds) filters.span_kinds = req.query.span_kinds.split(',')
  if (req.query.filepath) filters.filepath = req.query.filepath
  if (req.query.complexity_min) filters.complexity_min = parseFloat(req.query.complexity_min)
  if (req.query.complexity_max) filters.complexity_max = parseFloat(req.query.complexity_max)

  const hasFilters = Object.keys(filters).length > 0
  const matchingIndices = hasFilters ? filterMetadata(f.metadata, filters) : f.metadata.map(m => m.index)

  const total = matchingIndices.length
  const totalPages = Math.ceil(total / perPage)
  const start = (page - 1) * perPage
  const pageIndices = matchingIndices.slice(start, start + perPage)

  const examples = await f.reader.readLines(pageIndices, f.offsets, f.lengths)

  res.json({
    page,
    per_page: perPage,
    total,
    total_pages: totalPages,
    examples: examples.map((ex, i) => ex ? { ...ex, _index: pageIndices[i] } : null).filter(Boolean),
  })
})

// Full-text search
router.get('/search', async (req, res) => {
  const file = req.query.file || 'train.jsonl'
  const q = (req.query.q || '').toLowerCase()
  const page = Math.max(1, parseInt(req.query.page) || 1)
  const perPage = Math.min(100, Math.max(1, parseInt(req.query.per_page) || 20))

  if (!q) return res.status(400).json({ error: 'q is required' })

  const f = store.getFile(file)
  if (!f) return res.status(404).json({ error: `File not found: ${file}` })

  // Scan through all lines looking for matches in prefix/middle/suffix/filepath
  const matchingIndices = []
  for (let i = 0; i < f.metadata.length; i++) {
    // Quick check metadata fields first
    if (f.metadata[i].filepath.toLowerCase().includes(q) ||
        f.metadata[i].span_name.toLowerCase().includes(q)) {
      matchingIndices.push(i)
      continue
    }
    // For deeper search, read the actual line
    const raw = await f.reader.readLine(f.offsets[i], f.lengths[i])
    if (raw.toLowerCase().includes(q)) {
      matchingIndices.push(i)
    }
  }

  const total = matchingIndices.length
  const totalPages = Math.ceil(total / perPage)
  const start = (page - 1) * perPage
  const pageIndices = matchingIndices.slice(start, start + perPage)

  const examples = await f.reader.readLines(pageIndices, f.offsets, f.lengths)

  res.json({
    page,
    per_page: perPage,
    total,
    total_pages: totalPages,
    query: q,
    examples: examples.map((ex, i) => ex ? { ...ex, _index: pageIndices[i] } : null).filter(Boolean),
  })
})

export default router
