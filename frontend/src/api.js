async function request(method, url, body, isForm = false) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    if (isForm) opts.body = body
    else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  const res = await fetch(url, opts)
  if (res.status === 401 && !url.startsWith('/api/auth/')) window.dispatchEvent(new Event('govbid:signed-out'))
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {}
    throw new Error(msg)
  }
  const type = res.headers.get('content-type') || ''
  return type.includes('application/json') ? res.json() : res
}

export const api = {
  get: (u) => request('GET', u),
  post: (u, b) => request('POST', u, b),
  put: (u, b) => request('PUT', u, b),
  del: (u) => request('DELETE', u),
  upload: (u, form) => request('POST', u, form, true),
}

export function qs(params) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined && v !== false) p.set(k, v)
  })
  return p.toString()
}

export const money = (n) =>
  n == null ? '' : n >= 1e6 ? `$${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`

export function fmtDue(s) {
  if (!s) return 'n/a'
  if (/^\d{4}-\d{2}-\d{2}T/.test(s)) {
    const d = new Date(s)
    if (!isNaN(d)) return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, dd] = s.split('-').map(Number)
    return new Date(y, m - 1, dd).toLocaleDateString([], { dateStyle: 'medium' })
  }
  return s
}
