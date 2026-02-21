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

export const api = {
  open: (path) => get('/open', { path }),
  status: () => get('/status'),
  metadata: () => get('/metadata'),
  facets: (file) => get('/facets', { file }),
  examples: (params) => get('/examples', params),
  search: (params) => get('/search', params),
}
