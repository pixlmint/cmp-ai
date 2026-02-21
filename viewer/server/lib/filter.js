/**
 * Filter the in-memory metadata index and return matching line indices.
 */
export function filterMetadata(metadata, filters) {
  let results = metadata

  if (filters.span_kinds && filters.span_kinds.length > 0) {
    const kinds = new Set(filters.span_kinds)
    results = results.filter(m => kinds.has(m.span_kind))
  }

  if (filters.filepath) {
    const q = filters.filepath.toLowerCase()
    results = results.filter(m => m.filepath.toLowerCase().includes(q))
  }

  if (filters.complexity_min != null) {
    results = results.filter(m => m.complexity_score >= filters.complexity_min)
  }

  if (filters.complexity_max != null) {
    results = results.filter(m => m.complexity_score <= filters.complexity_max)
  }

  return results.map(m => m.index)
}

/**
 * Extract available facet values from metadata.
 */
export function extractFacets(metadata) {
  const spanKinds = {}
  const filepaths = {}
  let minComplexity = Infinity
  let maxComplexity = -Infinity

  for (const m of metadata) {
    spanKinds[m.span_kind] = (spanKinds[m.span_kind] || 0) + 1
    filepaths[m.filepath] = (filepaths[m.filepath] || 0) + 1
    if (m.complexity_score < minComplexity) minComplexity = m.complexity_score
    if (m.complexity_score > maxComplexity) maxComplexity = m.complexity_score
  }

  return {
    span_kinds: Object.entries(spanKinds).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count),
    filepaths: Object.entries(filepaths).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count),
    complexity_range: { min: minComplexity === Infinity ? 0 : minComplexity, max: maxComplexity === -Infinity ? 0 : maxComplexity },
  }
}
