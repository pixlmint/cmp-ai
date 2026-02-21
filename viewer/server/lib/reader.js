import { open } from 'node:fs/promises'

/**
 * Random-access line reader using byte offsets.
 * Keeps a file descriptor open for the active dataset file.
 */
export class LineReader {
  constructor() {
    this.fh = null
    this.filePath = null
  }

  async open(filePath) {
    if (this.fh) await this.close()
    this.fh = await open(filePath, 'r')
    this.filePath = filePath
  }

  async close() {
    if (this.fh) {
      await this.fh.close()
      this.fh = null
      this.filePath = null
    }
  }

  /**
   * Read a single line by index using pre-built offset/length arrays.
   */
  async readLine(offset, length) {
    if (!this.fh) throw new Error('No file open')
    const buf = Buffer.alloc(length)
    await this.fh.read(buf, 0, length, offset)
    return buf.toString('utf-8')
  }

  /**
   * Read multiple lines by their indices. Returns parsed JSON objects.
   */
  async readLines(indices, offsets, lengths) {
    const results = []
    for (const i of indices) {
      const raw = await this.readLine(offsets[i], lengths[i])
      try {
        results.push(JSON.parse(raw))
      } catch {
        results.push(null)
      }
    }
    return results
  }
}
