import { createReadStream } from 'node:fs'
import { createInterface } from 'node:readline'

/**
 * Build a byte-offset index for a JSONL file.
 * Returns { offsets: number[], lengths: number[], metadata: object[] }
 * where metadata[i] has lightweight fields extracted from each line.
 */
export async function buildIndex(filePath, onProgress) {
  const offsets = []
  const lengths = []
  const metadata = []

  const stream = createReadStream(filePath, { encoding: 'utf-8' })
  const rl = createInterface({ input: stream, crlfDelay: Infinity })

  let byteOffset = 0
  let lineNum = 0

  for await (const line of rl) {
    const lineBytes = Buffer.byteLength(line, 'utf-8')
    if (line.trim()) {
      offsets.push(byteOffset)
      lengths.push(lineBytes)
      try {
        const obj = JSON.parse(line)
        metadata.push({
          index: lineNum,
          span_kind: obj.span_kind || '',
          filepath: obj.filepath || '',
          complexity_score: obj.complexity_score ?? 0,
          middle_lines: obj.middle_lines ?? 0,
          span_name: obj.span_name || '',
        })
      } catch {
        metadata.push({
          index: lineNum,
          span_kind: '',
          filepath: '',
          complexity_score: 0,
          middle_lines: 0,
          span_name: '',
        })
      }
      lineNum++
    }
    // +1 for the newline character
    byteOffset += lineBytes + 1

    if (onProgress && lineNum % 1000 === 0) {
      onProgress(lineNum)
    }
  }

  return { offsets, lengths, metadata }
}
