import { readFile, writeFile, stat } from 'node:fs/promises'
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
    this.pendingMoves = [] // { sourceFile, index, destFile }[]
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
    for (const name of ['train.jsonl', 'val.jsonl', 'reject.jsonl']) {
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
    this.pendingMoves = []
  }

  /**
   * Apply all pending moves: read affected files, redistribute lines, rewrite files, rebuild indexes.
   */
  async applyMoves() {
    if (!this.pendingMoves.length) return {}

    // Group moves by source file
    const movesBySource = {}
    for (const m of this.pendingMoves) {
      if (!movesBySource[m.sourceFile]) movesBySource[m.sourceFile] = []
      movesBySource[m.sourceFile].push(m)
    }

    // Collect all affected file names
    const affectedFiles = new Set()
    for (const m of this.pendingMoves) {
      affectedFiles.add(m.sourceFile)
      affectedFiles.add(m.destFile)
    }

    // Read all lines from affected files
    const fileLines = {}
    for (const name of affectedFiles) {
      fileLines[name] = []
      const f = this.files[name]
      if (f) {
        for (let i = 0; i < f.offsets.length; i++) {
          const raw = await f.reader.readLine(f.offsets[i], f.lengths[i])
          fileLines[name].push(raw)
        }
      }
    }

    // Apply moves: collect lines to remove from sources and append to destinations
    const appendTo = {} // destFile -> lines to append
    const removeFrom = {} // sourceFile -> Set of indices to remove
    for (const m of this.pendingMoves) {
      if (!removeFrom[m.sourceFile]) removeFrom[m.sourceFile] = new Set()
      if (!appendTo[m.destFile]) appendTo[m.destFile] = []
      const lines = fileLines[m.sourceFile]
      if (lines && m.index < lines.length) {
        removeFrom[m.sourceFile].add(m.index)
        appendTo[m.destFile].push(lines[m.index])
      }
    }

    // Build new file contents
    for (const name of affectedFiles) {
      const original = fileLines[name] || []
      const removals = removeFrom[name] || new Set()
      const kept = original.filter((_, i) => !removals.has(i))
      const appended = appendTo[name] || []
      fileLines[name] = [...kept, ...appended]
    }

    // Write files and rebuild indexes
    for (const name of affectedFiles) {
      const filePath = join(this.datasetPath, name)
      const content = fileLines[name].map(l => l.trimEnd()).join('\n') + (fileLines[name].length ? '\n' : '')

      // Close old reader
      if (this.files[name]) {
        await this.files[name].reader.close()
      }

      await writeFile(filePath, content, 'utf-8')

      // Rebuild index and reopen reader
      const { offsets, lengths, metadata } = await buildIndex(filePath, () => {})
      const reader = new LineReader()
      await reader.open(filePath)
      this.files[name] = { offsets, lengths, metadata, reader }
    }

    this.pendingMoves = []

    return Object.fromEntries(
      [...affectedFiles].map(name => [name, this.files[name].metadata.length])
    )
  }
}

export const store = new DatasetStore()
