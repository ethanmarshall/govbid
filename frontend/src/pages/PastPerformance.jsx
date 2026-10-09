import { useEffect, useState } from 'react'
import { api, money } from '../api'

const ROLES = [
  ['prime', 'Prime contractor'],
  ['sub', 'Subcontractor'],
  ['commercial', 'Commercial customer'],
  ['personal_project', 'Independent project'],
  ['employment', 'Performed as an employee'],
]

const blank = () => ({
  title: '', customer: '', agency: '', contract_number: '', role: 'employment', contract_type: '', value: '',
  start_date: '', end_date: '', naics: '', psc: '', description: '', results: '', keywords: '',
  contact_name: '', contact_email: '', contact_phone: '', cpars_rating: '', can_use_as_reference: false, notes: '',
})

const toForm = (r) => ({ ...blank(), ...r, value: r.value ?? '', keywords: (r.relevance_keywords || []).join(', ') })

export default function PastPerformance() {
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(null) // id or 'new'
  const [form, setForm] = useState(blank)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = () => api.get('/api/past-performance?' + new URLSearchParams({ q })).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [q])

  const open = (r) => { setSel(r ? r.id : 'new'); setForm(r ? toForm(r) : blank()); setMsg(''); setErr('') }
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  const save = async () => {
    setMsg(''); setErr('')
    const { keywords, id, role_label, created_at, updated_at, relevance_keywords, ...rest } = form
    const body = { ...rest, value: form.value === '' ? null : Number(form.value), relevance_keywords: keywords }
    try {
      const r = sel === 'new' ? await api.post('/api/past-performance', body) : await api.put(`/api/past-performance/${sel}`, body)
      setSel(r.id); setForm(toForm(r)); setMsg('Saved.'); load()
    } catch (e) { setErr(e.message) }
  }

  const remove = async () => {
    if (!confirm('Delete this record?')) return
    await api.del(`/api/past-performance/${sel}`)
    setSel(null); load()
  }

  const toLibrary = async () => {
    setMsg(''); setErr('')
    try {
      const r = await api.post(`/api/past-performance/${sel}/to-library`)
      setMsg(`Added to the content library as entry #${r.id}. You can pull it into any proposal package.`)
    } catch (e) { setErr(e.message) }
  }

  return (
    <>
      <h1>Past performance</h1>
      <p className="sub">Every project you can point to as relevant experience. Records feed the bid score, the content library and a past performance volume draft.</p>
      <div className="notice">
        You do not need a prime contract to show relevant experience. Work you did as an employee or a subcontractor, and your own projects, can be described honestly as what they were (the role field labels it).
        Start with your training equipment design work and your power distribution work: what you designed, for whom, roughly how big, and what came of it.
      </div>
      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}

      <div className="pp-layout">
        <div className="panel">
          <div className="row spread" style={{ marginBottom: 10 }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, customer, keywords" style={{ flex: 1, minWidth: 180 }} />
            <button className="primary" onClick={() => open(null)}>+ Add record</button>
            <a className="btn" href="/api/past-performance/export.docx">Export volume (.docx)</a>
          </div>
          {!rows && <p className="muted">Loading…</p>}
          {rows && rows.length === 0 && <p className="muted">No records yet. Add your first project.</p>}
          {rows && rows.map((r) => (
            <div key={r.id} className={`pp-item ${sel === r.id ? 'sel' : ''}`} onClick={() => open(r)}>
              <div className="row spread">
                <b>{r.title}</b>
                <span className="tag">{r.role_label}</span>
              </div>
              <div className="small muted">
                {[r.customer || r.agency, r.start_date && `${r.start_date} to ${r.end_date || 'present'}`, r.value != null && money(r.value)].filter(Boolean).join(' · ')}
              </div>
              {r.relevance_keywords.length > 0 && <div className="small">{r.relevance_keywords.join(', ')}</div>}
            </div>
          ))}
        </div>

        <div className="panel">
          {!sel ? <p className="muted">Select a record or add a new one.</p> : (
            <>
              <h2 style={{ marginTop: 0 }}>{sel === 'new' ? 'New record' : 'Edit record'}</h2>
              <div className="grid g2">
                <label className="f" style={{ gridColumn: 'span 2' }}>Title<input value={form.title} onChange={set('title')} placeholder="Electrical trainer panel design" /></label>
                <label className="f">Customer<input value={form.customer} onChange={set('customer')} placeholder="Company or program" /></label>
                <label className="f">Agency (if federal)<input value={form.agency} onChange={set('agency')} /></label>
                <label className="f">Role<select value={form.role} onChange={set('role')}>{ROLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
                <label className="f">Contract number<input value={form.contract_number} onChange={set('contract_number')} /></label>
                <label className="f">Contract type<input value={form.contract_type} onChange={set('contract_type')} placeholder="FFP, T&M, purchase order" /></label>
                <label className="f">Value $<input type="number" value={form.value} onChange={set('value')} /></label>
                <label className="f">Start date<input type="date" value={form.start_date} onChange={set('start_date')} /></label>
                <label className="f">End date (blank = ongoing)<input type="date" value={form.end_date} onChange={set('end_date')} /></label>
                <label className="f">NAICS<input value={form.naics} onChange={set('naics')} /></label>
                <label className="f">PSC<input value={form.psc} onChange={set('psc')} /></label>
                <label className="f" style={{ gridColumn: 'span 2' }}>Description of work
                  <textarea value={form.description} onChange={set('description')} placeholder="Scope, what you personally did, tools and standards used" />
                </label>
                <label className="f" style={{ gridColumn: 'span 2' }}>Results
                  <textarea value={form.results} onChange={set('results')} placeholder="Delivered on time, units fielded, problems solved, numbers if you have them" />
                </label>
                <label className="f" style={{ gridColumn: 'span 2' }}>Relevance keywords (comma separated, used for bid matching)
                  <input value={form.keywords} onChange={set('keywords')} placeholder="power distribution, trainer panels, wire harness" />
                </label>
                <label className="f">Contact name<input value={form.contact_name} onChange={set('contact_name')} /></label>
                <label className="f">Contact email<input value={form.contact_email} onChange={set('contact_email')} /></label>
                <label className="f">Contact phone<input value={form.contact_phone} onChange={set('contact_phone')} /></label>
                <label className="f">CPARS rating (if any)<input value={form.cpars_rating} onChange={set('cpars_rating')} /></label>
                <label className="check" style={{ gridColumn: 'span 2' }}><input type="checkbox" checked={form.can_use_as_reference} onChange={set('can_use_as_reference')} /> Contact agreed to be a reference (contact details appear in exports only when checked)</label>
                <label className="f" style={{ gridColumn: 'span 2' }}>Private notes<textarea value={form.notes} onChange={set('notes')} style={{ minHeight: 50 }} /></label>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <button className="primary" onClick={save}>Save</button>
                {sel !== 'new' && <button onClick={toLibrary}>Add to content library</button>}
                {sel !== 'new' && <button className="link" onClick={remove}>Delete</button>}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
