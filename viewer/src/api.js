const BASE = '/api/datasets'

async function get(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin)
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') url.searchParams.set(k, v)
  }
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error || `HTTP ${res.status}`)
  }
  return res.json()
}

async function post(path, body, method = 'POST') {
  const url = new URL(BASE + path, window.location.origin)
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  open: (path) => get('/open', { path }),
  status: () => get('/status'),
  metadata: () => get('/metadata'),
  facets: (file) => get('/facets', { file }),
  examples: (params) => get('/examples', params),
  search: (params) => get('/search', params),
  move: (sourceFile, index, destFile) => post('/move', { sourceFile, index, destFile }),
  undoMove: (sourceFile, index) => post('/move', { sourceFile, index }, 'DELETE'),
  pending: () => get('/pending'),
  save: () => post('/save', {}),
}
