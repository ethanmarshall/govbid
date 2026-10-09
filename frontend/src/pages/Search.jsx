import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'

const HL_START = ''
const HL_END = ''

// Render a snippet whose matches are wrapped in private-use marker characters.
function Snippet({ text }) {
  if (!text) return null
  const out = []
  let rest = text
  let k = 0
  while (rest) {
    const a = rest.indexOf(HL_START)
    if (a < 0) { out.push(rest); break }
    const b = rest.indexOf(HL_END, a)
    if (b < 0) { out.push(rest.replace(HL_START, '')); break }
    if (a > 0) out.push(rest.slice(0, a))
    out.push(<mark key={k++} className="search-hit">{rest.slice(a + 1, b)}</mark>)
    rest = rest.slice(b + 1)
  }
  return <div className="search-snippet">{out}</div>
}

export default function Search() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const type = params.get('type') || ''
  const [text, setText] = useState(q)
  const [types, setTypes] = useState({})
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [inserting, setInserting] = useState(null)

  useEffect(() => { api.get('/api/search/types').then(setTypes).catch(() => {}) }, [])
  useEffect(() => { setText(q) }, [q])
  useEffect(() => {
    if (!q.trim()) { setRes(null); return }
    let live = true
    setBusy(true); setErr('')
    api.get(`/api/search?${qs({ q, types: type, limit: 60 })}`)
      .then((r) => { if (live) setRes(r) })
      .catch((e) => { if (live) setErr(e.message) })
      .finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [q, type])

  const submit = (e) => {
    e.preventDefault()
    setParams({ ...(text.trim() ? { q: text.trim() } : {}), ...(type ? { type } : {}) })
  }
  const pickType = (t) => setParams({ ...(q ? { q } : {}), ...(t ? { type: t } : {}) })

  const copy = async (r) => {
    try {
      await navigator.clipboard.writeText(r.copy || '')
      setMsg(`Copied "${r.title}".`)
    } catch {
      setErr('Your browser blocked clipboard access. Select the text in the item and copy it by hand.')
    }
  }

  const counts = {}
  ;(res?.results || []).forEach((r) => { counts[r.type] = (counts[r.type] || 0) + 1 })

  return (
    <>
      <div className="row spread">
        <h1>Search</h1>
        <a className="btn" href="/api/search/digest-preview?days=1" target="_blank" rel="noreferrer">Preview today's digest</a>
      </div>
      <p className="sub">One search over package sections, the content library, past performance, opportunities and analyses, part quotes, standards notes, contacts and source approvals. Put "exact phrases" in quotes; every word must match.</p>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder='e.g. "first article" anodize' style={{ flex: 1, minWidth: 240 }} />
        <button className="primary" type="submit" disabled={busy}>{busy ? 'Searching…' : 'Search'}</button>
      </form>
      <div className="row" style={{ marginBottom: 16 }}>
        <button type="button" className={`chip ${type ? '' : 'on'}`} onClick={() => pickType('')}>All</button>
        {Object.entries(types).map(([k, label]) => (
          <button type="button" key={k} className={`chip ${type === k ? 'on' : ''}`} onClick={() => pickType(k)}>
            {label}{!type && counts[k] ? ` (${counts[k]})` : ''}
          </button>
        ))}
      </div>
      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}
      {inserting && <InsertPanel item={inserting} onClose={() => setInserting(null)} onDone={(m) => { setMsg(m); setInserting(null) }} />}
      {res && (
        <p className="muted small">
          {res.count} result{res.count === 1 ? '' : 's'}{res.count >= 60 ? ' (showing the best 60)' : ''} · {res.engine === 'fts5' ? 'full-text index' : 'simple matching'}
        </p>
      )}
      {res && res.count === 0 && <div className="panel muted">Nothing matched. Try fewer words, or drop the quotes.</div>}
      {(res?.results || []).map((r) => (
        <div className="panel search-result" key={`${r.type}-${r.ref}`}>
          <div className="row spread">
            <div className="row">
              <span className="tag">{r.type_label}</span>
              <Link to={r.url} className="search-title">{r.title || '(untitled)'}</Link>
            </div>
            {r.reusable && (
              <div className="row">
                <button type="button" onClick={() => copy(r)}>Copy</button>
                <button type="button" onClick={() => { setMsg(''); setInserting(r) }}>Insert into a section</button>
              </div>
            )}
          </div>
          <Snippet text={r.snippet} />
        </div>
      ))}
    </>
  )
}

function InsertPanel({ item, onClose, onDone }) {
  const [pkgs, setPkgs] = useState(null)
  const [pkgId, setPkgId] = useState('')
  const [sections, setSections] = useState([])
  const [sid, setSid] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.get('/api/packages').then(setPkgs).catch((e) => setErr(e.message)) }, [])
  useEffect(() => {
    setSections([]); setSid('')
    if (!pkgId) return
    api.get(`/api/packages/${pkgId}`).then((p) => setSections(p.sections || [])).catch((e) => setErr(e.message))
  }, [pkgId])

  const insert = async () => {
    const s = sections.find((x) => String(x.id) === String(sid))
    if (!s) return
    setBusy(true); setErr('')
    try {
      // Re-read the section so the append never overwrites newer edits.
      const p = await api.get(`/api/packages/${pkgId}`)
      const cur = (p.sections || []).find((x) => x.id === s.id)?.content || ''
      const content = cur.trim() ? `${cur.replace(/\s+$/, '')}\n\n${item.copy}` : item.copy
      await api.put(`/api/sections/${s.id}`, { content })
      onDone(`Appended "${item.title}" to ${s.number ? s.number + ' ' : ''}${s.title}.`)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <div className="row spread"><h2>Insert "{item.title}"</h2><button type="button" className="link" onClick={onClose}>Close</button></div>
      {err && <div className="err">{err}</div>}
      <div className="grid g2">
        <label className="f">Package
          <select value={pkgId} onChange={(e) => setPkgId(e.target.value)}>
            <option value="">Choose a package…</option>
            {(pkgs || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label className="f">Section
          <select value={sid} onChange={(e) => setSid(e.target.value)} disabled={!sections.length}>
            <option value="">{pkgId ? (sections.length ? 'Choose a section…' : 'No sections') : 'Pick a package first'}</option>
            {sections.map((s) => <option key={s.id} value={s.id}>{[s.volume, s.number, s.title].filter(Boolean).join(' · ')}</option>)}
          </select>
        </label>
      </div>
      <p className="muted small">The text is added to the end of the section's current content.</p>
      <div className="row">
        <button type="button" className="primary" disabled={!sid || busy} onClick={insert}>{busy ? 'Adding…' : 'Append to section'}</button>
        {pkgId && sid && <Link to={`/packages/${pkgId}`}>Open package</Link>}
      </div>
    </div>
  )
}
