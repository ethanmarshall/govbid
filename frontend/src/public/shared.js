import { useEffect, useState } from 'react'

// Helpers shared by the customer pages. Talk only to /api/public/*.

export const money = (n, cents = true) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 })}`)
export const range = (lo, hi) => `${money(lo, lo < 100)} to ${money(hi, hi < 100)}`

// Errors carry the server's reply in err.data (a price change at checkout sends the new total).
export async function call(method, url, body, form) {
  const opts = { method, headers: {}, credentials: 'same-origin' }
  if (form) opts.body = form
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body) }
  const res = await fetch(url, opts)
  let data = null
  try { data = await res.json() } catch { /* not json */ }
  if (!res.ok) {
    const d = data && data.detail
    const e = new Error((typeof d === 'string' ? d : d && d.message) || `Something went wrong (${res.status}). Try again.`)
    e.status = res.status
    e.data = d
    throw e
  }
  return data
}

// Quotes this browser has priced, so a customer can come back to them. Only refs and private links, kept on their device.
const SAVED_KEY = 'pq-saved-quotes'
export function loadSaved() {
  try { const v = JSON.parse(localStorage.getItem(SAVED_KEY) || '[]'); return Array.isArray(v) ? v : [] } catch { return [] }
}
export function writeSaved(list) { try { localStorage.setItem(SAVED_KEY, JSON.stringify(list.slice(0, 30))) } catch { /* private mode */ } }

export const statusLink = (ref, token) => `${window.location.origin}/quote/status/${ref}?t=${encodeURIComponent(token)}`
export const statusPath = (ref, token) => `/quote/status/${ref}?t=${encodeURIComponent(token)}`
export const pdfLink = (ref, token) => `/api/public/quote/${ref}/pdf?token=${encodeURIComponent(token)}`

// The signed-in customer, shared by every component on the page. undefined while loading, null when signed out.
let account
let accountLoad
const listeners = new Set()
export function setAccount(a) { account = a; listeners.forEach((f) => f(a)) }
export function refreshAccount() {
  accountLoad = call('GET', '/api/public/account').then((r) => { setAccount(r); return r }).catch(() => { setAccount({ customer: null }); return account })
  return accountLoad
}
export function useAccount() {
  const [a, setA] = useState(account)
  useEffect(() => {
    listeners.add(setA)
    if (account === undefined && !accountLoad) refreshAccount()
    else setA(account)
    return () => listeners.delete(setA)
  }, [])
  return a // {customer, reset_by_email} or undefined
}

// Quotes made before signing in become part of the account (their private links prove they are the customer's).
export async function claimSaved() {
  const items = loadSaved().map((x) => ({ ref: x.ref, token: x.token }))
  if (!items.length) return 0
  try { return (await call('POST', '/api/public/account/claim', { items })).added } catch { return 0 }
}

export const accountHref = (next) => `/quote/account${next ? `?next=${encodeURIComponent(next)}` : ''}`
