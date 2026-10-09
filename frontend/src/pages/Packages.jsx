import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, fmtDue } from '../api'
import { countWords, renderMarkdown } from '../markdown'

const KIND_LABEL = { proposal: 'Proposal', tdp: 'Technical data package' }
const STATUS_LABEL = { draft: 'Draft', in_review: 'In review', final: 'Final', submitted: 'Submitted' }

export default function Packages() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'packages'
  return (
    <>
      <h1>Packages</h1>
      <p className="sub">Build proposal packages for bids and technical data packages for completed work.</p>
      <div className="tabs">
        <button className={tab === 'packages' ? 'on' : ''} onClick={() => setParams({})}>Packages</button>
        <button className={tab === 'library' ? 'on' : ''} onClick={() => setParams({ tab: 'library' })}>Content library</button>
      </div>
      {tab === 'packages' ? <PackageList /> : <Library />}
    </>
  )
}

function PackageList() {
  const nav = useNavigate()
  const [rows, setRows] = useState(null)
  const [opps, setOpps] = useState([])
  const [f, setF] = useState({ kind: 'proposal', name: '', opportunity_id: '', contract_number: '', template: 'auto' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/api/packages').then(setRows).catch((e) => setErr(e.message))
    // Offer opportunities in the pipeline first, then everything open
    Promise.all([api.get('/api/pipeline'), api.get('/api/opportunities?limit=200')])
      .then(([pipe, all]) => {
        const seen = new Set()
        const list = [...pipe, ...all.results].filter((o) => (seen.has(o.id) ? false : seen.add(o.id)))
        setOpps(list)
      })
      .catch(() => {})
  }, [])

  const create = async () => {
    setBusy(true); setErr('')
    try {
      const p = await api.post('/api/packages', { ...f, opportunity_id: f.opportunity_id ? Number(f.opportunity_id) : null })
      nav(`/packages/${p.id}`)
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <>
      <div className="panel">
        <h2>New package</h2>
        <div className="grid g4">
          <label className="f">Type
            <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="proposal">Proposal (bid)</option>
              <option value="tdp">Technical data package (completed work)</option>
            </select>
          </label>
          <label className="f" style={{ gridColumn: 'span 2' }}>{f.kind === 'proposal' ? 'Opportunity' : 'Related opportunity (optional)'}
            <select value={f.opportunity_id} onChange={(e) => setF({ ...f, opportunity_id: e.target.value })}>
              <option value="">None</option>
              {opps.map((o) => (
                <option key={o.id} value={o.id}>{o.pipeline_stage || o.pipeline ? '★ ' : ''}{o.solicitation_number ? `${o.solicitation_number}: ` : ''}{o.title.slice(0, 90)}</option>
              ))}
            </select>
          </label>
          <label className="f">Starting outline
            <select value={f.template} onChange={(e) => setF({ ...f, template: e.target.value })}>
              <option value="auto">Standard {f.kind === 'tdp' ? 'TDP' : 'proposal'} outline</option>
              <option value="blank">Blank</option>
            </select>
          </label>
          <label className="f" style={{ gridColumn: 'span 2' }}>Name (optional)
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Defaults to the opportunity title" />
          </label>
          {f.kind === 'tdp' && (
            <label className="f">Contract number
              <input value={f.contract_number} onChange={(e) => setF({ ...f, contract_number: e.target.value })} placeholder="W912XX-26-C-0001" />
            </label>
          )}
          <div style={{ alignSelf: 'flex-end' }}>
            <button className="primary" onClick={create} disabled={busy}>{busy ? 'Creating…' : 'Create package'}</button>
          </div>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          If the opportunity has been analyzed, every compliance-matrix requirement is assigned to the section that should answer it. ★ marks opportunities in your pipeline.
        </p>
        {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
      </div>

      {rows && rows.length === 0 && <p className="muted">No packages yet.</p>}
      {rows && rows.length > 0 && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <table>
            <thead><tr><th>Package</th><th>Type</th><th>Status</th><th>Sections done</th><th>Requirements covered</th><th>Deliverables ready</th><th>Due</th></tr></thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="click" onClick={() => nav(`/packages/${p.id}`)}>
                  <td><div className="t">{p.name}</div>{p.opportunity_title && <div className="small muted">{p.opportunity_title}</div>}</td>
                  <td className="small">{KIND_LABEL[p.kind]}</td>
                  <td><span className={`badge ${p.status === 'submitted' ? 'b-eligible_now' : p.status === 'draft' ? 'b-not_eligible' : 'b-eligible_once_certified'}`}>{STATUS_LABEL[p.status]}</span></td>
                  <td><Progress n={p.sections_done} d={p.sections_total} /></td>
                  <td>{p.requirements_total ? <Progress n={p.requirements_covered} d={p.requirements_total} /> : <span className="muted small">no matrix</span>}</td>
                  <td>{p.items_total ? <Progress n={p.items_ready} d={p.items_total} /> : <span className="muted small">none</span>}</td>
                  <td className="small">{p.due_date ? fmtDue(p.due_date) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export function Progress({ n, d }) {
  const pct = d ? Math.round((100 * n) / d) : 0
  return (
    <div style={{ minWidth: 110 }}>
      <div className="small mono">{n}/{d}</div>
      <div className="bar"><span style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

function Library() {
  const [meta, setMeta] = useState(null)
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState(null)
  const [preview, setPreview] = useState(false)
  const [err, setErr] = useState('')

  const load = () => api.get('/api/library?' + new URLSearchParams({ q })).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { api.get('/api/package-meta').then(setMeta) }, [])
  useEffect(() => { load() }, [q])

  const save = async () => {
    setErr('')
    try {
      if (edit.id) await api.put(`/api/library/${edit.id}`, edit)
      else await api.post('/api/library', edit)
      setEdit(null)
      load()
    } catch (e) { setErr(e.message) }
  }

  const grouped = rows.reduce((acc, r) => ((acc[r.category] ||= []).push(r), acc), {})

  return (
    <div className="grid list-detail">
      <div>
        <div className="row" style={{ marginBottom: 10 }}>
          <input style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search library" />
          <button className="primary" onClick={() => setEdit({ category: 'Company overview', title: '', content: '', tags: [] })}>New</button>
        </div>
        {Object.entries(grouped).map(([cat, list]) => (
          <div key={cat} style={{ marginBottom: 12 }}>
            <h3 style={{ marginTop: 0 }}>{cat}</h3>
            {list.map((r) => (
              <div key={r.id} className={`card click-card ${edit?.id === r.id ? 'sel' : ''}`} onClick={() => setEdit(r)}>
                <div className="t">{r.title}</div>
                <div className="small muted">{r.words} words</div>
              </div>
            ))}
          </div>
        ))}
        {rows.length === 0 && <p className="muted small">Save content you reuse across bids: capability statement, company history, past performance write-ups, resumes, quality control plan, safety program.</p>}
      </div>
      <div className="panel">
        {!edit ? <p className="muted">Pick an entry or create a new one.</p> : (
          <>
            <div className="grid g3">
              <label className="f" style={{ gridColumn: 'span 2' }}>Title<input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></label>
              <label className="f">Category
                <select value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })}>
                  {(meta?.library_categories || []).map((c) => <option key={c}>{c}</option>)}
                </select>
              </label>
            </div>
            <div className="row spread" style={{ margin: '12px 0 6px' }}>
              <span className="small muted">Markdown: ### heading, - bullet, 1. numbered, **bold**, | tables |. {countWords(edit.content)} words.</span>
              <button className="link" onClick={() => setPreview(!preview)}>{preview ? 'Edit' : 'Preview'}</button>
            </div>
            {preview
              ? <div className="md-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(edit.content) }} />
              : <textarea className="editor" value={edit.content} onChange={(e) => setEdit({ ...edit, content: e.target.value })} />}
            {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
            <div className="row" style={{ marginTop: 10 }}>
              <button className="primary" onClick={save} disabled={!edit.title}>Save</button>
              <button onClick={() => setEdit(null)}>Cancel</button>
              {edit.id && <button onClick={async () => { if (confirm('Delete this entry?')) { await api.del(`/api/library/${edit.id}`); setEdit(null); load() } }}>Delete</button>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export { KIND_LABEL, STATUS_LABEL }
