import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from './api'
import { renderMarkdown } from './markdown'

// Mirrors writing.is_sources_sought on the backend.
const TITLE_RE = /sources?[\s-]+sought|\bRFI\b|request\s+for\s+information|market\s+(research|survey)/i
const BODY_RE = /sources?[\s-]+sought|request\s+for\s+information|\bRFI\b|for\s+market\s+research\s+purposes|market\s+research\s+(only|purposes)|capabilit(?:y|ies)\s+statements?\s+(?:is\s+|are\s+)?(?:requested|request|due|shall|should|must|will)|(?:submit|provide)\s+(?:a\s+|your\s+)?capabilit(?:y|ies)\s+statements?/i

export function isSourcesSought(o) {
  if (!o) return false
  const nt = (o.notice_type || '').toLowerCase()
  if (nt.includes('award')) return false
  if (nt.includes('sources sought')) return true
  if (TITLE_RE.test(o.title || '') || TITLE_RE.test(o.notice_type || '')) return true
  return BODY_RE.test((o.description || '').slice(0, 20000))
}

const CHECK_CLASS = { covered: 'b-eligible_now', 'needs input': 'b-eligible_once_certified', partial: 'b-eligible_once_certified', missing: 'b-not_eligible' }

export default function SourcesSoughtDraft({ opp }) {
  const applies = isSourcesSought(opp)
  const [info, setInfo] = useState(null)
  const [draft, setDraft] = useState(null)
  const [md, setMd] = useState('')
  const [checklist, setChecklist] = useState([])
  const [view, setView] = useState('preview')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (applies) api.get(`/api/writing/sources-sought/${opp.id}`).then(setInfo).catch(() => {})
  }, [opp?.id, applies])

  if (!applies) return null

  const run = async (label, fn) => {
    setBusy(label); setErr(''); setMsg(null)
    try { await fn() } catch (e) { setErr(e.message) }
    setBusy('')
  }

  const generate = () => run('draft', async () => {
    if (md && !confirm('Replace the current draft with a new one?')) return
    const d = await api.post(`/api/writing/sources-sought/${opp.id}`)
    setDraft(d); setMd(d.markdown); setChecklist(d.checklist); setOpen(true)
    if (d.warning) setErr(d.warning)
  })

  const recheck = () => run('check', async () => {
    const r = await api.post(`/api/writing/sources-sought/${opp.id}/checklist`, { markdown: md })
    setChecklist(r.checklist)
  })

  const copy = async () => {
    try { await navigator.clipboard.writeText(md); setMsg({ text: 'Copied the draft as Markdown.' }) } catch { setErr('Copy failed; select the text and copy it manually.') }
  }

  const download = () => run('docx', async () => {
    const res = await api.post(`/api/writing/sources-sought/${opp.id}/docx`, { markdown: md })
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${(opp.solicitation_number || 'notice').replace(/[^A-Za-z0-9._-]+/g, '_')}_sources_sought_response.docx`
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  })

  const save = () => run('save', async () => {
    const r = await api.post(`/api/writing/sources-sought/${opp.id}/save`, { markdown: md })
    setMsg({ text: `Saved as package "${r.name}".`, link: `/packages/${r.package_id}` })
  })

  const asked = info?.requests || []

  return (
    <div className="panel ss-panel">
      <div className="row spread">
        <div>
          <h2 style={{ margin: 0 }}>Sources sought response</h2>
          <p className="small muted" style={{ margin: '4px 0 0' }}>
            This looks like market research. A short, direct capability response (usually 2 to 5 pages) puts you on the contracting officer's list and can shape the set-aside decision.
            {asked.length > 0 && <> The notice asks {asked.length} specific question{asked.length === 1 ? '' : 's'}.</>}
          </p>
        </div>
        <div className="row">
          {md && <button onClick={() => setOpen(!open)}>{open ? 'Hide draft' : 'Show draft'}</button>}
          <button className="primary" onClick={generate} disabled={!!busy}>
            {busy === 'draft' ? 'Drafting…' : md ? 'Redraft' : `Draft response${info ? (info.ai_configured ? ' (Claude)' : ' (template)') : ''}`}
          </button>
        </div>
      </div>

      {err && <div className="err" style={{ marginTop: 12 }}>{err}</div>}
      {msg && <div className="okmsg" style={{ marginTop: 12 }}>{msg.text} {msg.link && <Link to={msg.link}>Open it</Link>}</div>}

      {!md && asked.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary className="small">What the notice asks for</summary>
          <ol className="small">{asked.map((q, i) => <li key={i}>{q}</li>)}</ol>
        </details>
      )}

      {md && open && (
        <div className="ss-body">
          <div style={{ minWidth: 0 }}>
            <div className="row spread" style={{ margin: '12px 0 8px' }}>
              <div className="row">
                <button className={`seg ${view === 'preview' ? 'on' : ''}`} onClick={() => setView('preview')}>Preview</button>
                <button className={`seg ${view === 'edit' ? 'on' : ''}`} onClick={() => setView('edit')}>Edit</button>
                <span className="small muted">{draft?.method === 'claude' ? 'Drafted by Claude' : 'Template from your profile'}; fill every [bracketed] blank before sending.</span>
              </div>
              <div className="row">
                <button onClick={copy}>Copy</button>
                <button onClick={download} disabled={!!busy}>{busy === 'docx' ? 'Building…' : 'Download .docx'}</button>
                <button onClick={save} disabled={!!busy}>{busy === 'save' ? 'Saving…' : 'Save to a package'}</button>
              </div>
            </div>
            {view === 'edit'
              ? <textarea className="editor tall" value={md} onChange={(e) => setMd(e.target.value)} />
              : <div className="md-preview ss-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(md) }} />}
          </div>
          <div className="ss-check">
            <div className="row spread" style={{ margin: '12px 0 8px' }}>
              <h3 style={{ margin: 0 }}>Checklist</h3>
              <button className="link small" onClick={recheck} disabled={!!busy}>{busy === 'check' ? 'Checking…' : 'Recheck'}</button>
            </div>
            <p className="small muted" style={{ marginTop: 0 }}>What the notice asked for, and the basics every response needs, against what the draft covers.</p>
            <ul className="checklist">
              {checklist.map((c, i) => (
                <li key={i} className={c.source === 'accuracy' ? 'acc' : ''}>
                  <span className={`badge ${CHECK_CLASS[c.status] || ''}`}>{c.status}</span>
                  <span className="small">{c.item}</span>
                </li>
              ))}
            </ul>
            {draft?.past_performance?.length > 0 && (
              <p className="small muted">Past performance used: {draft.past_performance.map((p) => p.title).join('; ')}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
