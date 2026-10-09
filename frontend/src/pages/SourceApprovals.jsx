import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'

const usd = (n) => (n == null ? '' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const STATUS_LABELS = {
  researching: 'Researching', gathering_data: 'Gathering data', submitted: 'Submitted', under_review: 'Under review',
  approved: 'Approved', disapproved: 'Disapproved', withdrawn: 'Withdrawn',
}
const ITEM_LABELS = { todo: 'To do', in_progress: 'In progress', done: 'Done', na: 'Not applicable (statement)' }

export default function SourceApprovals() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'tracker'
  const [meta, setMeta] = useState(null)
  useEffect(() => { api.get('/api/sar/meta').then(setMeta) }, [])
  if (!meta) return <p className="muted">Loading…</p>
  const go = (t, extra = {}) => setParams({ ...(t === 'tracker' ? {} : { tab: t }), ...extra })
  return (
    <>
      <h1>Source approvals</h1>
      <p className="sub">Many DLA NSNs can only be bought from approved sources. A Source Approval Request (SAR) is the package that gets you added. Track each one here, with the DLA checklist, your files and reverse engineering notes.</p>
      <div className="tabs">
        <button className={tab === 'tracker' ? 'on' : ''} onClick={() => go('tracker')}>SARs</button>
        <button className={tab === 'candidates' ? 'on' : ''} onClick={() => go('candidates')}>Worth doing</button>
        <button className={tab === 'help' ? 'on' : ''} onClick={() => go('help')}>How DLA source approval works</button>
      </div>
      {tab === 'tracker' && <Tracker meta={meta} selected={params.get('id')} onSelect={(id) => go('tracker', id ? { id } : {})} />}
      {tab === 'candidates' && <Candidates onOpen={(id) => go('tracker', { id })} />}
      {tab === 'help' && <Help meta={meta} />}
    </>
  )
}

// ------------------------------------------------------------------ list
function Tracker({ meta, selected, onSelect }) {
  const [rows, setRows] = useState(null)
  const [status, setStatus] = useState('')
  const [err, setErr] = useState('')
  const [form, setForm] = useState({ nsn: '', part_number: '', dla_activity: '', category: '' })
  const load = () => api.get(`/api/sar?${qs({ status })}`).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [status])

  const create = async (e) => {
    e.preventDefault()
    setErr('')
    try {
      const s = await api.post('/api/sar', form)
      setForm({ nsn: '', part_number: '', dla_activity: '', category: '' })
      await load()
      onSelect(s.id)
    } catch (ex) { setErr(ex.message) }
  }

  if (selected) return <Detail meta={meta} id={selected} onBack={() => { onSelect(null); load() }} />
  return (
    <>
      {err && <div className="err">{err}</div>}
      <form className="panel" onSubmit={create}>
        <h2>Start a SAR</h2>
        <div className="grid g4">
          <label className="f">NSN<input value={form.nsn} onChange={(e) => setForm({ ...form, nsn: e.target.value })} placeholder="5340-01-480-5627" required /></label>
          <label className="f">Approved part number<input value={form.part_number} onChange={(e) => setForm({ ...form, part_number: e.target.value })} /></label>
          <label className="f">DLA activity
            <select value={form.dla_activity} onChange={(e) => setForm({ ...form, dla_activity: e.target.value })}>
              <option value="">Unknown</option>
              {meta.activities.map((a) => <option key={a}>{a}</option>)}
            </select>
          </label>
          <label className="f">Category
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="">Not chosen yet</option>
              {meta.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </label>
        </div>
        <div className="row" style={{ marginTop: 10 }}><button className="primary">Create</button></div>
      </form>
      <div className="panel">
        <div className="row spread">
          <h2>Your SARs</h2>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {meta.statuses.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
        </div>
        {!rows ? <p className="muted">Loading…</p> : rows.length === 0 ? <p className="muted">No SARs yet. Check the "Worth doing" tab for NSNs you keep seeing.</p> : (
          <table>
            <thead><tr><th>NSN</th><th>Item</th><th>Activity</th><th>Cat.</th><th>Status</th><th>Checklist</th><th>Est. annual value</th><th>In review</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="click" onClick={() => onSelect(r.id)}>
                  <td className="mono">{r.nsn}</td>
                  <td><div className="t">{r.nomenclature || r.part_number || ''}</div>{r.part_number && <span className="small muted">P/N {r.part_number}</span>}</td>
                  <td>{r.dla_activity}</td>
                  <td>{r.category}</td>
                  <td>{STATUS_LABELS[r.status]}</td>
                  <td>{r.checklist_done}/{r.checklist_required}</td>
                  <td>{usd(r.estimated_annual_value)}</td>
                  <td className={r.days_in_review > meta.review_long_days ? 'due-soon' : ''}>{r.days_in_review != null ? `${r.days_in_review} days` : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

// ------------------------------------------------------------------ detail
const EDIT_FIELDS = ['nsn', 'part_number', 'nomenclature', 'dla_activity', 'category', 'amsc', 'solicitation_number', 'status',
  'submitted_date', 'decision_date', 'decision_notes', 'approved_part_number', 'approved_cage', 'annual_demand',
  're_measurements', 're_materials', 're_notes', 'notes', 'approved_sources']

function Detail({ meta, id, onBack }) {
  const [s, setS] = useState(null)
  const [f, setF] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [onlyRequired, setOnlyRequired] = useState(true)

  const take = (d) => {
    setS(d)
    const nf = {}
    EDIT_FIELDS.forEach((k) => { nf[k] = d[k] ?? '' })
    nf.approved_sources = (d.approved_sources || []).map((a) => ({ ...a }))
    setF(nf)
  }
  useEffect(() => { api.get(`/api/sar/${id}`).then(take).catch((e) => setErr(e.message)) }, [id])
  if (err && !s) return <div className="err">{err}</div>
  if (!s || !f) return <p className="muted">Loading…</p>

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    setErr(''); setMsg('')
    try {
      const body = { ...f, annual_demand: f.annual_demand === '' || f.annual_demand == null ? null : Number(f.annual_demand) }
      take(await api.put(`/api/sar/${id}`, body))
      setMsg('Saved.')
    } catch (e) { setErr(e.message) }
  }
  const remove = async () => {
    if (!confirm('Delete this SAR and its uploaded files?')) return
    await api.del(`/api/sar/${id}`)
    onBack()
  }
  const setItem = async (key, patch) => {
    setErr('')
    try {
      const cur = s.checklist.find((r) => r.key === key)
      take(await api.put(`/api/sar/${id}`, { checklist: { [key]: { status: cur.status, note: cur.note, ...patch } } }))
    } catch (e) { setErr(e.message) }
  }
  const upload = async (key, files) => {
    if (!files?.length) return
    setErr('')
    const fd = new FormData()
    fd.append('section', key)
    Array.from(files).forEach((x) => fd.append('files', x))
    try { take((await api.upload(`/api/sar/${id}/documents`, fd)).sar) } catch (e) { setErr(e.message) }
  }
  const delFile = async (name) => {
    if (!confirm(`Delete ${name}?`)) return
    try { take(await api.del(`/api/sar/${id}/documents/${encodeURIComponent(name)}`)) } catch (e) { setErr(e.message) }
  }
  const src = f.approved_sources
  const setSrc = (i, k, v) => setF({ ...f, approved_sources: src.map((a, j) => (j === i ? { ...a, [k]: v } : a)) })
  const cat = meta.categories.find((c) => c.key === f.category)
  const items = s.checklist.filter((r) => r.section && (!onlyRequired || r.required))
  const reFiles = s.checklist.find((r) => r.key === 'RE')
  const otherFiles = s.checklist.find((r) => r.key === 'OTHER')

  return (
    <>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <button className="link" onClick={onBack}>← All SARs</button>
        <div className="row"><button onClick={remove}>Delete</button><button className="primary" onClick={save}>Save</button></div>
      </div>
      {err && <div className="err">{err}</div>}
      {msg && <div className="okmsg">{msg}</div>}
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="stat"><div className="n">{STATUS_LABELS[s.status]}</div><div className="l">Status{s.days_in_review != null ? `, ${s.days_in_review} days in review` : ''}</div></div>
        <div className="stat"><div className="n">{s.checklist_done}/{s.checklist_required}</div><div className="l">Checklist items done or N/A</div></div>
        <div className="stat"><div className="n">{s.last_award_price != null ? usd(s.last_award_price) : 'n/a'}</div><div className="l">Last award unit price</div></div>
        <div className="stat"><div className="n">{s.estimated_annual_value != null ? usd(s.estimated_annual_value) : 'n/a'}</div><div className="l">Annual demand x last price</div></div>
      </div>
      {s.days_in_review > meta.review_long_days && (
        <div className="notice">In review longer than DLA's stated range ({meta.review_min_days} to {meta.review_long_days}+ days). Ask the SAR monitor for status{s.contact?.sar_email ? ` at ${s.contact.sar_email}` : ''}.</div>
      )}

      <div className="panel">
        <h2>Item and request</h2>
        <div className="grid g4">
          <label className="f">NSN<input value={f.nsn} onChange={set('nsn')} /></label>
          <label className="f">Nomenclature<input value={f.nomenclature} onChange={set('nomenclature')} /></label>
          <label className="f">Approved part number<input value={f.part_number} onChange={set('part_number')} /></label>
          <label className="f">AMSC<input value={f.amsc} onChange={set('amsc')} maxLength={1} placeholder="B, C or D" /></label>
          <label className="f">DLA activity
            <select value={f.dla_activity} onChange={set('dla_activity')}>
              <option value="">Unknown</option>
              {meta.activities.map((a) => <option key={a}>{a}</option>)}
            </select>
          </label>
          <label className="f">Category
            <select value={f.category} onChange={set('category')}>
              <option value="">Not chosen yet</option>
              {meta.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </label>
          <label className="f">Status
            <select value={f.status} onChange={set('status')}>
              {meta.statuses.map((x) => <option key={x} value={x}>{STATUS_LABELS[x]}</option>)}
            </select>
          </label>
          <label className="f">Solicitation (alternate offer only)<input value={f.solicitation_number} onChange={set('solicitation_number')} /></label>
          <label className="f">Submitted<input type="date" value={f.submitted_date} onChange={set('submitted_date')} /></label>
          <label className="f">Decision date<input type="date" value={f.decision_date} onChange={set('decision_date')} /></label>
          <label className="f">Annual demand estimate (units)<input type="number" min="0" value={f.annual_demand ?? ''} onChange={set('annual_demand')} /></label>
          <div />
          <label className="f">Your approved part number<input value={f.approved_part_number} onChange={set('approved_part_number')} /></label>
          <label className="f">Approved under CAGE<input value={f.approved_cage} onChange={set('approved_cage')} /></label>
        </div>
        {cat && <p className="small muted" style={{ marginTop: 10 }}><b>{cat.label}.</b> {cat.definition}</p>}
        <label className="f" style={{ marginTop: 10 }}>Decision notes<textarea value={f.decision_notes} onChange={set('decision_notes')} /></label>
        <label className="f" style={{ marginTop: 10 }}>Notes<textarea value={f.notes} onChange={set('notes')} /></label>
      </div>

      <div className="panel">
        <div className="row spread"><h2>Current approved sources</h2><button onClick={() => setF({ ...f, approved_sources: [...src, { cage: '', part_number: '', name: '' }] })}>Add source</button></div>
        {src.length === 0 ? <p className="muted small">Add the CAGE codes and part numbers listed as approved for this NSN (from the RFQ or the item's procurement history).</p> : (
          <table>
            <thead><tr><th>CAGE</th><th>Part number</th><th>Company</th><th /></tr></thead>
            <tbody>
              {src.map((a, i) => (
                <tr key={i}>
                  <td><input value={a.cage} onChange={(e) => setSrc(i, 'cage', e.target.value)} className="mono" size={8} /></td>
                  <td><input value={a.part_number} onChange={(e) => setSrc(i, 'part_number', e.target.value)} /></td>
                  <td><input value={a.name} onChange={(e) => setSrc(i, 'name', e.target.value)} style={{ width: '100%' }} /></td>
                  <td><button className="link" onClick={() => setF({ ...f, approved_sources: src.filter((_, j) => j !== i) })}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="small muted">Save to keep changes.</p>
      </div>

      <div className="panel">
        <div className="row spread">
          <h2>DLA SAR checklist{f.category ? ` (Category ${f.category})` : ''}</h2>
          <label className="check"><input type="checkbox" checked={onlyRequired} onChange={(e) => setOnlyRequired(e.target.checked)} /> Only sections required for this category</label>
        </div>
        {!s.category && <p className="notice">Pick a category to see only the sections DLA requires for it. Until then every section is shown as required.</p>}
        <p className="small muted">From the checklist in the {meta.guide.title}. If a section does not apply to your part, mark it "Not applicable" and include a statement saying so, as the guide requires. Combine everything into one PDF named {s.file_name_hint || 'with the NSN and your CAGE'}.</p>
        <table>
          <thead><tr><th>Sec.</th><th>Element</th><th>State</th><th>Files</th></tr></thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.key}>
                <td className="mono">{r.section}</td>
                <td>
                  <div className="t">{r.title}{!r.required && <span className="muted small"> (not required for this category)</span>}</div>
                  <div className="small muted">{r.hint}</div>
                  <NoteInput value={r.note} onSave={(note) => setItem(r.key, { note })} />
                </td>
                <td>
                  <select value={r.status} onChange={(e) => setItem(r.key, { status: e.target.value })}>
                    {meta.item_states.map((x) => <option key={x} value={x}>{ITEM_LABELS[x]}</option>)}
                  </select>
                </td>
                <td><FileCell id={id} row={r} onUpload={upload} onDelete={delFile} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Reverse engineering notes</h2>
        <p className="small muted">For Category IV. The guide asks for a tabulation of measured dimensions (at least three sample parts recommended), materials reports, tolerance rationale and proof the samples came from the Government.</p>
        <div className="grid g2">
          <label className="f">Measurements<textarea className="mono" rows={8} value={f.re_measurements} onChange={set('re_measurements')} placeholder="Feature, nominal, sample 1, 2, 3, instrument, calibration due" /></label>
          <label className="f">Materials analysis<textarea rows={8} value={f.re_materials} onChange={set('re_materials')} placeholder="Alloy, chemistry, hardness, heat treat, coating, lab and report number" /></label>
        </div>
        <label className="f" style={{ marginTop: 10 }}>Other notes<textarea value={f.re_notes} onChange={set('re_notes')} placeholder="Sample source (RPPOB), mating parts, next higher assembly, tolerance reasoning" /></label>
        <h3>Photos and lab reports</h3>
        {reFiles && <FileCell id={id} row={reFiles} onUpload={upload} onDelete={delFile} accept="image/*,.pdf" />}
        <h3>Other files</h3>
        {otherFiles && <FileCell id={id} row={otherFiles} onUpload={upload} onDelete={delFile} />}
        <div className="row" style={{ marginTop: 12 }}><button className="primary" onClick={save}>Save notes</button></div>
      </div>

      <div className="panel">
        <h2>Solicitations for this NSN</h2>
        {s.linked_opportunities.length === 0 ? <p className="muted small">No imported DIBBS or SAM.gov opportunities with this NSN yet.</p> : (
          <table>
            <thead><tr><th>Solicitation</th><th>Title</th><th>Qty</th><th>Due</th></tr></thead>
            <tbody>
              {s.linked_opportunities.map((o) => (
                <tr key={o.id}>
                  <td className="mono"><Link to={`/opportunities/${o.id}`}>{o.solicitation_number || o.id}</Link></td>
                  <td>{o.title}</td><td>{o.quantity}</td><td>{o.response_deadline}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {s.contact && (
        <div className="panel">
          <h2>Where to send it (DLA {s.dla_activity})</h2>
          <ul className="clean">
            <li>SAR submissions: <span className="mono">{s.contact.sar_email}</span>{s.contact.note ? `. ${s.contact.note}` : ''}</li>
            {s.contact.technical && <li>Technical questions: <span className="mono">{s.contact.technical}</span></li>}
            {s.contact.rppob && <li>Buy or borrow sample parts (RPPOB): <span className="mono">{s.contact.rppob}</span></li>}
            {s.contact.small_business && <li>Small business office: <span className="mono">{s.contact.small_business}</span></li>}
          </ul>
          <p className="small muted">From Appendix A of the <a href={meta.guide.url} target="_blank" rel="noreferrer">{meta.guide.title}</a>. Files over 8 MB: email first to request a DoD SAFE link.</p>
        </div>
      )}
    </>
  )
}

function NoteInput({ value, onSave }) {
  const [v, setV] = useState(value || '')
  useEffect(() => { setV(value || '') }, [value])
  return (
    <input className="small" style={{ width: '100%', marginTop: 4 }} value={v} placeholder="Note"
      onChange={(e) => setV(e.target.value)} onBlur={() => { if (v !== (value || '')) onSave(v) }} />
  )
}

function FileCell({ id, row, onUpload, onDelete, accept }) {
  return (
    <div>
      {row.files.map((x) => (
        <div key={x.name} className="row small" style={{ gap: 6 }}>
          <a href={`/api/sar/${id}/documents/${encodeURIComponent(x.name)}`}>{x.original || x.name}</a>
          <button className="link" onClick={() => onDelete(x.name)}>×</button>
        </div>
      ))}
      <input type="file" multiple accept={accept} className="small" onChange={(e) => { onUpload(row.key, e.target.files); e.target.value = '' }} />
    </div>
  )
}

// ------------------------------------------------------------------ candidates
function Candidates({ onOpen }) {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.get('/api/sar/candidates').then(setRows).catch((e) => setErr(e.message)) }, [])
  const start = async (r) => {
    setErr('')
    try {
      const s = await api.post('/api/sar', { nsn: r.nsn, nomenclature: r.nomenclature,
        approved_sources: r.last_awardee_cage ? [{ cage: r.last_awardee_cage, name: r.last_awardee || '' }] : [] })
      onOpen(s.id)
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="panel">
      <h2>NSNs worth a SAR</h2>
      <p className="small muted">NSNs from your imported DIBBS and SAM.gov opportunities, plus part quotes flagged as approved-source only. Ranked by how many solicitations you have seen, then by the last award value from your NSN history. Approval only lets you compete; it does not guarantee orders.</p>
      {err && <div className="err">{err}</div>}
      {!rows ? <p className="muted">Loading…</p> : rows.length === 0 ? <p className="muted">No NSNs found yet. Import DIBBS RFQs or save part quotes with an NSN.</p> : (
        <table>
          <thead><tr><th>NSN</th><th>Item</th><th>Solicitations</th><th>Quotes</th><th>Last unit price</th><th>Last award value</th><th>Last awardee</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.niin}>
                <td className="mono">{r.nsn}</td>
                <td>{r.nomenclature}{r.quantities.length > 0 && <div className="small muted">Qty seen: {r.quantities.join(', ')}</div>}</td>
                <td>{r.solicitation_count}</td>
                <td>{r.quote_ids.length || ''}</td>
                <td>{usd(r.last_unit_price)}</td>
                <td>{usd(r.last_award_value)}</td>
                <td>{r.last_awardee || ''}{r.last_award_date && <div className="small muted">{r.last_award_date}</div>}</td>
                <td>{r.existing_sar_id
                  ? <button className="link" onClick={() => onOpen(r.existing_sar_id)}>Open ({STATUS_LABELS[r.existing_sar_status]})</button>
                  : <button onClick={() => start(r)}>Start SAR</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ help
function Help({ meta }) {
  return (
    <div className="panel">
      <h2>How DLA source approval works</h2>
      <ul className="clean">
        <li>A SAR can be sent any time. It must contain all the technical data needed to show you can make the NSN to the same or better quality than the current approved sources.</li>
        <li>Only NSNs bought on an "other than full and open competition" basis qualify, such as AMSC B (source controlled), C (source restricted) or D (CAGE and part number). AMSC G items are not evaluated because they are already full and open. AMSC B may also need a letter from the controlling source granting use of its data.</li>
        <li>An Alternate Offer (AO) is the same kind of package sent against an active solicitation: put the solicitation number and the contracting officer's name in the cover letter. For automated solicitations (T or U in the 9th position of the solicitation number) an AO is only considered for future buys.</li>
        <li>Review generally takes at least {meta.review_min_days} days and possibly {meta.review_long_days} days or longer, and takes longer when information is missing. Awards are not delayed while a package is pending.</li>
        <li>Format: one PDF per submission (no ZIP, no password), named with the NSN and your CAGE, emailed to the DLA activity. Over 8 MB, email to request a DoD SAFE link. Keep a copy; packages are not returned.</li>
        <li>A separate SAR is needed for each NSN. Approval to supply an assembly does not approve you to make its components unless the package shows that.</li>
        <li>Approval only grants the chance to compete. It does not guarantee contracts or orders.</li>
      </ul>
      <h3>Categories</h3>
      <ul className="clean">{meta.categories.map((c) => <li key={c.key}><b>{c.label}.</b> {c.definition}</li>)}</ul>
      <h3>Submission addresses</h3>
      <table>
        <thead><tr><th>Activity</th><th>SAR email</th><th>Sample parts (RPPOB)</th><th>Small business office</th></tr></thead>
        <tbody>
          {Object.entries(meta.contacts).map(([k, c]) => (
            <tr key={k}><td>{k}</td><td className="mono">{c.sar_email}{c.note && <div className="small muted" style={{ fontFamily: 'inherit' }}>{c.note}</div>}</td><td className="mono">{c.rppob}</td><td className="mono">{c.small_business}</td></tr>
          ))}
        </tbody>
      </table>
      <h3>Sources</h3>
      <ul className="clean small">
        <li><a href={meta.guide.url} target="_blank" rel="noreferrer">{meta.guide.title}</a> (definitions p. 4, categories p. 5 to 6, timeline and format p. 7, checklist p. 9, addresses Appendix A).</li>
        <li><a href="https://www.dla.mil/Portals/104/Documents/SmallBusiness/SAR%20TKO%20Slides%205-11-2023.pdf" target="_blank" rel="noreferrer">DLA small business SAR training slides, May 2023</a>. Military Services may add their own SAR guidance.</li>
      </ul>
    </div>
  )
}
