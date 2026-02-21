import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { buildIndex } from './indexer.js'
import { LineReader } from './reader.js'

/**
 * In-memory state for the currently active dataset.
 */
class DatasetStore {
  constructor() {
    this.datasetPath = null
    this.metadataJson = null
    this.files = {}       // { filename: { offsets, lengths, metadata, reader } }
    this.indexing = false
    this.indexProgress = { file: '', indexed: 0, total: 0 }
  }

  async open(dirPath) {
    // Close previous dataset
    await this.close()

    this.datasetPath = dirPath

    // Read metadata.json
    try {
      const raw = await readFile(join(dirPath, 'metadata.json'), 'utf-8')
      this.metadataJson = JSON.parse(raw)
    } catch {
      this.metadataJson = null
    }

    // Find JSONL files
    const jsonlFiles = []
    for (const name of ['train.jsonl', 'val.jsonl']) {
      try {
        const s = await stat(join(dirPath, name))
        if (s.isFile()) jsonlFiles.push(name)
      } catch { /* skip */ }
    }

    this.indexing = true
    this.indexProgress = { file: '', indexed: 0, total: jsonlFiles.length }

    for (const filename of jsonlFiles) {
      this.indexProgress.file = filename
      const filePath = join(dirPath, filename)
      const { offsets, lengths, metadata } = await buildIndex(filePath, (n) => {
        this.indexProgress.indexed = n
      })

      const reader = new LineReader()
      await reader.open(filePath)

      this.files[filename] = { offsets, lengths, metadata, reader }
    }

    this.indexing = false
    return {
      path: dirPath,
      metadata: this.metadataJson,
      files: Object.entries(this.files).map(([name, f]) => ({
        name,
        examples: f.metadata.length,
      })),
    }
  }

  getFile(filename) {
    return this.files[filename] || null
  }

  async close() {
    for (const f of Object.values(this.files)) {
      await f.reader.close()
    }
    this.files = {}
    this.datasetPath = null
    this.metadataJson = null
  }
}

export const store = new DatasetStore()
